import os
import psycopg2
from dotenv import load_dotenv
from flask import g
from psycopg2 import extras
from flask_login import current_user

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
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM users WHERE email = %s LIMIT 1", (email,))
                exists = cursor.fetchone() is not None

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
            conn.rollback()
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
    def get_user_preferences(user_id: int) -> dict:
        """Recupera le preferenze dell'utente.

        Esegue una query su user_preference e preference table.
        Ritorna un dict es: {'favorite_color': 'Red', 'gender': 'M'}
        """

        query = """
                SELECT p.name, up.value
                FROM users u
                         INNER JOIN user_preference up ON u.id = up.user_id
                         INNER JOIN preferences p ON up.preference_id = p.id
                WHERE u.id = %s
                """

        preferences = {}

        try:
            conn = DBManager.get_db_connection()

            with conn.cursor() as cursor:
                cursor.execute(query, (user_id,))

                rows = cursor.fetchall()

                preferences = {row[0]: row[1] for row in rows}

        except Exception as e:
            print(f"Errore nel recupero preferenze per user {user_id}: {e}")

        return preferences


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
    def update_user_preferences(user_id: int, new_preferences: dict) -> bool:
        values_list = [(user_id, k, str(v)) for k, v in new_preferences.items()]

        query = """
                INSERT INTO user_preference (user_id, preference_id, value)
                SELECT data.uid, p.id, data.p_val
                FROM (VALUES %s) AS data (uid, p_name, p_val)
                         JOIN preferences p ON p.name = data.p_name
                ON CONFLICT (user_id, preference_id)
                    DO UPDATE SET value = EXCLUDED.value \
                """

        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            psycopg2.extras.execute_values(
                cursor,
                query,
                values_list,
                template=None,
                page_size=100
            )

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()

            print(f"Errore batch update per user {user_id}: {e}")
            return False
        finally:
            cursor.close()

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


    @staticmethod
    def get_user_conversations(user_id: int):
        """Recupera tutte le conversazioni di un utente.

        Ritorna lista di dict con le conversazioni dell'utente.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, title, created_at FROM conversations WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,)
            )
            rows = cursor.fetchall()
            cursor.close()
            conversations = []
            for row in rows:
                conversations.append({
                    "id": row[0],
                    "title": row[1],
                    "created_at": row[2].isoformat() if row[2] else None
                })
            return conversations
        except Exception:
            raise


    @staticmethod
    def create_conversation_with_message(user_id: int, title: str, message_text: str):
        """
        Crea una nuova conversazione per un utente e inserisce il primo messaggio.

        Ritorna l'id della conversazione creata.
        """
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO conversations (user_id, title) VALUES (%s, %s) RETURNING id",
                (user_id, title)
            )
            conversation_id = cursor.fetchone()[0]

            cursor.execute(
                "INSERT INTO messages (conversation_id, text) VALUES (%s, %s)",
                (conversation_id, message_text)
            )

            conn.commit()
            cursor.close()

            return conversation_id

        except Exception as e:
            # Se qualcosa va storto (es. errore nel messaggio), annulla TUTTO (rollback)
            if conn:
                conn.rollback()
            # È buona norma loggare o stampare l'errore per capire cosa è successo
            print(f"Errore durante la creazione della conversazione: {e}")
            return None

    from flask_login import current_user

    @staticmethod
    def add_message_to_conversation(conversation_id: int, text: str):
        """
        Aggiunge un messaggio a una conversazione esistente, ma solo se
        la conversazione appartiene all'utente corrente.

        Ritorna True se l'operazione ha successo, False altrimenti (o se non autorizzato).
        """
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            # Cerchiamo se esiste una conversazione con questo ID E questo user_id
            cursor.execute(
                "SELECT id FROM conversations WHERE id = %s AND user_id = %s",
                (conversation_id, current_user.id)
            )

            # Se l utente vuole mandare un messaggio in una conversazione inesistente o non sua --> errore
            if cursor.fetchone() is None:
                print(f"Tentativo non autorizzato: L'utente {current_user.id} ha provato a scrivere nella chat {conversation_id}")
                # Non facciamo rollback perché non abbiamo scritto nulla, chiudiamo solo.
                cursor.close()
                return False

            # Altrimenti tutto bene!!
            cursor.execute(
                "INSERT INTO messages (conversation_id, text) VALUES (%s, %s)",
                (conversation_id, text)
            )

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            if conn:
                conn.rollback()
            print(f"Errore durante l'inserimento del messaggio: {e}")
            return False

    @staticmethod
    def delete_conversation(user_id: int, conversation_id: int) -> bool:
        """Elimina una conversazione dell'utente.

        Ritorna True se eliminata, False se non trovata o non appartiene all'utente.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                (conversation_id, user_id)
            )
            deleted = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return deleted
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def rename_conversation(user_id: int, conversation_id: int, new_title: str) -> bool:
        """Rinomina il titolo di una conversazione dell'utente.

        Ritorna True se aggiornata, False se non trovata o non appartiene all'utente.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE conversations SET title = %s WHERE id = %s AND user_id = %s",
                (new_title, conversation_id, user_id)
            )
            updated = cursor.rowcount > 0
            conn.commit()
            cursor.close()
            return updated
        except Exception:
            conn.rollback()
            raise