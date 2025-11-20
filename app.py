from flask import Flask, request
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from db_manager import DBManager
import os

app = Flask(__name__)
app.config.from_object(DBManager)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.teardown_appcontext(DBManager.close_db_connection)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class AppUser(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict['id']
        self.email = user_dict['email']
        self._password_hash = user_dict.get('password')

    def get_id(self):  # type: ignore[override]
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    user = DBManager.get_user_by_id(int(user_id))
    if user:
        return AppUser(user)
    return None

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

        # Autentica tramite Flask-Login (sessione cookie based)
        login_user(AppUser(user))

        return {
            "success": True,
            "user": user_payload
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/logout', methods=['GET'])
def logout():
    """Endpoint per logout utente.

    Non richiede parametri (usa sessione Flask-Login).
    Risposte:
      - 401 se non autenticato
      - 200 se successo {success: true}
    """
    try:
        if not current_user.is_authenticated:
            return {"error": "Non autenticato"}, 401
        logout_user()
        
        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/session', methods=['GET'])
def check_session():
    """Verifica validità della sessione Flask-Login.

    Non richiede parametri (usa cookie di sessione).
    Risposte:
      - 401 se sessione non valida
      - 200 se valido {success: true, user: {...}}
    """
    try:
        if not current_user.is_authenticated:
            return {"error": "Sessione non valida"}, 401
        # Recupero completo utente dal DB se servono preferenze
        user_db = DBManager.get_user_by_id(int(current_user.get_id()))
        preferences = DBManager.get_user_preferences(user_db['id']) if user_db else []
        user_payload = {"id": user_db['id'], "email": user_db['email'], "preferences": preferences} if user_db else {}
        return {"success": True, "user": user_payload}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/update', methods=['POST'])
def update_user_credentials():
    """Aggiorna email e/o password dell'utente autenticato.

    Body JSON: {"email": "nuovaEmail"?, "password": "nuovaPassword"?}
    Almeno uno tra email o password deve essere presente.
    Usa current_user per identificare l'utente.
    Errori:
      - 401 se non autenticato
      - 400 se nessun campo da aggiornare
      - 404 utente non trovato
    Successo: {success: true}
    """
    try:
        if not current_user.is_authenticated:
            return {"error": "Non autenticato"}, 401

        data = request.get_json() or {}
        new_email = data.get('email')
        new_password = data.get('password')

        if not new_email and not new_password:
            return {"error": "Nessun campo da aggiornare"}, 400

        password_hash = None
        if new_password:
            password_hash = generate_password_hash(new_password)

        user_id = int(current_user.get_id())
        updated = DBManager.update_user_credentials(user_id, new_email=new_email, new_password_hash=password_hash)

        if not updated:
            return {"error": "Utente non trovato"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == '__main__':
    # Avvia l'app Flask
    app.run(host='0.0.0.0', port=8000, debug=True)