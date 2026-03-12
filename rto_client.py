import rpyc
import tkinter as tk
from tkinter import ttk, messagebox, font
import sys
import threading
import time
from datetime import datetime
from rpyc.utils.classic import obtain # ✅ IMPORT THIS

class RTOClient:
    def __init__(self, server_host, server_port):
        self.server_host = server_host
        self.server_port = server_port
        self.connection = None
        self.running = True
        self.connected = False
        
        # State data
        self.signals = {1: 0, 2: 0, 3: 0, 4: 0}
        
        # GUI elements
        self.root = tk.Tk()
        self.root.title("RTO Monitoring & Control")
        self.root.geometry("500x350")
        self.root.configure(bg='gray15')
        
        self.status_labels = {}
        self.setup_gui()

    def setup_gui(self):
        # Status Bar
        self.connection_status_label = ttk.Label(self.root, text="🔄 CONNECTING...", background="yellow", anchor="center")
        self.connection_status_label.pack(fill=tk.X, padx=10, pady=5)
        
        # Main content frames
        main_frame = ttk.Frame(self.root, style='TFrame')
        main_frame.pack(expand=True, fill="both", padx=10, pady=10)
        
        status_frame = ttk.LabelFrame(main_frame, text=" Live Signal Status ", style='TLabelframe')
        status_frame.pack(side="left", fill="both", expand=True, padx=5)
        
        control_frame = ttk.LabelFrame(main_frame, text=" Manual Override ", style='TLabelframe')
        control_frame.pack(side="right", fill="both", expand=True, padx=5)
        
        # Configure styles
        self.root.style = ttk.Style()
        self.root.style.configure('TFrame', background='gray15')
        self.root.style.configure('TLabelframe', background='gray15', foreground='white')
        self.root.style.configure('TLabel', background='gray15', foreground='white', font=('Helvetica', 12))
        self.root.style.configure('TButton', font=('Helvetica', 10, 'bold'))

        # Status Labels inside the status_frame
        bold_font = font.Font(family="Arial", size=16, weight="bold")
        for i in range(1, 5):
            frame = ttk.Frame(status_frame, style='TFrame')
            frame.pack(pady=10)
            ttk.Label(frame, text=f"Road {i}:").pack(side="left", padx=5)
            self.status_labels[i] = tk.Label(frame, text="---", font=bold_font, bg="black", fg="white", width=8, relief="sunken")
            self.status_labels[i].pack(side="left")

        # Control Buttons inside the control_frame
        for i in range(1, 5):
            button = ttk.Button(control_frame, text=f"Force Road {i} Green", 
                                command=lambda road_id=i: self.force_green(road_id))
            button.pack(pady=15, padx=10, fill='x')

    def connect_to_server(self):
        while self.running:
            if not self.connected:
                try:
                    print(f"Attempting to connect to {self.server_host}:{self.server_port}")
                    self.connection = rpyc.connect(
                        self.server_host, self.server_port,
                        config={'allow_pickle': True, 'sync_request_timeout': 30}
                    )
                    self.connection.root.register_client("rto_client", f"rto_{time.time()}")
                    self.connected = True
                    print("Connected to Traffic Controller.")
                    self.root.after(0, self.connection_status_label.config, {'text': '✅ CONNECTED', 'background': 'lightgreen'})
                except Exception as e:
                    print(f"Connection failed: {e}")
                    self.connected = False
                    self.root.after(0, self.connection_status_label.config, {'text': '❌ DISCONNECTED', 'background': 'red'})
                    time.sleep(5)
            else:
                time.sleep(10)

    def force_green(self, road_id):
        if not self.connected:
            messagebox.showwarning("Offline", "Cannot send command. Not connected to the server.")
            return
        try:
            success = self.connection.root.force_signal_state(road_id)
            if success:
                messagebox.showinfo("Command Sent", f"Request to force Road {road_id} green was sent successfully.")
            else:
                messagebox.showerror("Command Failed", "Server was busy or unable to process the request.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to send command: {e}")
            self.connected = False

    def update_status_loop(self):
        """Continuously fetches state from the server in a background thread."""
        while self.running:
            if self.connected:
                try:
                    state_data_proxy = self.connection.root.get_signal_state()
                    # ✅ THIS IS THE FIX: Convert the proxy to a real dict
                    self.signals = obtain(state_data_proxy['signals'])
                    
                    self.root.after(0, self.update_display)
                except Exception as e:
                    print(f"Failed to get state: {e}")
                    self.connected = False
                    self.root.after(0, self.connection_status_label.config, {'text': '❌ DISCONNECTED', 'background': 'red'})
            time.sleep(1)

    def update_display(self):
        """Updates the GUI labels with the latest state data."""
        state_map = {
            0: ("RED", "red"),
            0.5: ("RED", "maroon"),
            1: ("YELLOW", "yellow"),
            2: ("GREEN", "lime green")
        }
        for road_id, label in self.status_labels.items():
            # Now self.signals is a real dictionary, so .get() works perfectly
            state = self.signals.get(road_id, 0)
            text, color = state_map.get(state, ("UNKNOWN", "gray"))
            label.config(text=text, bg=color, fg="black" if color == "yellow" else "white")

    def on_closing(self):
        self.running = False
        if self.connection:
            self.connection.close()
        self.root.destroy()

    def start(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        threading.Thread(target=self.connect_to_server, daemon=True).start()
        threading.Thread(target=self.update_status_loop, daemon=True).start()
        self.root.mainloop()

if __name__ == "__main__":
    server_host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    server_port = int(sys.argv[2]) if len(sys.argv) > 2 else 18812
    client = RTOClient(server_host, server_port)
    client.start()