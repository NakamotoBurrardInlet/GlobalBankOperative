# utils.py
import string
import random
import socket
import logging
import os
import sys
from config import LOG_LEVEL, LOG_DIRECTORY, LOG_FILENAME

def generate_address(prefix="LGBX_", length=32):
    """Generates a random alphanumeric address."""
    chars = string.ascii_uppercase + string.digits
    return prefix + ''.join(random.choice(chars) for _ in range(length))

def get_local_ip():
    """Tries to get the local IP address for sharing."""
    # Prefer IPs on common private ranges if multiple interfaces exist
    preferred_prefixes = ('192.168.', '10.', '172.16.', '172.17.', '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.', '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.', '172.30.', '172.31.')
    try:
        host_name = socket.gethostname()
        all_ips = socket.getaddrinfo(host_name, None, socket.AF_INET)
        ip_addresses = [ip[4][0] for ip in all_ips]

        # Try to find a preferred IP
        for ip in ip_addresses:
            if any(ip.startswith(prefix) for prefix in preferred_prefixes):
                return ip

        # If no preferred IP found, return the first one or fallback
        if ip_addresses:
            return ip_addresses[0]

    except socket.gaierror:
         logging.warning("Could not automatically determine local IP via hostname. Falling back.")
    except Exception as e:
        logging.warning(f"Error getting local IP: {e}. Falling back.")

    # Fallback method
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 1)) # Connect to external address (doesn't send data)
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1' # Ultimate fallback
    finally:
        s.close()
    return ip


def setup_logging():
    """Configures logging to file and console."""
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s:%(lineno)d] - %(message)s')
    root_logger = logging.getLogger()
    root_logger.setLevel(LOG_LEVEL)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    root_logger.addHandler(console_handler)

    # File Handler
    try:
        if not os.path.exists(LOG_DIRECTORY):
            os.makedirs(LOG_DIRECTORY)
        log_path = os.path.join(LOG_DIRECTORY, LOG_FILENAME)
        file_handler = logging.FileHandler(log_path, mode='a') # Append mode
        file_handler.setFormatter(log_formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"Logging initialized. Log file: {log_path}")
    except Exception as e:
        logging.error(f"Failed to set up file logging to {LOG_DIRECTORY}/{LOG_FILENAME}: {e}")