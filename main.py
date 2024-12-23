import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import platform
import socket
import threading
import json
import os
import queue

class PingApp:
    VERSION: str = "1.1.0"

    def __init__(self, master):
        self.master = master
        self.master.title(f"IP Scanner Tool - v{self.VERSION}")
        self.master.resizable(False, False)

        # Create a queue for thread communication
        self.queue = queue.Queue()
        self.master.after(100, self.process_queue)  # Start processing the queue after 100ms

        # Set the window size
        self.window_width = 700
        self.window_height = 400
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        x = (screen_width // 2) - (self.window_width // 2)
        y = (screen_height // 2) - (self.window_height // 2)
        self.master.geometry(f"{self.window_width}x{self.window_height}+{x}+{y}")

        # Create a frame to hold the buttons next to each other
        button_frame = tk.Frame(master)
        button_frame.pack(pady=10)

        # Load IP button
        self.load_button = tk.Button(button_frame, text="Load IP Addresses", command=self.load_ip_addresses)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # Check Button to start scanning
        self.check_button = tk.Button(button_frame, text="Ping and Check Ports", command=self.start_checking, state=tk.DISABLED)
        self.check_button.pack(side=tk.LEFT, padx=5)

        # Stop button to stop scanning
        self.stop_button = tk.Button(button_frame, text="Stop", command=self.stop_checking, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        self.stop_scanning = False

        # Timeout input
        tk.Label(button_frame, text="Timeout (sec):").pack(side=tk.LEFT, padx=5)
        self.timeout_value = tk.IntVar(value=2)
        self.timeout_entry = tk.Spinbox(button_frame, from_=1, to=10, textvariable=self.timeout_value)
        self.timeout_entry.pack(side=tk.LEFT, padx=5)

        # Treeview for Results
        tree_frame = tk.Frame(master)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("Key", "IP Address", "Connection State", "Port", "Port State", "Time"), show='headings', height=10)
        self.tree.heading("Key", text="Key Name")
        self.tree.heading("IP Address", text="IP Address")
        self.tree.heading("Connection State", text="Connection State")
        self.tree.heading("Port", text="Port")
        self.tree.heading("Port State", text="Port State")
        self.tree.heading("Time", text="Time (ms)")
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.column("Key", width=100)
        self.tree.column("IP Address", width=150)
        self.tree.column("Connection State", width=120)
        self.tree.column("Port", width=100)
        self.tree.column("Port State", width=120)
        self.tree.column("Time", width=100)

        # Initialize IP addresses list
        self.ip_addresses = []

        # Status bar at the bottom
        self.status_bar = tk.Label(master, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Set tag colors
        self.tree.tag_configure('success', background='lightgreen')
        self.tree.tag_configure('failure', background='lightcoral')
        self.tree.tag_configure('grey', background='lightgrey')  # Grey tag for loaded IPs

    def load_ip_addresses(self):
        """Load IP addresses and ports from a selected configuration file."""
        file_path = filedialog.askopenfilename(title="Open Configuration File", filetypes=[("JSON Files", "*.json")])
        if file_path:
            try:
                with open(file_path, 'r') as file:
                    config = json.load(file)
                    self.ip_addresses = [(key, value.split(':')[0], value.split(':')[1] if ':' in value else None) for key, value in config.items()]
                    self.check_button.config(state=tk.NORMAL)
                    self.master.title(f"IP Scanner Tool - v{self.VERSION} - {os.path.basename(file_path)}")

                    # Insert the loaded IPs as grey in the treeview
                    for key, ip, port in self.ip_addresses:
                        self.tree.insert('', 'end', values=(key, ip, "Loaded", port if port else "Not Checked", "Not Checked", "N/A"), tags=['grey'])
                    
                    messagebox.showinfo("Success", "IP addresses loaded successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load IP addresses: {str(e)}")

    def start_checking(self):
        """Start the checking process in a separate thread."""
        self.stop_scanning = False  # Reset the stop flag
        self.check_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        threading.Thread(target=self.check).start()

    def stop_checking(self):
        """Stop the checking process by setting the stop flag."""
        self.stop_scanning = True
        self.status_bar.config(text="Scanning stopped.")
        self.stop_button.config(state=tk.DISABLED)

    def check(self):
        """Ping each IP address and optionally check the specified ports."""
        total_count = len(self.ip_addresses)
        timeout = self.timeout_value.get()

        for count, (key, ip, port) in enumerate(self.ip_addresses, 1):
            if self.stop_scanning:
                break

            self.status_bar.config(text=f"IP {ip} scanning. {count} of {total_count}")
            self.status_bar.update_idletasks()

            # Find the existing row for the IP address
            existing_row = None
            for row in self.tree.get_children():
                item = self.tree.item(row)
                if item['values'][1] == ip:  # Check if the IP matches
                    existing_row = row
                    break

            # Put "Connecting" state in the queue
            if existing_row:
                self.queue.put(("update", existing_row, key, ip, "Connecting", port if port else "Not Checked", "Not Checked", "N/A"))

            # Perform the actual ping
            ping_result, ping_time = self.ping(ip, timeout)

            # Now check the port if a port is specified
            if port:
                port_result = self.check_port(ip, port, timeout)
                connection_state = "Connected" if ping_result == "Response received" else "Not Connected"
                if port_result == "Open" and connection_state == "Not Connected":
                    connection_state = "Connected (Port Open)"
                port_state = "Open" if port_result == "Open" else "Closed"
                # Put final state in the queue
                self.queue.put(("update", existing_row, key, ip, connection_state, port, port_state, ping_time))
            else:
                connection_state = "Connected" if ping_result == "Response received" else "Not Connected"
                # Put final state in the queue
                self.queue.put(("update", existing_row, key, ip, connection_state, "Not Checked", "Not Checked", ping_time))

        if not self.stop_scanning:
            self.status_bar.config(text="Scanning complete.")
        
        # Use after() to safely update the button in the main thread, only if the window is still open
        if self.master.winfo_exists():  # Check if the window is still alive
            self.master.after(0, self.check_button.config, {"state": tk.NORMAL})
            self.master.after(0, self.stop_button.config, {"state": tk.DISABLED})

    def update_row(self, row_id, key, ip, connection_state, port, port_state, time):
        """Update an existing row in the treeview."""
        tags = ['failure'] if connection_state == "Not Connected" or port_state == "Closed" else ['success']
        self.tree.item(row_id, values=(key, ip, connection_state, port, port_state, time), tags=tags)

    def insert_row(self, key, ip, connection_state, port, port_state, time):
        """Insert a row into the table and color-code based on status."""
        tags = ['failure'] if connection_state == "Not Connected" or port_state == "Closed" else ['success']
        self.tree.insert('', 'end', values=(key, ip, connection_state, port, port_state, time), tags=tags)

    def ping(self, ip, timeout):
        """Ping the specified IP address with the given timeout and return the result along with the time taken."""
        param = '-n' if platform.system().lower() == 'windows' else '-c'
        command = ['ping', param, '4', ip, '-w' if platform.system().lower() == 'windows' else '-W', str(timeout * 1000)]

        try:
            output = subprocess.check_output(command, universal_newlines=True)
            if "Reply from" in output or "TTL=" in output:
                time_str = output.split("time=")[-1].split("ms")[0].strip()
                return "Response received", time_str
            else:
                return "No response", "N/A"
        except subprocess.CalledProcessError:
            return "Ping failed", "N/A"

    def check_port(self, ip, port, timeout):
        """Check if the specified port is open on the given IP address with the specified timeout."""
        try:
            with socket.create_connection((ip, int(port)), timeout=timeout):
                return "Open"
        except (socket.timeout, socket.error):
            return "Closed"
        
    def process_queue(self):
        """Process the queue and update the treeview with the results."""
        try:
            while True:
                message = self.queue.get_nowait()  # Non-blocking, get the message
                if message[0] == "update":
                    # Update the row in the treeview with the data from the queue
                    self.update_row(*message[1:])
                self.queue.task_done()  # Mark the task as done
        except queue.Empty:
            pass
        # Call this method again after 100ms to continue processing
        self.master.after(100, self.process_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = PingApp(root)
    root.mainloop()
