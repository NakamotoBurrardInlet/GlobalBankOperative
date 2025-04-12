# networking.py
import socket
import threading
import json
import logging
from config import DEFAULT_P2P_PORT, SOCKET_TIMEOUT, SOCKET_BUFFER_SIZE

class P2PHandler:
    def __init__(self, logic_callback_object, local_ip, port=DEFAULT_P2P_PORT):
        """
        Initializes the P2P handler.
        Args:
            logic_callback_object: Instance of BankLogic to call back to.
            local_ip (str): The local IP address to bind the listener to.
            port (int): The port to listen on.
        """
        self.logic = logic_callback_object
        self.local_ip = local_ip
        self.port = port
        self.server_socket = None
        self.listener_thread = None
        self.running = False

    def start_listener(self):
        """Starts the network listener thread."""
        if self.running:
            logging.warning("Listener already running.")
            return
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.local_ip, self.port))
            self.server_socket.listen(5)
            self.running = True
            self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self.listener_thread.start()
            logging.info(f"P2P Listener started on {self.local_ip}:{self.port}")
            return True
        except OSError as e:
            logging.error(f"!!! FAILED TO BIND LISTENER TO {self.local_ip}:{self.port} - {e} !!!")
            logging.error("Port might be in use. P2P receiving will NOT work.")
            self.server_socket = None
            self.running = False
            # Notify logic/GUI about the failure
            if hasattr(self.logic, 'handle_network_error'):
                 # Use scheduler if available (likely from GUI via logic)
                 if hasattr(self.logic, 'schedule_task'):
                      self.logic.schedule_task(0, self.logic.handle_network_error, f"Listener failed: {e}")
                 else: # Fallback direct call (less safe if logic updates GUI directly)
                      self.logic.handle_network_error(f"Listener failed: {e}")

            return False
        except Exception as e:
            logging.error(f"Unexpected error starting listener: {e}")
            self.running = False
            return False

    def stop_listener(self):
        """Stops the network listener."""
        self.running = False
        if self.server_socket:
            try:
                # Shut down the socket to interrupt the accept() call
                self.server_socket.shutdown(socket.SHUT_RDWR)
                self.server_socket.close()
                logging.info("P2P Listener socket closed.")
            except OSError as e:
                # OSError is expected if socket is already closed or shutting down
                logging.debug(f"Error closing server socket (might be expected on shutdown): {e}")
            except Exception as e:
                logging.warning(f"Unexpected error closing server socket: {e}")
        self.server_socket = None
        # Wait briefly for thread to exit (optional, as it's daemon)
        # if self.listener_thread and self.listener_thread.is_alive():
        #     self.listener_thread.join(timeout=1.0)


    def _listen_loop(self):
        """Background thread function to accept incoming connections."""
        while self.running and self.server_socket:
            try:
                client_socket, addr = self.server_socket.accept()
                logging.info(f"Accepted connection from {addr}")
                client_socket.settimeout(SOCKET_TIMEOUT)
                # Handle each client in a new thread
                handler_thread = threading.Thread(target=self._handle_client, args=(client_socket, addr), daemon=True)
                handler_thread.start()
            except socket.timeout: # Should not happen with accept, but defensive
                continue
            except OSError: # Expected when socket is closed by stop_listener
                logging.info("Listener socket closed, exiting listen loop.")
                self.running = False
                break
            except Exception as e:
                if self.running: # Only log unexpected errors if we are supposed to be running
                     logging.error(f"Error accepting connection: {e}")
                time.sleep(0.5) # Prevent busy-loop on continuous errors

        logging.info("P2P Listener thread finished.")


    def _handle_client(self, client_socket, addr):
        """Handles message reception from a connected client."""
        raw_data = b''
        try:
            while True: # Loop to receive potentially fragmented data
                chunk = client_socket.recv(SOCKET_BUFFER_SIZE)
                if not chunk:
                    break # Connection closed by peer
                raw_data += chunk
                # Basic check: assume message ends with '}' for JSON
                if raw_data.strip().endswith(b'}'):
                    break
                # Add a safeguard against infinitely growing buffer if peer sends non-JSON
                if len(raw_data) > SOCKET_BUFFER_SIZE * 10:
                     raise ValueError("Received data too large or not valid JSON.")

            if not raw_data:
                 logging.warning(f"No data received from {addr} or connection closed prematurely.")
                 return

            data_str = raw_data.decode('utf-8').strip()
            logging.debug(f"Received raw data from {addr}: {data_str}")
            message = json.loads(data_str)

            # --- Process Message ---
            action = message.get("action")
            response = {"status": "error", "message": "Unknown action"} # Default error response

            if action == "transfer":
                amount_str = message.get("amount")
                sender_address = message.get("sender_address")
                if amount_str is None or sender_address is None:
                    response = {"status": "error", "message": "Missing 'amount' or 'sender_address'"}
                else:
                    try:
                        amount = float(amount_str)
                        if amount <= 0:
                            response = {"status": "error", "message": "Invalid amount (must be positive)"}
                        else:
                             # Call back to logic layer (must be thread-safe!)
                             # Logic layer will handle DB update and GUI notification via scheduler
                             success = self.logic.handle_received_transfer(amount, sender_address, addr)
                             if success:
                                 response = {"status": "success", "message": "Transfer acknowledged"}
                                 logging.info(f"Received valid transfer of {amount} from {sender_address} via {addr}")
                             else:
                                 # Logic layer failed (e.g., DB error)
                                 response = {"status": "error", "message": "Internal server error processing transfer"}
                                 logging.error(f"Logic layer failed to process transfer from {sender_address}")

                    except ValueError:
                        response = {"status": "error", "message": "Invalid amount format"}
                    except Exception as e:
                         response = {"status": "error", "message": f"Server processing error: {e}"}
                         logging.exception(f"Error processing transfer message from {addr}:") # Log full traceback

            else:
                logging.warning(f"Received unknown action '{action}' from {addr}")

            # Send response back to client
            client_socket.sendall(json.dumps(response).encode('utf-8'))

        except json.JSONDecodeError:
            logging.error(f"Received invalid JSON from {addr}: {raw_data.decode('utf-8', errors='ignore')}")
            try:
                client_socket.sendall(json.dumps({"status": "error", "message": "Invalid JSON format"}).encode('utf-8'))
            except Exception: pass
        except UnicodeDecodeError:
             logging.error(f"Received non-UTF8 data from {addr}")
             try:
                  client_socket.sendall(json.dumps({"status": "error", "message": "Invalid encoding (use UTF-8)"}).encode('utf-8'))
             except Exception: pass
        except ValueError as e: # Handle amount conversion errors or custom value errors
             logging.error(f"Data validation error handling client {addr}: {e}")
             try:
                  client_socket.sendall(json.dumps({"status": "error", "message": f"Data error: {e}"}).encode('utf-8'))
             except Exception: pass
        except socket.timeout:
            logging.warning(f"Socket timeout handling client {addr}")
        except Exception as e:
            logging.error(f"Unhandled error handling client {addr}: {e}")
            logging.exception("Traceback:") # Log traceback for unexpected errors
            try:
                # Send generic error if possible
                client_socket.sendall(json.dumps({"status": "error", "message": "Unexpected server error"}).encode('utf-8'))
            except Exception: pass
        finally:
            client_socket.close()
            logging.debug(f"Connection from {addr} closed")


    def send_message(self, ip, port, amount, sender_address):
        """Connects to a peer and sends a transfer message. Runs in background thread."""

        def _send_thread_target():
            result = {"status": "failed", "reason": "Unknown error"} # Default result
            recipient_info_str = f"{ip}:{port}"
            logging.info(f"Attempting to send {amount:.8f} {TOKEN_NAME} to {recipient_info_str}...")

            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(SOCKET_TIMEOUT)
                    sock.connect((ip, port))

                    message = {
                        "action": "transfer",
                        "amount": str(amount), # Send amount as string for broader compatibility
                        "sender_address": sender_address
                    }
                    payload = json.dumps(message).encode('utf-8')
                    sock.sendall(payload)
                    logging.debug(f"Sent payload to {recipient_info_str}: {payload.decode()}")

                    # Wait for response
                    response_raw = sock.recv(SOCKET_BUFFER_SIZE)
                    if not response_raw:
                         raise ConnectionAbortedError("Peer closed connection without response.")

                    response_data = response_raw.decode('utf-8')
                    response = json.loads(response_data)
                    logging.debug(f"Received response from {recipient_info_str}: {response}")

                    if response.get("status") == "success":
                        result["status"] = "success"
                        result["reason"] = response.get("message", "Transfer successful")
                        logging.info(f"Successfully sent {amount:.8f} {TOKEN_NAME} to {recipient_info_str}")
                    else:
                        result["status"] = "failed_peer_error"
                        result["reason"] = response.get('message', 'Unknown error reported by recipient')
                        logging.warning(f"Recipient {recipient_info_str} reported error: {result['reason']}")

            except socket.timeout:
                result["reason"] = f"Connection to {recipient_info_str} timed out."
                logging.warning(result["reason"])
            except ConnectionRefusedError:
                result["reason"] = f"Connection refused by {recipient_info_str}. (Node offline or wrong port?)"
                logging.warning(result["reason"])
            except ConnectionAbortedError as e:
                 result["reason"] = f"Connection aborted by {recipient_info_str}. {e}"
                 logging.warning(result["reason"])
            except json.JSONDecodeError:
                result["reason"] = f"Invalid response format received from {recipient_info_str}."
                logging.error(result["reason"] + f" Raw: {response_raw.decode('utf-8', errors='ignore')}")
            except UnicodeDecodeError:
                 result["reason"] = f"Received non-UTF8 response from {recipient_info_str}."
                 logging.error(result["reason"])
            except Exception as e:
                result["reason"] = f"Unexpected error sending to {recipient_info_str}: {e}"
                logging.exception(f"Detailed error during send to {recipient_info_str}:") # Log full traceback

            # --- Callback to logic layer ---
            # Must be scheduled to run in the main thread if it updates GUI
            self.logic.handle_send_result(result, amount, recipient_info_str)


        # Start the sending operation in a separate thread
        send_thread = threading.Thread(target=_send_thread_target, daemon=True)
        send_thread.start()