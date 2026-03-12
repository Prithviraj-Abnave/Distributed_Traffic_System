import rpyc
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
from datetime import datetime

class TrafficSignalDisplay:
    def __init__(self, server_host='localhost', server_port=18812):
        self.server_host = server_host
        self.server_port = server_port
        self.connection = None
        self.running = True
        self.signals = {1: 0, 2: 0, 3: 0, 4: 0}
        self.last_update = None
        self.root = None
        self.canvas = None
        self.signal_objects = {}
        self.status_label = None
        self.connected = False
        
    def connect_to_server(self):
        try:
            print(f"Connecting to Traffic Controller at {self.server_host}:{self.server_port}")
            # **** THIS IS THE FIX ****
            # Add config={'allow_pickle': True} to the connection call.
            self.connection = rpyc.connect(self.server_host, self.server_port, config={
                'sync_request_timeout': 30,
                'allow_pickle': True
            })
            self.connection.root.register_client("traffic_display", "display_001")
            self.connected = True
            print("Connected to Traffic Signal Controller")
            threading.Thread(target=self.update_from_server, daemon=True).start()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            messagebox.showerror("Connection Error", f"Failed to connect to server: {e}")
            return False
    
    def update_from_server(self):
        while self.running and self.connected:
            try:
                state_data = self.connection.root.get_signal_state()
                self.signals = state_data['signals']
                self.last_update = datetime.now()
                if self.root:
                    self.root.after(0, self.update_display)
                time.sleep(0.5)
            except Exception as e:
                print(f"Update error: {e}")
                self.connected = False
                if self.root:
                    self.root.after(0, lambda: self.status_label.config(
                        text="❌ DISCONNECTED", background="red"))
                time.sleep(5)
    
    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Traffic Signal Display - 4-Way Intersection")
        self.root.geometry("800x800")
        self.root.configure(bg='darkgreen')
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        self.status_label = ttk.Label(status_frame, text="🔄 CONNECTING...", 
                                     background="yellow", foreground="black")
        self.status_label.pack(side=tk.LEFT)
        self.time_label = ttk.Label(status_frame, text="")
        self.time_label.pack(side=tk.RIGHT)
        self.canvas = tk.Canvas(self.root, width=760, height=760, bg='darkgreen')
        self.canvas.pack(padx=20, pady=20)
        self.draw_intersection()
        self.draw_traffic_signals()
        self.update_time_display()
        return self.root
    
    def draw_intersection(self):
        road_color = 'gray20'
        line_color = 'yellow'
        self.canvas.create_rectangle(320, 0, 440, 760, fill=road_color, outline='')
        for y in range(0, 760, 40):
            self.canvas.create_rectangle(375, y, 385, y+20, fill=line_color, outline='')
        self.canvas.create_rectangle(0, 320, 760, 440, fill=road_color, outline='')
        for x in range(0, 760, 40):
            self.canvas.create_rectangle(x, 375, x+20, 385, fill=line_color, outline='')
        self.canvas.create_rectangle(320, 320, 440, 440, fill='gray15', outline='')
        self.canvas.create_text(380, 50, text="ROAD 1\n(North)", fill='white', 
                               font=('Arial', 12, 'bold'))
        self.canvas.create_text(380, 710, text="ROAD 2\n(South)", fill='white', 
                               font=('Arial', 12, 'bold'))
        self.canvas.create_text(50, 380, text="ROAD 3\n(West)", fill='white', 
                               font=('Arial', 12, 'bold'))
        self.canvas.create_text(710, 380, text="ROAD 4\n(East)", fill='white', 
                               font=('Arial', 12, 'bold'))
        self.draw_pedestrian_crossings()
    
    def draw_pedestrian_crossings(self):
        crossing_color = 'white'
        for i in range(0, 120, 10):
            self.canvas.create_rectangle(325+i, 310, 335+i, 320, fill=crossing_color, outline='')
        for i in range(0, 120, 10):
            self.canvas.create_rectangle(325+i, 440, 335+i, 450, fill=crossing_color, outline='')
        for i in range(0, 120, 10):
            self.canvas.create_rectangle(310, 325+i, 320, 335+i, fill=crossing_color, outline='')
        for i in range(0, 120, 10):
            self.canvas.create_rectangle(440, 325+i, 450, 335+i, fill=crossing_color, outline='')
    
    def draw_traffic_signals(self):
        positions = {1: (350, 280), 2: (410, 480), 3: (280, 350), 4: (480, 410)}
        for road_id, (x, y) in positions.items():
            self.canvas.create_rectangle(x-5, y-5, x+45, y+85, fill='black', outline='gray')
            red_light = self.canvas.create_oval(x, y, x+35, y+25, fill='darkred', outline='black', width=2)
            yellow_light = self.canvas.create_oval(x, y+30, x+35, y+55, fill='darkorange', outline='black', width=2)
            green_light = self.canvas.create_oval(x, y+60, x+35, y+85, fill='darkgreen', outline='black', width=2)
            self.signal_objects[road_id] = {'red': red_light, 'yellow': yellow_light, 'green': green_light}
            self.canvas.create_text(x+17, y-15, text=f"#{road_id}", fill='white', font=('Arial', 10, 'bold'))
    
    def update_display(self):
        if not self.canvas or not self.signal_objects:
            return
        colors = {
            0: {'red': 'red', 'yellow': 'darkorange', 'green': 'darkgreen'},
            0.5: {'red': '#300', 'yellow': 'darkorange', 'green': 'darkgreen'},
            1: {'red': 'darkred', 'yellow': 'yellow', 'green': 'darkgreen'},
            2: {'red': 'darkred', 'yellow': 'darkorange', 'green': 'lime'}
        }
        for road_id in range(1, 5):
            if road_id in self.signals and road_id in self.signal_objects:
                state = self.signals[road_id]
                signal_colors = colors.get(state, colors[0])
                self.canvas.itemconfig(self.signal_objects[road_id]['red'], fill=signal_colors['red'])
                self.canvas.itemconfig(self.signal_objects[road_id]['yellow'], fill=signal_colors['yellow'])
                self.canvas.itemconfig(self.signal_objects[road_id]['green'], fill=signal_colors['green'])
        if self.connected:
            self.status_label.config(text="✅ CONNECTED", background="lightgreen")
        else:
            self.status_label.config(text="❌ DISCONNECTED", background="red")
    
    def update_time_display(self):
        if self.time_label:
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            last_update_str = self.last_update.strftime("%H:%M:%S") if self.last_update else "Never"
            time_text = f"Current: {current_time} | Last Update: {last_update_str}"
            self.time_label.config(text=time_text)
        if self.root:
            self.root.after(1000, self.update_time_display)
    
    def on_closing(self):
        self.running = False
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
        self.root.destroy()

def main():
    print("Traffic Signal Display Client")
    print("=" * 40)
    server_host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    server_port = int(sys.argv[2]) if len(sys.argv) > 2 else 18812
    display = TrafficSignalDisplay(server_host, server_port)
    root = display.create_gui()
    root.protocol("WM_DELETE_WINDOW", display.on_closing)
    connect_thread = threading.Thread(target=display.connect_to_server, daemon=True)
    connect_thread.start()
    print("Starting GUI main loop...")
    root.mainloop()

if __name__ == "__main__":
    main()