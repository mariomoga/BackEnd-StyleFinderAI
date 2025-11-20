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

    @staticmethod
    def email_exists(email: str) -> bool:
        """Controlla se un'email esiste nella tabella `users`."""
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM users WHERE email = %s LIMIT 1", (email,))
            exists = cursor.fetchone() is not None
            cursor.close()
            return exists
        except Exception:
            # In caso di errore, rilancia per far gestire l'errore a chi chiama
            raise

    @staticmethod
    def create_user(email: str, password_hash: str):
        """Crea un nuovo utente nella tabella `users`.

        Nota: la tabella `users` deve avere almeno le colonne `email` e `password`.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (email, password) VALUES (%s, %s)",
                (email, password_hash)
            )
            conn.commit()
            cursor.close()
        except Exception:
            # Rollback in caso di errore e rilancia
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    @staticmethod
    def get_user_by_email(email: str):
        """Recupera utente dalla tabella `users` per email.

        Ritorna dict {id, email, password} oppure None.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, email, password FROM users WHERE email = %s LIMIT 1",
                (email,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {"id": row[0], "email": row[1], "password": row[2]}
            return None
        except Exception:
            raise

    @staticmethod
    def get_user_preferences(user_id: int):
        """Recupera le preferenze dell'utente dalla tabella `user_prova_preferences`.

        Ritorna lista di dict con chiavi: favorite_color, favorite_brand, favorite_material, gender.
        """
        ###### DA FARE ########
        
        return []



    @staticmethod
    def update_user_credentials(user_id: int, new_email: str = None, new_password_hash: str = None) -> bool:
        """Aggiorna email e/o password dell'utente.

        Si aspetta che la validazione dei campi da aggiornare sia fatta a livello di route.
        Ritorna True se almeno una riga è stata aggiornata, False se nessuna (utente non trovato).
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            fields = []
            params = []
            if new_email is not None:
                fields.append("email = %s")
                params.append(new_email)
            if new_password_hash is not None:
                fields.append("password = %s")
                params.append(new_password_hash)

            # Assumiamo che almeno un campo sia presente (validato dalla route)
            params.append(user_id)
            query = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
            cursor.execute(query, tuple(params))
            updated = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return updated
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise

    @staticmethod
    def get_user_by_id(user_id: int):
        """Recupera utente per id. Ritorna dict {id,email,password} oppure None.

        Necessario per Flask-Login user_loader.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, email, password FROM users WHERE id = %s LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {"id": row[0], "email": row[1], "password": row[2]}
            return None
        except Exception:
            raise