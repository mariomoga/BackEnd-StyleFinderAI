import os
import psycopg2
from dotenv import load_dotenv
from flask import g
from psycopg2 import extras
from flask_login import current_user
from psycopg2.extras import RealDictCursor

from storage_manager import delete_images, get_image_url

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
    def get_raw_connection():
        """Crea e restituisce una (nuova) connessione al database PostgreSQL """

        return psycopg2.connect(
            host=DBManager.DB_HOST,
            port=DBManager.DB_PORT,
            database=DBManager.DB_NAME,
            user=DBManager.DB_USER,
            password=DBManager.DB_PASSWORD
        )

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
    def create_user(name: str, email: str, password_hash: str):
        """Crea un nuovo utente nella tabella `users`.

        Nota: la tabella `users` deve avere almeno le colonne `email` e `password`.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                (name, email, password_hash)
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
                "SELECT id, name, email, password, gender FROM users WHERE email = %s LIMIT 1",
                (email,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {"id": row[0], "name" : row[1], "email": row[2], "password": row[3], "gender": row[4]}
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
    def update_user_name(user_id: int, new_name: str) -> bool:
        """Aggiorna il nome dell'utente."""
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET name = %s WHERE id = %s", (new_name, user_id))
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
        gender = new_preferences.get("gender")
        del new_preferences["gender"]

        # Prepariamo i dati come prima
        values_list = [(user_id, k, str(v)) for k, v in new_preferences.items()]

        # Query 1: Cancellazione totale delle preferenze dell'utente
        delete_query = "DELETE FROM user_preference WHERE user_id = %s"

        # Query 2: Inserimento massivo (senza ON CONFLICT, dato che abbiamo pulito)
        # Manteniamo la JOIN per risolvere il preference_id dal nome
        insert_query = """
                       INSERT INTO user_preference (user_id, preference_id, value)
                       SELECT data.uid, p.id, data.p_val
                       FROM (VALUES %s) AS data (uid, p_name, p_val)
                                JOIN preferences p ON p.name = data.p_name \
                       """

        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            # 1. Eseguiamo la DELETE
            cursor.execute(delete_query, (user_id,))

            # 2. Eseguiamo la INSERT solo se ci sono nuove preferenze da inserire
            if values_list:
                psycopg2.extras.execute_values(
                    cursor,
                    insert_query,
                    values_list,
                    template=None,
                    page_size=100
                )

            if gender:
                cursor.execute("UPDATE users SET gender = %s WHERE id = %s", (gender, user_id))

            conn.commit()
            cursor.close()
            return True

        except Exception as e:
            if conn:
                conn.rollback()

            print(f"Errore replace preferences per user {user_id}: {e}")
            return False

    @staticmethod
    def get_user_by_id(user_id: int):
        """Recupera utente per id. Ritorna dict {id,email,password} oppure None.

        Necessario per Flask-Login user_loader.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, email, password, gender FROM users WHERE id = %s LIMIT 1",
                (user_id,)
            )
            row = cursor.fetchone()
            cursor.close()
            if row:
                return {"id": row[0], "name": row[1], "email": row[2], "password": row[3], "gender": row[4]}
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
                    "created_at": row[2]
                })
            return conversations
        except Exception:
            raise

    @staticmethod
    def get_chat_messages(user_id, conversation_id)->list[dict]:
        """
        Recupera la cronologia chat. Per i messaggi dell'AI, ricostruisce l'array 'outfit'
        con i dettagli completi (titolo, prezzo, immagine, ecc.) prendendoli dalla tabella product_data.
        """
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            query = """
                    WITH chat_history AS (
                        -- 1. MESSAGGI UTENTE (Prompts)
                        SELECT
                            p.id AS message_id,
                            p.prompt AS text,
                            NULL AS explanation,
                            'user' AS role,
                            p.created_at,
                            '[]'::json AS outfit, -- L'utente non ha outfit
                            p.image_id,
                            NULL as status
                        FROM prompts p
                                 JOIN conversations c ON p.conversation_id = c.id
                        WHERE p.conversation_id = %s AND c.user_id = %s

                        UNION ALL

                        -- 2. MESSAGGI AI (AI Responses)
                        SELECT
                            ar.id AS message_id,
                            ar.short_message AS text,
                            ar.explanation AS explanation,
                            'model' AS role,
                            ar.created_at,
                            COALESCE(
                                    (
                                        SELECT json_agg(
                                                       json_build_object(
                                                               'id', pd.id,
                                                               'title', pd.title,
                                                               'url', pd.url,
                                                               'price', pd.price,
                                                               'image_link', pd.image_link,
                                                               'brand', pd.brand,
                                                               'material', pd.material
                                                       )
                                               )
                                        FROM outfit_suggestion os
                                                 JOIN product_data pd ON os.product_id = pd.id
                                        WHERE os.ai_response_id = ar.id
                                    ),
                                    '[]'::json
                            ) AS outfit,
                            NULL AS image_id,
                            ar.status as status
                        FROM ai_responses ar
                                 JOIN conversations c ON ar.conversation_id = c.id
                        WHERE ar.conversation_id = %s AND c.user_id = %s
                    )

                    -- 3. ORDINAMENTO FINALE
                    SELECT * FROM chat_history
                    ORDER BY created_at; \
                    """

            # Eseguiamo la query passando i parametri per entrambe le parti della UNION
            cursor.execute(query, (conversation_id, user_id, conversation_id, user_id))

            results = cursor.fetchall()
            cursor.close()

            for message in results:
                if message.get("role") == "user":
                    del message['explanation'], message['outfit']
                    if message['image_id']:
                        file_path = f"public/{message['image_id']}.jpg"
                        message['image_id'] = get_image_url(file_path)

                if message.get("role") == "ai":
                    del message['image_id']

            return results

        except Exception as e:
            print(f"Errore recupero chat: {e}")
            return []

    @staticmethod
    def create_conversation_with_message(user_id: int, title: str, message_text: str, image_id = None):
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
                "INSERT INTO prompts (conversation_id, prompt, image_id) VALUES (%s, %s, %s)",
                (conversation_id, message_text, image_id)
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

    @staticmethod
    def add_ai_response(conversation_id, response_data):
        """
        Salva la risposta dell'AI e i suggerimenti di outfit nel database.

        Args:
            conversation_id (int): L'ID della conversazione.
            response_data (dict): Il dizionario contenente i dati della risposta (formato JSON).
        """
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            # 1. Estrai i dati dal dizionario
            short_message = response_data.get('message')
            explanation = response_data.get('explanation')
            outfit_items = response_data.get('outfit', [])
            if not short_message or not explanation or len(outfit_items) == 0:
                print(f"Empty values passed:\n {short_message}\n, {explanation}\n, {outfit_items}\n")
                return -1

            # 2. Inserisci la risposta nella tabella ai_responses
            # Usiamo RETURNING id per ottenere l'ID generato auto-increment
            insert_response_query = """
                                    INSERT INTO ai_responses (conversation_id, short_message, explanation, status)
                                    VALUES (%s, %s, %s, 'COMPLETED')
                                    RETURNING id; \
                                    """
            cursor.execute(insert_response_query, (conversation_id, short_message, explanation))
            new_ai_response_id = cursor.fetchone()[0]

            # 3. Gestisci i prodotti e i suggerimenti
            for item in outfit_items:
                product_id = item.get('id')

                if not product_id:
                    continue

                # 3a. Inserisci o aggiorna il prodotto nella tabella product_data
                # Assumiamo che la tabella product_data abbia le colonne: id, title, url, price, image_link, brand, material
                upsert_product_query = """
                    INSERT INTO product_data (id, title, url, price, image_link, brand, material)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        title = EXCLUDED.title,
                        url = EXCLUDED.url,
                        price = EXCLUDED.price,
                        image_link = EXCLUDED.image_link,
                        brand = EXCLUDED.brand,
                        material = EXCLUDED.material;
                """
                cursor.execute(upsert_product_query, (
                    product_id,
                    item.get('title'),
                    item.get('url'),
                    item.get('price'),
                    item.get('image_link'),
                    item.get('brand'),
                    item.get('material')
                ))

                # 3b. Inserisci il collegamento in outfit_suggestion
                insert_suggestion_query = """
                                          INSERT INTO outfit_suggestion (ai_response_id, product_id)
                                          VALUES (%s, %s); \
                                          """
                cursor.execute(insert_suggestion_query, (new_ai_response_id, product_id))

            # Conferma le modifiche (Commit)
            conn.commit()
            cursor.close()
            return new_ai_response_id

        except psycopg2.Error as e:
            if conn:
                conn.rollback() # Annulla tutto se c'è un errore
            print(f"Errore Database: {e}")
            raise e

    @staticmethod
    def add_simple_ai_response(conversation_id, message, status):
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            # 2. Inserisci la risposta nella tabella ai_responses
            # Usiamo RETURNING id per ottenere l'ID generato auto-increment
            insert_response_query = """
                                    INSERT INTO ai_responses (conversation_id, short_message, status)
                                    VALUES (%s, %s, %s)
                                    RETURNING id; \
                                    """
            cursor.execute(insert_response_query, (conversation_id, message, status))
            new_ai_response_id = cursor.fetchone()[0]

            # Conferma le modifiche (Commit)
            conn.commit()
            cursor.close()
            return new_ai_response_id

        except psycopg2.Error as e:
            if conn:
                conn.rollback() # Annulla tutto se c'è un errore
            print(f"Errore Database: {e}")
            raise e


    @staticmethod
    def add_message_to_conversation(conversation_id: int, text: str, image_id=None):
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
                "INSERT INTO prompts (conversation_id, prompt, image_id) VALUES (%s, %s, %s)",
                (conversation_id, text, image_id)
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
        """Elimina una conversazione dell'utente e le relative immagini dallo storage.

        Ritorna True se eliminata, False se non trovata o non appartiene all'utente.
        """
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT p.image_id
                FROM prompts p
                         JOIN conversations c ON p.conversation_id = c.id
                WHERE c.id = %s AND c.user_id = %s AND p.image_id IS NOT NULL
                """,
                (conversation_id, user_id)
            )

            images_to_delete = [str(row[0]) for row in cursor.fetchall()]

            if images_to_delete:
                delete_images(images_to_delete)

            cursor.execute(
                "DELETE FROM conversations WHERE id = %s AND user_id = %s",
                (conversation_id, user_id)
            )

            deleted = cursor.rowcount > 0
            conn.commit()
            cursor.close()

            return deleted

        except Exception as e:
            print(f"Errore durante la cancellazione della conversazione: {e}")
            if conn:
                conn.rollback()
            raise

    @staticmethod
    def delete_user(user_id: int) -> bool:
        """Elimina un utente e tutti i suoi dati associati.

        Ritorna True se eliminato, False se non trovato.
        """
        conn = None
        try:
            conn = DBManager.get_db_connection()
            cursor = conn.cursor()

            # 1. Recupera tutte le conversazioni per eliminare le immagini
            cursor.execute("SELECT id FROM conversations WHERE user_id = %s", (user_id,))
            conversation_ids = [row[0] for row in cursor.fetchall()]

            for conv_id in conversation_ids:
                # Riutilizziamo la logica di delete_conversation per pulire le immagini
                # Nota: questo è un po' inefficiente fare N query, ma sicuro per le immagini.
                # Possiamo ottimizzare se necessario, ma per ora va bene.
                # Tuttavia, delete_conversation committa la transazione, il che rompe l'atomicità qui.
                # Meglio reimplementare la logica di pulizia immagini qui o fare tutto in una query.
                
                # Recuperiamo immagini per questa conversazione
                cursor.execute(
                    """
                    SELECT p.image_id
                    FROM prompts p
                    WHERE p.conversation_id = %s AND p.image_id IS NOT NULL
                    """,
                    (conv_id,)
                )
                images = [str(row[0]) for row in cursor.fetchall()]
                if images:
                    delete_images(images)

            # 2. Elimina preferenze
            cursor.execute("DELETE FROM user_preference WHERE user_id = %s", (user_id,))

            # 3. Elimina conversazioni (cascade su prompts e ai_responses se configurato, 
            # ma per sicurezza facciamo delete esplicito o ci affidiamo al DB)
            # Assumiamo che il DB abbia ON DELETE CASCADE sulle foreign key.
            # Se non lo ha, dovremmo cancellare prompts e ai_responses prima.
            # Per ora proviamo a cancellare le conversazioni.
            cursor.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))

            # 4. Elimina utente
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            
            deleted = cursor.rowcount > 0
            conn.commit()
            cursor.close()

            return deleted

        except Exception as e:
            print(f"Errore durante l'eliminazione dell'utente {user_id}: {e}")
            if conn:
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

    @staticmethod
    def preferences():
        try:
            conn = DBManager.get_db_connection()
            # Usa un cursore dizionario se disponibile (es. psycopg2.extras.RealDictCursor)
            # altrimenti usa quello standard
            with conn.cursor() as cursor:

                # 1. Recupera le preferenze base
                cursor.execute("SELECT id, name FROM preferences")
                rows = cursor.fetchall()

                # 2. Struttura base uniforme per tutti gli elementi
                # Ogni elemento sarà un dizionario con "name" e "values" (anche se vuoto)
                preferences = {}
                for row in rows:
                    pref_id = row[0]
                    pref_name = row[1]
                    preferences[pref_id] = {
                        "name": pref_name,
                        "values": []
                    }

                for pref_id, pref_data in preferences.items():
                    match int(pref_id):
                        case 2: # Brand
                            cursor.execute("SELECT brand FROM product_data GROUP BY brand")
                            brands = [row[0] for row in cursor.fetchall()]
                            pref_data["values"] = brands

                        case 3: # Materiali
                            cursor.execute("SELECT name FROM materials")
                            materials = [row[0] for row in cursor.fetchall()]
                            pref_data["values"] = materials

                        case 4: # Genere
                            pref_data["values"] = ["male", "female", "non-binary"]

                return preferences

        except Exception as e:
            print(f"Errore durante il recupero delle preferenze: {e}")
            return {}