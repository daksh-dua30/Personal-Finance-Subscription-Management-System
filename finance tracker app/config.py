import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()


class Config:
    """Application and Database Configuration Settings."""

    # Flask Security
    SECRET_KEY = os.environ.get(
        'SECRET_KEY', 'fintrack-production-secret-key-2025-secure')

    # MySQL Database Connection Settings
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'root')
    # Change "YOUR_MYSQL_PASSWORD" to your actual MySQL root password or set MYSQL_PASSWORD env variable
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_NAME = os.environ.get('DB_NAME', 'finance_tracker_db')

    # Connection Pool Settings
    DB_POOL_NAME = 'finance_tracker_pool'
    DB_POOL_SIZE = 5

    @classmethod
    def get_db_config(cls):
        return {
            'host': cls.DB_HOST,
            'port': cls.DB_PORT,
            'user': cls.DB_USER,
            'password': cls.DB_PASSWORD,
            'database': cls.DB_NAME,
            'autocommit': False,  # Managed explicitly or per query
            'raise_on_warnings': True
        }
