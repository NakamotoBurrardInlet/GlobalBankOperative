# logic.py
import logging
import time
from database import DatabaseManager
from networking import P2PHandler
from config import ISSUANCE_INTERVAL_MINUTES, ISSUANCE_AMOUNT, TOKEN_NAME
from utils import get_local_ip
from config import DEFAULT_P2P_PORT

class BankLogic:
    def __init__(self, gui_callback=None):
        """
        Initializes the core bank logic.
        Args:
            gui_callback: A callable function in the GUI layer to update the UI.
                          It should accept arguments like (update_type, data).
                          e.g., gui_callback('balance_update', new_balance)
                                gui_callback('log', message)
                                gui_callback('history_update', history_list)
                                gui_callback('error', message)
        """
        self.db_manager = DatabaseManager() # Manages database interactions
        self.gui_callback = gui_callback   # Function to call for GUI updates
        self.tk_root = None                # Reference to Tkinter root needed for scheduling

        # Load initial state
        wallet_data = self.db_manager.get_wallet_data()
        self.address = wallet_data['address']
        self._balance = wallet_data['balance'] # Use internal var for controlled updates

        self.local_ip = get_local_ip()
        self.port = DEFAULT_P2P_PORT # Use the configured port

        # Initialize networking (pass self for callbacks)
        self.p2p_handler = P2PHandler(self, self.local_ip, self.port)

        self._issuance_timer_id = None # To store the .after() timer ID

    def initialize(self, tk_root):
        """
        Completes initialization requiring the Tkinter root.
        Starts networking and schedules token issuance.
        MUST be called after Tkinter root window is created.
        """
        if not tk_root:
             logging.critical("Tkinter root object not provided to BankLogic.initialize()")
             raise ValueError("Tkinter root is required for scheduling.")
        self.tk_root = tk_root

        # Start P2P Listener
        if not self.p2p_handler.start_listener():
             # Handle listener start failure (already logged in P2PHandler)
             self._notify_gui('error', f"Failed to start P2P listener on port {self.port}. Receiving disabled.")

        # Schedule first token issuance check
        self.schedule_token_issuance()
        logging.info("BankLogic initialized.")


    def _notify_gui(self, update_type, data):
        """Safely calls the GUI callback function if it exists."""
        if self.gui_callback:
            try:
                 # Schedule the GUI update in the main Tkinter thread
                 self.tk_root.after(0, self.gui_callback, update_type, data)
            except Exception as e:
                 logging.error(f"Error calling GUI callback ({update_type}): {e}")
        else:
            logging.warning(f"GUI callback not set. Update ({update_type}) not sent to UI.")

    # --- Wallet Data Access ---
    def get_balance(self):
        return self._balance

    def get_address(self):
        return self.address

    def get_p2p_info(self):
        return f"{self.local_ip}:{self.port}"

    def get_history(self, limit=100):
        return self.db_manager.get_transaction_history(limit)

    # --- Token Issuance ---
    def schedule_token_issuance(self):
        """Schedules the periodic token issuance."""
        if self._issuance_timer_id: # Cancel previous timer if exists
            self.tk_root.after_cancel(self._issuance_timer_id)

        interval_ms = ISSUANCE_INTERVAL_MINUTES * 60 * 1000
        logging.info(f"Scheduling next token issuance check in {ISSUANCE_INTERVAL_MINUTES} minutes.")
        self._issuance_timer_id = self.tk_root.after(interval_ms, self._issue_token_callback)

    def _issue_token_callback(self):
        """Callback function executed by the timer to issue tokens."""
        logging.info("Issuance interval reached. Processing token issuance.")
        new_balance = self._balance + ISSUANCE_AMOUNT

        # Update database and record transaction
        success = self.db_manager.update_balance_add_transaction(
            tx_type='issuance',
            amount=ISSUANCE_AMOUNT,
            new_balance=new_balance,
            remote_address=None, # No remote address for issuance
            details=f"{ISSUANCE_AMOUNT} {TOKEN_NAME} issued"
        )

        if success:
            self._balance = new_balance
            self._notify_gui('balance_update', self._balance)
            self._notify_gui('log', f"Received {ISSUANCE_AMOUNT:.8f} {TOKEN_NAME} via periodic issuance.")
            self._notify_gui('history_update', self.get_history()) # Update history view
            # Optional: Show a popup (might be annoying over time)
            # self._notify_gui('info_popup', f"Received {ISSUANCE_AMOUNT:.8f} {TOKEN_NAME}!")
        else:
            logging.error("Failed to record token issuance transaction in database.")
            self._notify_gui('error', "Database error during token issuance.")

        # Schedule the next issuance regardless of success
        self.schedule_token_issuance()


    # --- P2P Transfer Handling ---

    def initiate_send(self, recipient_info, amount_str):
        """Validates and initiates a P2P token transfer."""
        # 1. Validate Recipient Info
        try:
            if ':' not in recipient_info:
                 raise ValueError("Invalid format. Use IP_ADDRESS:PORT")
            recipient_ip, recipient_port_str = recipient_info.strip().split(':')
            recipient_port = int(recipient_port_str)
            # Basic IP format check (can be improved)
            parts = recipient_ip.split('.')
            if len(parts) != 4 or not all(0 <= int(p) <= 255 for p in parts):
                 raise ValueError("Invalid IP address format")
        except ValueError as e:
            logging.warning(f"Invalid recipient info format: {recipient_info} - {e}")
            self._notify_gui('error', f"Invalid P2P Info: {e}. Use IP:PORT (e.g., 192.168.1.5:61001).")
            return

        # 2. Validate Amount
        try:
            amount = float(amount_str)
            if amount <= 0:
                self._notify_gui('error', "Send amount must be positive.")
                return
            # Use a small tolerance for float comparison
            if amount > self._balance + 1e-9: # Add tolerance
                self._notify_gui('error', f"Insufficient funds. You have {self._balance:.8f} {TOKEN_NAME}.")
                return
        except ValueError:
            self._notify_gui('error', "Invalid amount. Please enter a number.")
            return

        # 3. Initiate Send via Networking Layer
        self._notify_gui('log', f"Validating send of {amount:.8f} to {recipient_ip}:{recipient_port}...")
        # Networking layer will handle the actual sending in a background thread
        self.p2p_handler.send_message(recipient_ip, recipient_port, amount, self.address)


    def handle_send_result(self, result, amount, recipient_info_str):
        """
        Callback executed by P2PHandler after a send attempt.
        MUST run in the main thread (use root.after from P2PHandler).
        """
        # This function is scheduled by P2PHandler using root.after, so it runs in the main thread
        logging.debug(f"Handling send result: {result}")
        if result.get("status") == "success":
            # Send was successful, update balance and log transaction
            new_balance = self._balance - amount
            success = self.db_manager.update_balance_add_transaction(
                tx_type='sent',
                amount=amount,
                new_balance=new_balance,
                remote_address=None, # We don't store recipient *wallet address* here easily
                details=f"Sent to {recipient_info_str}" # Log IP:Port
            )
            if success:
                self._balance = new_balance
                self._notify_gui('balance_update', self._balance)
                self._notify_gui('log', f"Successfully sent {amount:.8f} {TOKEN_NAME} to {recipient_info_str}.")
                self._notify_gui('history_update', self.get_history())
            else:
                 # This is serious - network send succeeded but DB failed
                 logging.critical(f"CRITICAL: Send to {recipient_info_str} confirmed by peer, BUT database update FAILED!")
                 self._notify_gui('error', f"CRITICAL DB ERROR after sending {amount:.8f}. Balance may be inconsistent!")
                 # Consider mechanisms to retry DB update or alert user more strongly

        else:
            # Send failed (network error, peer error, etc.)
            reason = result.get("reason", "Unknown failure reason")
            self._notify_gui('log', f"Send failed: {reason}")
            self._notify_gui('error_popup', f"Failed to send {TOKEN_NAME}:\n{reason}")


    def handle_received_transfer(self, amount, sender_address, sender_ip_port):
        """
        Processes an incoming transfer request (called by P2PHandler).
        This method might be called from a network thread, so database/GUI updates
        need careful handling (DB manager is likely okay, GUI needs scheduling).
        Returns True on success, False on failure (e.g., DB error).
        """
        logging.info(f"Processing received transfer: {amount} from {sender_address} via {sender_ip_port}")
        new_balance = self._balance + amount

        # Update database and record transaction
        success = self.db_manager.update_balance_add_transaction(
            tx_type='received',
            amount=amount,
            new_balance=new_balance,
            remote_address=sender_address, # Store sender's wallet address
            details=f"Received from {sender_ip_port[0]}:{sender_ip_port[1]}" # Log sender IP:Port
        )

        if success:
            # Schedule the balance/GUI update in the main thread
            def _update_state_and_gui():
                self._balance = new_balance
                self._notify_gui('balance_update', self._balance)
                self._notify_gui('log', f"Received {amount:.8f} {TOKEN_NAME} from {sender_address}.")
                self._notify_gui('history_update', self.get_history())

            self.schedule_task(0, _update_state_and_gui) # Use scheduler
            return True
        else:
            logging.error(f"Failed to record received transaction from {sender_address} in database.")
            # Don't update balance if DB failed
            # P2PHandler will send an error response back to the sender
            return False

    def handle_network_error(self, message):
         """Callback for network errors (e.g., listener bind failure)."""
         self._notify_gui('error', message) # Show error in main GUI log


    def schedule_task(self, delay_ms, callback, *args):
        """Schedules a function to run in the main Tkinter thread."""
        if self.tk_root:
            return self.tk_root.after(delay_ms, callback, *args)
        else:
            logging.error("Cannot schedule task: Tkinter root not available.")
            return None

    def shutdown(self):
        """Performs cleanup operations."""
        logging.info("BankLogic shutting down...")
        if self._issuance_timer_id:
            try:
                 self.tk_root.after_cancel(self._issuance_timer_id)
                 logging.info("Token issuance timer cancelled.")
            except Exception as e:
                 logging.warning(f"Could not cancel issuance timer: {e}")
        self.p2p_handler.stop_listener()
        # Database connection is managed per-operation, no explicit close needed here
        logging.info("BankLogic shutdown complete.")