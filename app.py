from flask import Flask, request
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timedelta
from db_manager import DBManager
app = Flask(__name__)
app.config.from_object(DBManager)
app.teardown_appcontext(DBManager.close_db_connection)

with app.app_context():
    DBManager.initialize_db_connection()
    db_status = DBManager.check_db_connection()

@app.route('/')
def index():
    """Homepage che mostra lo stato della connessione al database."""
    if db_status["connected"]:
        return {
            "message": "Welcome to StyleFinderAI API",
            "status": "running",
            "database": "connected"
        }, 200
    else:
        return {
            "message": "Welcome to StyleFinderAI API",
            "status": "running",
            "database": "disconnected",
            "error": db_status["error"]
        }, 500

@app.route('/test')
def test():
    """Ritorna il contenuto della tabella users_prova_preferences."""
    try:
        conn = DBManager.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users_prova_preferences")
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()

        data = [dict(zip(columns, row)) for row in results]

        return {"data": data}, 200

    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/user/', methods=['POST'])
def signup():
    """Endpoint per registrare un nuovo utente.

    Riceve JSON {"email", "password"}.
    Ritorna 400 se mancano dati, 409 se email esiste, 201 se creato.
    """
    try:
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return {"error": "Dati mancanti"}, 400

        # Controlla se l'email è già registrata
        if DBManager.email_exists(email):
            return {"error": "Email già esistente"}, 409

        # Hash della password e creazione utente
        hashed = generate_password_hash(password)
        DBManager.create_user(email, hashed)

        return {"success": True}, 201

    except Exception as e:
        return {"error": str(e)}, 500
    
@app.route('/api/user/login', methods=['POST'])
def login():
    """Endpoint per login utente.

    Riceve JSON con `email` e `password`.
    Risposte:
      - 404 se utente non trovato
      - 401 se password errata
      - 200 se successo con {success: true, user: {id,email, preferences:[...]}}
    """
    try:
        data = request.get_json() or {}
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return {"error": "Credenziali mancanti"}, 400

        user = DBManager.get_user_by_email(email)
        if not user:
            return {"error": "Utente non trovato"}, 404

        if not check_password_hash(user['password'], password):
            return {"error": "Credenziali non valide"}, 401

        preferences = DBManager.get_user_preferences(user['id'])
        user_payload = {"id": user['id'], "email": user['email'], "preferences": preferences}

        # Genera token di sessione senza scadenza e salva su DB
        session_token = str(uuid.uuid4())
        DBManager.set_session_token(user['id'], session_token, None)

        return {
            "success": True,
            "session_token": session_token,
            "user": user_payload
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/logout', methods=['POST'])
def logout():
    """Endpoint per logout utente.

    Body JSON richiesto: {"id": <user_id>}.
    Azzeramento del session_token. Risposte:
      - 400 se id mancante
      - 404 se utente non trovato
      - 200 se successo {success: true}
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('id')

        if user_id is None:
            return {"error": "ID utente mancante"}, 400

        updated = DBManager.clear_session_token(user_id)
        if not updated:
            return {"error": "Utente non trovato"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/session', methods=['POST'])
def check_session():
    """Verifica validità del session_token.

    Body JSON: {"session_token": "..."}
    Risposte:
      - 400 se token mancante
      - 404 se token non trovato
      - 200 se valido {success: true, user: {...}}
    """
    try:
        data = request.get_json() or {}
        token = data.get('session_token')

        if not token:
            return {"error": "Session token mancante"}, 400

        user = DBManager.get_user_by_session_token(token)
        if not user:
            return {"error": "Sessione non valida"}, 404

        preferences = DBManager.get_user_preferences(user['id'])
        user_payload = {"id": user['id'], "email": user['email'], "preferences": preferences}

        return {"success": True, "user": user_payload}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/update', methods=['POST'])
def update_user_credentials():
    """Aggiorna email e/o password dell'utente.

    Body JSON: {"id": <int>, "email": "nuovaEmail"?, "password": "nuovaPassword"?}
    Almeno uno tra email o password deve essere presente.
    Errori:
      - 400 dati mancanti / nessun campo
      - 404 utente non trovato
    Successo: {success: true}
    """
    try:
        data = request.get_json() or {}
        user_id = data.get('id')
        new_email = data.get('email')
        new_password = data.get('password')

        if user_id is None:
            return {"error": "ID utente mancante"}, 400
        if not new_email and not new_password:
            return {"error": "Nessun campo da aggiornare"}, 400

        password_hash = None
        if new_password:
            password_hash = generate_password_hash(new_password)

        updated = DBManager.update_user_credentials(user_id, new_email=new_email, new_password_hash=password_hash)

        if not updated:
            return {"error": "Utente non trovato"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == '__main__':
    # Avvia l'app Flask
    app.run(host='0.0.0.0', port=8000, debug=True)