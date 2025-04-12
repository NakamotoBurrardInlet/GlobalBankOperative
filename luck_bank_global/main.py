# main.py
import tkinter as tk
import logging
from gui import BankAppGUI
from utils import setup_logging
from config import APP_NAME

if __name__ == "__main__":
    # Configure logging first
    setup_logging()
    logging.info(f"Starting {APP_NAME}...")

    # Create the main Tkinter window
    root = tk.Tk()

    # Set window properties (optional, can also be in GUI class)
    # root.geometry("650x500")

    # Instantiate the GUI application (which also initializes logic)
    try:
        app = BankAppGUI(root)
    except Exception as e:
        # Catch critical errors during initialization (e.g., DB connection)
        logging.critical(f"Failed to initialize application: {e}", exc_info=True)
        messagebox.showerror("Fatal Error", f"Application failed to start:\n{e}\n\nCheck logs for details.")
        root.destroy() # Close the empty window
        exit(1) # Exit with error code


    # Start the Tkinter event loop
    logging.info("Starting Tkinter main event loop.")
    root.mainloop()

    logging.info(f"{APP_NAME} exited gracefully.")