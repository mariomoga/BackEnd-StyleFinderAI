import os
import psycopg2
from dotenv import load_dotenv
from flask import g

# Carica le variabili d'ambiente dal file .env
load_dotenv()

class DBManager:
    # Configurazione database PostgreSQL
    DB_USER = os.getenv('DB_USER', 'postgres')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = os.getenv('DB_PORT', '5432')
    DB_NAME = os.getenv('DB_NAME', 'stylefinderai')

    _status = {"connected": False, "error": "Not checked yet"}

    @staticmethod
    def initialize_db_connection():
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()

            DBManager._status = {
                "connected": True,
                "error": None
            }
        except Exception as e:
            DBManager._status = {
                "connected": False,
                "error": str(e)
            }
    
    @staticmethod
    def get_db_connection():
        """Crea e restituisce una connessione al database PostgreSQL"""

        if 'db' not in g:
            g.db = psycopg2.connect(
                host=DBManager.DB_HOST,
                port=DBManager.DB_PORT,
                database=DBManager.DB_NAME,
                user=DBManager.DB_USER,
                password=DBManager.DB_PASSWORD
            )

        return g.db

    @staticmethod
    def check_db_connection():
        return DBManager._status

    @staticmethod
    def close_db_connection(e=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()