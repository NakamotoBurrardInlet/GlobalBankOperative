# database.py
import sqlite3
import logging
from config import DATABASE_FILENAME
from utils import generate_address
from config import ADDRESS_PREFIX, ADDRESS_LENGTH

class DatabaseManager:
    def __init__(self, db_file=DATABASE_FILENAME):
        self.db_file = db_file
        self._init_db()

    def _get_connection(self):
        """Creates a database connection."""
        try:
            # isolation_level=None enables autocommit mode, simpler for this app
            # timeout specifies how long the connection should wait for the lock to go away
            conn = sqlite3.connect(self.db_file, timeout=10.0, isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL;") # Write-Ahead Logging for better concurrency
            conn.row_factory = sqlite3.Row # Access columns by name
            return conn
        except sqlite3.Error as e:
            logging.critical(f"FATAL: Could not connect to database {self.db_file}: {e}")
            raise  # Re-raise the critical error

    def _init_db(self):
        """Initializes the database tables if they don't exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Wallet Table (should only ever have one row for this app instance)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS wallet (
                        id INTEGER PRIMARY KEY CHECK (id = 1), -- Enforce only one row
                        address TEXT UNIQUE NOT NULL,
                        balance REAL NOT NULL DEFAULT 0.0
                    )
                ''')
                # Transactions Table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        type TEXT NOT NULL CHECK(type IN ('issuance', 'sent', 'received')),
                        amount REAL NOT NULL,
                        remote_address TEXT, -- Sender/Recipient address (or NULL for issuance)
                        local_balance_after REAL NOT NULL,
                        details TEXT -- e.g., Recipient IP:Port for sent transactions
                    )
                ''')
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions (timestamp DESC);")
                logging.info("Database tables checked/created successfully.")
        except sqlite3.Error as e:
            logging.error(f"Database initialization failed: {e}")
            raise

    def get_wallet_data(self):
        """Retrieves wallet address and balance, creating if necessary."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT address, balance FROM wallet WHERE id = 1")
                data = cursor.fetchone()

                if data:
                    logging.info(f"Wallet data loaded: Address={data['address']}, Balance={data['balance']}")
                    return {"address": data['address'], "balance": float(data['balance'])}
                else:
                    # Create new wallet entry
                    new_address = generate_address(ADDRESS_PREFIX, ADDRESS_LENGTH)
                    initial_balance = 0.0
                    cursor.execute("INSERT OR IGNORE INTO wallet (id, address, balance) VALUES (1, ?, ?)",
                                   (new_address, initial_balance))
                    # Fetch again to confirm insertion (or if another instance inserted first)
                    cursor.execute("SELECT address, balance FROM wallet WHERE id = 1")
                    data = cursor.fetchone()
                    if data:
                         logging.info(f"New wallet created: Address={data['address']}, Balance={data['balance']}")
                         return {"address": data['address'], "balance": float(data['balance'])}
                    else:
                         # This should ideally not happen with INSERT OR IGNORE and id=1 check
                         logging.error("Failed to create or retrieve wallet data after insertion attempt.")
                         raise sqlite3.OperationalError("Failed to create/retrieve wallet data")
        except sqlite3.Error as e:
            logging.error(f"Failed to get wallet data: {e}")
            # Provide default safe values to allow app to potentially continue partially
            return {"address": "DB_ERROR", "balance": 0.0}


    def update_balance_add_transaction(self, tx_type, amount, new_balance, remote_address=None, details=None):
        """Atomically updates balance and adds a transaction record."""
        try:
            with self._get_connection() as conn:
                 # Use a transaction block for atomicity
                 conn.execute("BEGIN TRANSACTION;")
                 try:
                     # Update balance
                     conn.execute("UPDATE wallet SET balance = ? WHERE id = 1", (new_balance,))

                     # Add transaction log
                     conn.execute('''
                         INSERT INTO transactions (type, amount, remote_address, local_balance_after, details)
                         VALUES (?, ?, ?, ?, ?)
                     ''', (tx_type, amount, remote_address, new_balance, details))

                     conn.execute("COMMIT;") # Commit changes
                     logging.info(f"Transaction recorded: Type={tx_type}, Amount={amount}, New Balance={new_balance}")
                     return True
                 except sqlite3.Error as inner_e:
                      conn.execute("ROLLBACK;") # Rollback on error within transaction
                      logging.error(f"Database transaction failed, rolling back: {inner_e}")
                      return False
        except sqlite3.Error as e:
            logging.error(f"Failed to update balance/add transaction: {e}")
            return False

    def get_transaction_history(self, limit=100):
        """Retrieves the most recent transaction records."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, type, amount, remote_address, local_balance_after, details
                    FROM transactions
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                return cursor.fetchall() # Returns list of sqlite3.Row objects
        except sqlite3.Error as e:
            logging.error(f"Failed to retrieve transaction history: {e}")
            return []