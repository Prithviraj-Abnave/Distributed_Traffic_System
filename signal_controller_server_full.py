import rpyc
from rpyc.utils.server import ThreadedServer
import threading
import time
import random
import logging
from datetime import datetime
import queue

# --- Configuration ---
HOST = '0.0.0.0' # Listen on all network interfaces
PORT = 18812

# --- Constants ---
# Signal States
RED, YELLOW, GREEN = 0, 1, 2
# Pedestrian States
PED_RED, PED_GREEN = 0, 1

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s',
    handlers=[
        logging.FileHandler("traffic_controller.log"),
        logging.StreamHandler()
    ]
)

class TrafficControllerService(rpyc.Service):
    def __init__(self):
        super().__init__()
        # This lock protects shared state. For full Task 5, a more complex
        # ReadWriteLock would be ideal, but a standard Lock is sufficient here.
        self.state_lock = threading.Lock()
        
        # --- State Variables ---
        self.traffic_signals = {1: RED, 2: RED, 3: RED, 4: RED}
        self.pedestrian_signals = {'1_2': PED_GREEN, '3_4': PED_RED} # For roads 1&2 and 3&4
        self.active_pair = (3, 4)  # Start with roads 3 & 4 being green initially
        self.is_switching = False
        
        # --- Client Management ---
        self.clients = {}
        # This setup is for Version 1 (Tasks 1-4).
        # You can adjust this for Version 2 (RTOs) if needed.
        self.required_clients = {'traffic_display': 1, 'pedestrian_display': 2}
        self.all_clients_connected = False
        self.active_clients = 0 # Simple counter
        
        # --- Task-Specific Components ---
        # Task 1 & 4: Request Queue & Load Balancing
        self.request_queue = queue.Queue(maxsize=20) # Max 20 requests before "overloaded"
        
        # Task 3: VIP Deadlock Management
        self.vip_queue = queue.PriorityQueue() # (priority, road_id, timestamp)
        
        logging.info("Traffic Controller Service initialized.")
        
    def on_connect(self, conn):
        logging.info(f"Client connected: {conn}")
        self.active_clients += 1

    def on_disconnect(self, conn):
        logging.warning(f"A client has disconnected: {conn}. Operations may be halted.")
        self.active_clients -= 1
        self.all_clients_connected = False
        self.clients.clear() # Clear registered clients to force re-registration
        logging.error("A client disconnected. Halting operations and waiting for all clients to reconnect.")


    def _check_start_condition(self):
        """Check if all required clients are connected."""
        # Check if the number of connected clients meets the total requirement
        required_total = sum(self.required_clients.values())
        if self.active_clients >= required_total:
             if not self.all_clients_connected:
                self.all_clients_connected = True
                logging.info("All required clients have connected. Starting operations.")
                # Start the main control loop and other handlers
                threading.Thread(target=self._main_control_loop, name="ControlLoop", daemon=True).start()
                threading.Thread(target=self._simulate_traffic_requests, name="RequestSim", daemon=True).start()
                threading.Thread(target=self._vip_request_handler, name="VIPHandler", daemon=True).start()
        else:
            logging.info(f"Waiting for clients. Connected: {self.active_clients}, Required: {required_total}")
            
    # --- RPyC Exposed Methods ---
    
    def exposed_register_client(self, client_type, client_id):
        """Allows clients to register themselves with the controller."""
        if client_id in self.clients:
            logging.warning(f"Client ID {client_id} already exists. Re-registering.")
        
        self.clients[client_id] = {'type': client_type}
        logging.info(f"Registered client: ID='{client_id}', Type='{client_type}'")
        self._check_start_condition()

    def exposed_get_signal_state(self):
        """[Task 5: READ] Provides the current state of all signals."""
        with self.state_lock:
            return {
                'signals': self.traffic_signals.copy(),
                'pedestrian': self.pedestrian_signals.copy()
            }
            
    def exposed_request_green(self, road_id):
        """[Task 2 & 4] External method for a road to request green light."""
        if self.request_queue.full():
            logging.error(f"Request queue is full! SERVER OVERLOADED. Dropping request from Road {road_id}.")
            return False # Reject request
        
        request = (road_id, time.time())
        self.request_queue.put(request)
        logging.info(f"[MUTEX] Road {road_id} requested green. Added to queue. Queue size: {self.request_queue.qsize()}")
        return True

    def exposed_vip_request(self, road_id, distance):
        """[Task 3] Method for VIP vehicles to request passage."""
        priority = distance # Lower distance = higher priority
        self.vip_queue.put((priority, road_id, time.time()))
        logging.warning(f"[DEADLOCK MGMT] VIP request from Road {road_id} at distance {distance}. Added to priority queue.")

    def exposed_force_signal_state(self, road_id):
        """[Task 5: WRITE] Allows an RTO to force a signal switch."""
        logging.warning(f"[RTO OVERRIDE] Received request to force Road {road_id} green.")
        
        # Check if a switch is already happening to prevent conflicts.
        with self.state_lock:
            if self.is_switching:
                logging.error("Cannot process RTO request: a switch is already in progress.")
                return False

            current_green_pair, _ = self._get_pairs()
            if road_id in current_green_pair:
                logging.info(f"RTO request for Road {road_id} is for an already green light. No action needed.")
                return True
        
        # Since the target road is not green, initiate a switch.
        # Run in a new thread to avoid blocking the RTO client.
        logging.info(f"RTO override is triggering a signal switch for Road {road_id}.")
        threading.Thread(target=self._switch_signals, daemon=True).start()
        return True

    # --- Core Logic ---
    
    def _main_control_loop(self):
        """The main loop that controls the signal timing and state changes."""
        green_pair, _ = self._get_pairs()
        self._set_green(green_pair)
        
        while True:
            if not self.all_clients_connected:
                time.sleep(1)
                continue
            
            if not self.vip_queue.empty():
                time.sleep(0.1) # Let VIP handler manage it
                continue
                
            if not self.request_queue.empty():
                road_id, req_time = self.request_queue.get()
                logging.info(f"[MUTEX] Processing request for Road {road_id}. Granting access.")
                
                current_green_pair, _ = self._get_pairs()
                if road_id in current_green_pair:
                    logging.info(f"Request from Road {road_id} is for an already green light. Ignoring.")
                    continue
                
                self._switch_signals()
            
            time.sleep(0.5)

    def _vip_request_handler(self):
        """[Task 3] Handles VIP requests, resolving potential deadlocks."""
        while True:
            if self.all_clients_connected and not self.vip_queue.empty():
                priority, road_id, req_time = self.vip_queue.get()
                logging.warning(f"[DEADLOCK MGMT] Handling VIP request for Road {road_id}.")
                
                current_green_pair, _ = self._get_pairs()
                if road_id in current_green_pair:
                    logging.info(f"VIP on Road {road_id} has a green light. No action needed.")
                    continue
                
                logging.warning(f"VIP on Road {road_id} requires signal switch. Forcing switch now.")
                self._switch_signals()
            
            time.sleep(1)
            
    def _switch_signals(self):
        """Manages the 5-second transition period between signal pairs."""
        with self.state_lock:
            if self.is_switching:
                return # Avoid concurrent switches
            self.is_switching = True

        logging.info("Starting signal switch...")
        
        green_pair, red_pair = self._get_pairs()
        
        with self.state_lock:
            self.traffic_signals[green_pair[0]] = YELLOW
            self.traffic_signals[green_pair[1]] = YELLOW
            logging.info(f"Roads {green_pair} set to YELLOW.")
            
        blinker_thread = threading.Thread(target=self._blink_red, args=(red_pair, 5), daemon=True)
        blinker_thread.start()
        
        time.sleep(5)
        blinker_thread.join()
        
        with self.state_lock:
            self.active_pair = red_pair
            
            self.traffic_signals[green_pair[0]] = RED
            self.traffic_signals[green_pair[1]] = RED
            if green_pair == (1, 2):
                self.pedestrian_signals['1_2'] = PED_GREEN
            else:
                self.pedestrian_signals['3_4'] = PED_GREEN

            self.traffic_signals[red_pair[0]] = GREEN
            self.traffic_signals[red_pair[1]] = GREEN
            if red_pair == (1, 2):
                self.pedestrian_signals['1_2'] = PED_RED
            else:
                self.pedestrian_signals['3_4'] = PED_RED
            
            logging.info(f"Switch complete. Roads {red_pair} are now GREEN.")
            self.is_switching = False

    def _blink_red(self, road_pair, duration):
        """Simulates blinking red light for a given duration."""
        end_time = time.time() + duration
        is_red = True
        while time.time() < end_time:
            with self.state_lock:
                state = RED if is_red else 0.5 # Using 0.5 for "off" state
                self.traffic_signals[road_pair[0]] = state
                self.traffic_signals[road_pair[1]] = state
            is_red = not is_red
            time.sleep(0.5)
        with self.state_lock:
            self.traffic_signals[road_pair[0]] = RED
            self.traffic_signals[road_pair[1]] = RED

    def _set_green(self, road_pair):
        """Helper to set a pair of roads to green and others to red."""
        with self.state_lock:
            all_roads = {1, 2, 3, 4}
            red_roads = all_roads - set(road_pair)
            
            for r in road_pair: self.traffic_signals[r] = GREEN
            for r in red_roads: self.traffic_signals[r] = RED

            if road_pair == (1, 2):
                self.pedestrian_signals['1_2'] = PED_RED
                self.pedestrian_signals['3_4'] = PED_GREEN
            else:
                self.pedestrian_signals['3_4'] = PED_RED
                self.pedestrian_signals['1_2'] = PED_GREEN
            logging.info(f"Initial state set: Roads {road_pair} GREEN.")
            
    def _get_pairs(self):
        """Returns the current green and red pairs based on the active pair."""
        if self.active_pair == (1, 2):
            return (1, 2), (3, 4)
        else:
            return (3, 4), (1, 2)

    def _simulate_traffic_requests(self):
        """Simulates roads requesting green lights randomly."""
        while True:
            if self.all_clients_connected:
                road_to_request = random.randint(1, 4)
                self.exposed_request_green(road_to_request)
                
                if random.random() < 0.1: # 10% chance for a VIP
                    vip_road = random.randint(1,4)
                    vip_dist = random.randint(10, 100)
                    self.exposed_vip_request(vip_road, vip_dist)

            time.sleep(random.uniform(5, 12))


if __name__ == "__main__":
    logging.info(f"Starting Traffic Controller Server on {HOST}:{PORT}")
    server = ThreadedServer(
        TrafficControllerService(),
        port=PORT,
        protocol_config={"allow_pickle": True}
    )
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Server shutting down.")
        server.close()