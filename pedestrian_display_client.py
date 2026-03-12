import rpyc
import tkinter as tk
from tkinter import ttk, font
import threading
import time
import sys
import uuid
from rpyc.utils.classic import obtain

class PedestrianDisplay:
    def __init__(self, server_host, server_port):
        self.client_id = f"ped_display_{uuid.uuid4().hex[:6]}"
        self.server_host = server_host
        self.server_port = server_port
        self.connection = None
        self.running = True
        self.connected = False
        self.ped_state = {'1_2': 0, '3_4': 0}
        self.root = tk.Tk()
        self.root.title(f"Pedestrian Display ({self.client_id})")
        self.root.geometry("400x300")
        self.root.configure(bg='gray10')
        self.setup_gui()

    def setup_gui(self):
        self.status_label = ttk.Label(self.root, text="🔄 CONNECTING...", background="yellow", anchor="center")
        self.status_label.pack(fill=tk.X, padx=10, pady=5)
        bold_font = font.Font(family="Helvetica", size=24, weight="bold")
        self.label_1_2 = tk.Label(self.root, text="ROADS 1 & 2", font=bold_font, bg="gray10", fg="white")
        self.label_1_2.pack(pady=(20, 5))
        self.state_1_2 = tk.Label(self.root, text="---", font=bold_font, bg="black", fg="white", width=10)
        self.state_1_2.pack(pady=5)
        self.label_3_4 = tk.Label(self.root, text="ROADS 3 & 4", font=bold_font, bg="gray10", fg="white")
        self.label_3_4.pack(pady=(20, 5))
        self.state_3_4 = tk.Label(self.root, text="---", font=bold_font, bg="black", fg="white", width=10)
        self.state_3_4.pack(pady=5)
        
    def connect_to_server(self):
        while self.running:
            if not self.connected:
                try:
                    print(f"[{self.client_id}] Connecting to {self.server_host}:{self.server_port}")
                    # **** THIS IS THE FIX ****
                    # Add config={'allow_pickle': True} to the connection call.
                    self.connection = rpyc.connect(
                        self.server_host, self.server_port,
                        config={'allow_pickle': True}
                    )
                    self.connection.root.register_client("pedestrian_display", self.client_id)
                    self.connected = True
                    print(f"[{self.client_id}] Connected and registered.")
                    self.root.after(0, self.status_label.config, {'text': '✅ CONNECTED', 'background': 'lightgreen'})
                except Exception as e:
                    print(f"[{self.client_id}] Connection failed: {e}")
                    self.connected = False
                    self.root.after(0, self.status_label.config, {'text': '❌ DISCONNECTED', 'background': 'red'})
                    time.sleep(5)
            else:
                time.sleep(10)

    def update_from_server(self):
        if self.running and self.connected:
            try:
                state_data_proxy = self.connection.root.get_signal_state()
                self.ped_state = obtain(state_data_proxy['pedestrian'])
                self.update_display()
            except Exception as e:
                print(f"[{self.client_id}] Update error: {e}")
                self.connected = False
                self.root.after(0, self.status_label.config, {'text': '❌ DISCONNECTED', 'background': 'red'})
        self.root.after(1000, self.update_from_server)

    def update_display(self):
        state12 = self.ped_state.get('1_2', 0)
        if state12 == 1:
            self.state_1_2.config(text="WALK", bg="green", fg="white")
        else:
            self.state_1_2.config(text="STOP", bg="red", fg="white")
        state34 = self.ped_state.get('3_4', 0)
        if state34 == 1:
            self.state_3_4.config(text="WALK", bg="green", fg="white")
        else:
            self.state_3_4.config(text="STOP", bg="red", fg="white")

    def on_closing(self):
        self.running = False
        if self.connection:
            self.connection.close()
        self.root.destroy()

    def start(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        threading.Thread(target=self.connect_to_server, daemon=True).start()
        self.root.after(1000, self.update_from_server)
        self.root.mainloop()

if __name__ == "__main__":
    server_host = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    server_port = int(sys.argv[2]) if len(sys.argv) > 2 else 18812
    app = PedestrianDisplay(server_host, server_port)
    app.start()