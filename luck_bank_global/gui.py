# gui.py
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox, Toplevel, ttk
import logging
from logic import BankLogic # Import the logic class
from config import WINDOW_TITLE, TOKEN_NAME, HISTORY_WINDOW_TITLE

class BankAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(WINDOW_TITLE)
        # self.root.geometry("650x500") # Optional: Set initial size

        # Configure style for themed widgets
        self.style = ttk.Style()
        self.style.theme_use('clam') # Or 'alt', 'default', 'classic'

        # Create and initialize the logic component
        # Pass the 'update_gui' method as the callback
        self.logic = BankLogic(gui_callback=self.update_gui)

        # Complete logic initialization (requires root for scheduling)
        self.logic.initialize(self.root)

        # --- GUI Elements ---
        self.create_widgets()

        # Populate initial data
        self.update_balance_display(self.logic.get_balance())
        self.address_var.set(self.logic.get_address())
        self.p2p_info_var.set(self.logic.get_p2p_info())
        self.log_message(f"Welcome to {WINDOW_TITLE}!")
        self.log_message(f"Your Address: {self.logic.get_address()}")
        self.log_message(f"Share your P2P Info to receive tokens: {self.logic.get_p2p_info()}")

        self.history_window = None # To track the history window

        # Handle window closing
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)


    def create_widgets(self):
        """Creates and arranges all GUI widgets."""
        main_frame = ttk.Frame(self.root, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1) # Make log area expand horizontally
        main_frame.rowconfigure(2, weight=1)    # Make log area expand vertically

        # --- Info Section ---
        info_frame = ttk.LabelFrame(main_frame, text="Wallet Info", padding="10")
        info_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        info_frame.columnconfigure(1, weight=1) # Make entry fields expand

        ttk.Label(info_frame, text="Address:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.address_var = tk.StringVar()
        address_entry = ttk.Entry(info_frame, textvariable=self.address_var, state='readonly', width=45)
        address_entry.grid(row=0, column=1, sticky=(tk.W, tk.E))

        ttk.Label(info_frame, text="Balance:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5,0))
        self.balance_var = tk.StringVar()
        balance_label = ttk.Label(info_frame, textvariable=self.balance_var, font=('Helvetica', 12, 'bold'))
        balance_label.grid(row=1, column=1, sticky=tk.W)

        ttk.Label(info_frame, text="P2P Info:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5,0))
        self.p2p_info_var = tk.StringVar()
        p2p_entry = ttk.Entry(info_frame, textvariable=self.p2p_info_var, state='readonly', width=45)
        p2p_entry.grid(row=2, column=1, sticky=(tk.W, tk.E))
        ttk.Label(info_frame, text="(Share this IP:Port)", style='secondary.TLabel').grid(row=3, column=1, sticky=tk.W)
        self.style.configure('secondary.TLabel', foreground='gray')

        # --- Action Section ---
        action_frame = ttk.Frame(main_frame, padding="5")
        action_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        action_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        send_button = ttk.Button(action_frame, text=f"Send {TOKEN_NAME}", command=self.show_send_dialog, width=18)
        send_button.grid(row=0, column=0, padx=5, pady=5, sticky=tk.E)

        history_button = ttk.Button(action_frame, text="Show History", command=self.show_history_window, width=18)
        history_button.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)


        # --- Log Section ---
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.N, tk.S, tk.E, tk.W))
        log_frame.columnconfigure(0, weight=1) # Make text widget expand
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=70, state='disabled', wrap=tk.WORD, relief=tk.FLAT)
        self.log_text.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        # Configure tags for message types (optional styling)
        self.log_text.tag_configure("ERROR", foreground="red")
        self.log_text.tag_configure("SUCCESS", foreground="green")
        self.log_text.tag_configure("INFO", foreground="black")
        self.log_text.tag_configure("WARNING", foreground="orange")


    def update_gui(self, update_type, data):
        """
        Callback method called by the BankLogic to update the GUI.
        This method MUST run in the main Tkinter thread.
        Logic layer ensures this using root.after().
        """
        logging.debug(f"GUI received update: Type={update_type}, Data={data}")
        if update_type == 'balance_update':
            self.update_balance_display(data)
        elif update_type == 'log':
            self.log_message(data, "INFO")
        elif update_type == 'error':
            self.log_message(f"ERROR: {data}", "ERROR")
        elif update_type == 'warning':
             self.log_message(f"WARNING: {data}", "WARNING")
        elif update_type == 'success':
             self.log_message(data, "SUCCESS")
        elif update_type == 'history_update':
            # If history window is open, refresh it
            if self.history_window and self.history_window.winfo_exists():
                self.populate_history_tree(data)
        elif update_type == 'error_popup':
            messagebox.showerror("Error", data, parent=self.root)
        elif update_type == 'info_popup':
             messagebox.showinfo("Information", data, parent=self.root)
        else:
            logging.warning(f"GUI received unknown update type: {update_type}")

    def update_balance_display(self, new_balance):
        """Formats and updates the balance label."""
        self.balance_var.set(f"{new_balance:.8f} {TOKEN_NAME}")

    def log_message(self, message, tag="INFO"):
        """Adds a timestamped message to the log area with optional styling."""
        # Ensure we're manipulating the widget in the main thread
        def _do_log():
            timestamp = time.strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}\n"
            self.log_text.config(state='normal')
            # Insert with the specified tag
            self.log_text.insert(tk.END, formatted_message, (tag,))
            self.log_text.see(tk.END) # Scroll to the bottom
            self.log_text.config(state='disabled')
        # If called directly from GUI event, root.after isn't strictly needed,
        # but using it makes it safe if called from logic callbacks too.
        self.root.after(0, _do_log)


    def show_send_dialog(self):
        """Opens dialogs to get recipient info and amount for sending."""
        recipient_info = simpledialog.askstring("Send ONTIME",
                                                "Enter recipient's P2P Info (IP_ADDRESS:PORT):",
                                                parent=self.root)
        if not recipient_info: return # User cancelled

        amount_str = simpledialog.askstring("Send ONTIME",
                                            f"Enter amount of {TOKEN_NAME} to send:",
                                            parent=self.root)
        if not amount_str: return # User cancelled

        # Pass validated data to the logic layer for processing
        self.logic.initiate_send(recipient_info, amount_str)


    def show_history_window(self):
        """Opens or focuses the transaction history window."""
        if self.history_window and self.history_window.winfo_exists():
            self.history_window.lift() # Bring existing window to front
            return

        self.history_window = Toplevel(self.root)
        self.history_window.title(HISTORY_WINDOW_TITLE)
        self.history_window.geometry("750x400")

        # --- Treeview for History ---
        cols = ('Timestamp', 'Type', 'Amount', 'Balance After', 'Remote Address', 'Details')
        self.history_tree = ttk.Treeview(self.history_window, columns=cols, show='headings', height=15)

        # Define headings
        for col in cols:
            self.history_tree.heading(col, text=col)
            # Adjust column widths (heuristic)
            if col == 'Timestamp': width = 140
            elif col == 'Type': width = 70
            elif col == 'Amount': width = 100
            elif col == 'Balance After': width = 110
            elif col == 'Remote Address': width = 150
            else: width = 100 # Details
            self.history_tree.column(col, width=width, anchor=tk.W)


        # Scrollbars
        vsb = ttk.Scrollbar(self.history_window, orient="vertical", command=self.history_tree.yview)
        hsb = ttk.Scrollbar(self.history_window, orient="horizontal", command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Layout
        self.history_tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        self.history_window.grid_rowconfigure(0, weight=1)
        self.history_window.grid_columnconfigure(0, weight=1)

        # --- Refresh Button ---
        refresh_button = ttk.Button(self.history_window, text="Refresh",
                                     command=lambda: self.populate_history_tree(self.logic.get_history()))
        refresh_button.grid(row=2, column=0, columnspan=2, pady=10)


        # Populate with current data
        self.populate_history_tree(self.logic.get_history())

        # Set focus behavior
        self.history_window.transient(self.root) # Keep window on top of main
        self.history_window.grab_set() # Prevent interaction with main until closed (optional)
        self.root.wait_window(self.history_window) # Wait until closed


    def populate_history_tree(self, history_data):
        """Clears and repopulates the history Treeview."""
        if not self.history_window or not self.history_window.winfo_exists():
             return # Don't try to update if window closed

        # Clear existing items
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        # Insert new data (rows are sqlite3.Row objects)
        for row in history_data:
            # Format data for display
            timestamp = row['timestamp'].split('.')[0] # Remove microseconds if present
            type = str(row['type']).capitalize()
            amount = f"{row['amount']:.8f}"
            balance_after = f"{row['local_balance_after']:.8f}"
            remote = row['remote_address'] if row['remote_address'] else '-'
            details = row['details'] if row['details'] else '-'

            values = (timestamp, type, amount, balance_after, remote, details)
            self.history_tree.insert('', tk.END, values=values)


    def on_closing(self):
        """Handles window closing: shutdown logic and destroy window."""
        if messagebox.askokcancel("Quit", f"Do you want to exit {WINDOW_TITLE}?", parent=self.root):
            self.log_message("Shutting down...", "WARNING")
            self.logic.shutdown() # Tell logic layer to clean up (stop timers/network)
            self.root.destroy() # Close the Tkinter window