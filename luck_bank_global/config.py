# config.py
import logging

# --- General Settings ---
APP_NAME = "Luck Global Bank (Steady)"
TOKEN_NAME = "ONTIME"
DATABASE_FILENAME = "luck_bank_data.db"
LOG_DIRECTORY = "log"
LOG_FILENAME = "bank_app.log"
LOG_LEVEL = logging.INFO # DEBUG, INFO, WARNING, ERROR, CRITICAL

# --- Token Issuance ---
ISSUANCE_INTERVAL_MINUTES = 20 # Every 20 minutes
ISSUANCE_AMOUNT = 1.0

# --- Networking ---
DEFAULT_P2P_PORT = 61001 # Slightly different port from previous example
SOCKET_TIMEOUT = 15.0 # Seconds for connection/send/receive attempts
SOCKET_BUFFER_SIZE = 2048

# --- Wallet ---
ADDRESS_PREFIX = "LGBX_" # Changed prefix slightly
ADDRESS_LENGTH = 32

# --- GUI ---
WINDOW_TITLE = f"{APP_NAME} - Node"
HISTORY_WINDOW_TITLE = f"{APP_NAME} - Transaction History"