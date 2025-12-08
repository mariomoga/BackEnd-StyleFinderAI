import base64
import uuid
from urllib.parse import urlparse

from flask import Flask, request
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from db_manager import DBManager
import os
import title_generator

from ai.src.app import outfit_recommendation_handler, generate_explanation_only
from storage_manager import upload_image, compress_image, download_image
from cachetools import LRUCache

app = Flask(__name__)
app.config.from_object(DBManager)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
cache = LRUCache(maxsize=100)

# CORS configuration for frontend
CORS(app, 
     origins=[
         "http://localhost:5173", 
         "http://localhost:5174",
         "http://127.0.0.1:5173",
         "http://127.0.0.1:5174"
     ],
     supports_credentials=True,
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])

app.teardown_appcontext(DBManager.close_db_connection)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

not_auth_convs = {}

class AppUser(UserMixin):
    def __init__(self, user_dict):
        self.id = user_dict['id']
        self.email = user_dict['email']
        self._password_hash = user_dict.get('password')
        self.gender = user_dict.get('gender')

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


@app.route('/api/user/', methods=['POST'])
def signup():
    """Endpoint per registrare un nuovo utente.

    Riceve JSON {"email", "password"}.
    Ritorna 400 se mancano dati, 409 se email esiste, 201 se creato.
    """
    try:
        data = request.get_json() or {}
        email = data.get('email')
        name = data.get('name')
        password = data.get('password')

        if not email or not password:
            return {"error": "Dati mancanti"}, 400

        # Controlla se l'email è già registrata
        if DBManager.email_exists(email):
            return {"error": "Email già esistente"}, 409

        # Hash della password e creazione utente
        hashed = generate_password_hash(password)
        DBManager.create_user(name, email, hashed)

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

        if not user or not check_password_hash(user['password'], password):
            return {"error": "Email or password not valid"}, 401

        preferences = DBManager.get_user_preferences(user['id'])
        # Aggiungi gender dalle info utente (solo se presente)
        if user.get('gender'):
            preferences['gender'] = user['gender']
        user_payload = {"id": user['id'], "name": user['name'], "email": user['email'], "preferences": preferences}

        # Autentica tramite Flask-Login (sessione cookie based)
        login_user(AppUser(user))

        return {
            "success": True,
            "user": user_payload
        }, 200

    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/logout', methods=['GET'])
@login_required
def logout():
    """Endpoint per logout utente.

    Non richiede parametri (usa sessione Flask-Login).
    Risposte:
      - 401 se non autenticato
      - 200 se successo {success: true}
    """
    try:
        logout_user()
        
        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/session', methods=['GET'])
@login_required
def check_session():
    """Verifica validità della sessione Flask-Login.

    Non richiede parametri (usa cookie di sessione).
    Risposte:
      - 401 se sessione non valida
      - 200 se valido {success: true, user: {...}}
    """
    try:
        # Recupero completo utente dal DB se servono preferenze
        user_db = DBManager.get_user_by_id(int(current_user.get_id()))
        preferences = DBManager.get_user_preferences(user_db['id']) if user_db else {}
        # Aggiungi gender dalle info utente (è salvato nella tabella users, non in user_preference)
        if user_db and user_db.get('gender'):
            preferences['gender'] = user_db['gender']
        user_payload = {"id": user_db['id'], "name": user_db['name'], "email": user_db['email'], "preferences": preferences} if user_db else {}
        return {"success": True, "user": user_payload}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/update', methods=['POST'])
@login_required
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

@app.route('/api/user/delete', methods=['DELETE'])
@login_required
def delete_account():
    """Elimina l'account dell'utente autenticato.

    Non richiede parametri nel body (usa current_user).
    Risposte:
      - 401 se non autenticato
      - 200 con {success: true}
    """
    try:
        user_id = int(current_user.get_id())
        deleted = DBManager.delete_user(user_id)

        if not deleted:
            return {"error": "Utente non trovato"}, 404

        logout_user()
        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/change-password', methods=['POST'])
@login_required
def change_password():
    """
    Endpoint per cambiare la password.
    Richiede JSON: { "current_password": "...", "new_password": "..." }
    """
    try:
        data = request.get_json() or {}
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return {"error": "Password mancante"}, 400

        # Verifica la vecchia password
        user_db = DBManager.get_user_by_id(int(current_user.get_id()))
        if not user_db or not check_password_hash(user_db['password'], current_password):
            return {"error": "Password attuale non corretta"}, 401

        # Aggiorna con la nuova password
        new_hash = generate_password_hash(new_password)
        DBManager.update_user_credentials(int(current_user.get_id()), new_password_hash=new_hash)

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/user/profile', methods=['PUT'])
@login_required
def update_profile():
    """
    Endpoint per aggiornare il profilo (nome).
    Richiede JSON: { "name": "..." }
    Ritorna: { "success": true, "user": { id, name, email, preferences } }
    """
    try:
        data = request.get_json() or {}
        new_name = data.get('name')

        if not new_name:
            return {"error": "Nome mancante"}, 400

        user_id = int(current_user.get_id())
        updated = DBManager.update_user_name(user_id, new_name)

        if not updated:
            return {"error": "Utente non trovato"}, 404

        # Recupera l'utente aggiornato per restituirlo
        user_db = DBManager.get_user_by_id(user_id)
        if not user_db:
            return {"error": "Utente non trovato"}, 404

        preferences = DBManager.get_user_preferences(user_id)
        # Aggiungi gender dalle info utente
        if user_db.get('gender'):
            preferences['gender'] = user_db['gender']

        return {
            "success": True,
            "user": {
                "id": user_db['id'],
                "name": user_db['name'],
                "email": user_db['email'],
                "preferences": preferences
            }
        }, 200
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/preferences', methods=['PUT', 'POST'])
@login_required
def update_user_preferences():
    try:
        data = request.get_json() or {}

        user_id = int(current_user.get_id())
        updated = DBManager.update_user_preferences(user_id, data)

        if not updated:
            return {"error": "Utente non trovato"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500


@app.route('/api/conversations', methods=['GET'])
@login_required
def get_conversations():
    """Recupera tutte le conversazioni dell'utente autenticato.

    Non richiede parametri nel body (usa current_user).
    Risposte:
      - 401 se non autenticato
      - 200 con {success: true, conversations: [...]}
    """
    try:
        user_id = int(current_user.get_id())
        conversations = DBManager.get_user_conversations(user_id)

        return {"success": True, "conversations" : conversations}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/chat', methods=['GET', 'POST'])
@login_required
def get_messages():
    """Recupera tutte le conversazioni dell'utente autenticato.

    Non richiede parametri nel body (usa current_user).
    Risposte:
      - 401 se non autenticato
      - 200 con {success: true, conversations: [...]}
    """
    try:
        data = request.get_json() or {}

        user_id = int(current_user.get_id())
        chat_id = data.get('conv_id')

        messages = DBManager.get_chat_messages(user_id, chat_id)

        return messages, 200

    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/messages/send', methods=['POST', 'PUT'])
def send_message():
    is_authenticated = current_user.is_authenticated
    user_id = int(current_user.get_id()) if is_authenticated else None
    
    try:
        image = None
        selected_outfit_index = None
        guest_gender = None  # Gender for non-authenticated users
        
        if request.is_json:
            data = request.get_json() or {}
            print(f"DEBUG: JSON Request Data: {data}")
            msg_text = data.get('message')
            conv_id = data.get('conv_id')
            selected_outfit_index = data.get('selected_outfit_index')
            selected_message_id = data.get('selected_message_id') # Extract from JSON
            guest_gender = data.get('gender')  # Get gender from request body
        else:
            print(f"DEBUG: Form Request Data: {request.form}")
            msg_text = request.form.get('message')
            conv_id = request.form.get('conv_id')
            selected_outfit_index = request.form.get('selected_outfit_index')
            selected_message_id = request.form.get('selected_message_id') # Extract from FormData
            guest_gender = request.form.get('gender')  # Get gender from form data
            image_uploaded = request.files.get('image')
            if image_uploaded:
                image = compress_image(image_uploaded.read())

        # Convert selected_outfit_index to int if present
        if selected_outfit_index is not None:
            try:
                selected_outfit_index = int(selected_outfit_index)
            except ValueError:
                selected_outfit_index = None

        image_id = None
        image_url = None
        if image:
            image_id = str(uuid.uuid4())
            if is_authenticated:
                image_url = upload_image(image_id, image)
            else:
                # Per utenti non autenticati, creiamo un URL base64 temporaneo
                image_url = f"data:image/jpeg;base64,{base64.b64encode(image).decode('utf-8')}"

        image_data = None
        if image_id:
            image_data = (image_id, image)

        # === UTENTE NON AUTENTICATO ===
        if not is_authenticated:
            if not conv_id:
                # Prima chat: genera un ID temporaneo
                conv_id = f"temp_{uuid.uuid4()}"
                chat_history = []
                past_images = {}
                
                output = outfit_recommendation_handler(msg_text, chat_history, user_id, image_data=image_data, past_images=past_images, selected_outfit_index=selected_outfit_index, guest_gender=guest_gender)
                
                conv_title = output.get('conversation_title')
                if not conv_title:
                    conv_title = title_generator.generate_title(msg_text)
                
                # Salva in memoria (non nel DB)
                not_auth_convs[conv_id] = {
                    'chat_history': chat_history,
                    'past_images': past_images,
                    'title': conv_title,
                    'gender': guest_gender  # Save gender for the conversation
                }
            else:
                # Conversazione esistente in memoria
                conv_title = None
                if conv_id not in not_auth_convs:
                    return {"error": "Conversation not found"}, 404
                
                conv_data = not_auth_convs[conv_id]
                chat_history = conv_data['chat_history']
                past_images = conv_data['past_images']
                # Use saved gender from conversation if not provided in request
                saved_gender = conv_data.get('gender') or guest_gender
                
                output = outfit_recommendation_handler(msg_text, chat_history, user_id, image_data=image_data, past_images=past_images, selected_outfit_index=selected_outfit_index, guest_gender=saved_gender)
            
            # Aggiorna la history in memoria
            if image_id and image:
                past_images[image_id] = image

        # === UTENTE AUTENTICATO ===
        else:
            if not conv_id:
                # First chat: Call AI first to get title and response
                chat_history = []
                past_images = {}
                
                output = outfit_recommendation_handler(msg_text, chat_history, user_id, image_data=image_data, past_images=past_images, selected_outfit_index=selected_outfit_index)
                
                conv_title = output.get('conversation_title')
                if not conv_title:
                    conv_title = title_generator.generate_title(msg_text)

                conv_id = DBManager.create_conversation_with_message(user_id, conv_title, msg_text, image_id=image_id)
                if conv_id is None:
                    return {"error": "Error while creating a new conversation"}, 500

                cache[conv_id] = (chat_history, past_images)

            else:
                conv_title = None
                success = DBManager.add_message_to_conversation(conv_id, msg_text, image_id=image_id)
                if not success:
                    return {"error": "Unable to save the message (Not authorized or generic db error)"}, 403

                if conv_id in cache:
                    chat_history, past_images = cache[conv_id]
                else:
                    chat_history, past_images = load_messages(conv_id, user_id)
                    cache[conv_id] = (chat_history, past_images)

                output = outfit_recommendation_handler(msg_text, chat_history, user_id, image_data=image_data, past_images=past_images, selected_outfit_index=selected_outfit_index, selected_message_id=selected_message_id)

        status = output.get('status')
        if not status:
            raise Exception("Error while generating recommendations")

        if status == "AWAITING_INPUT" or status == "Guardrail":
            text = output.get("prompt_to_user", output.get("message"))
            if is_authenticated:
                DBManager.add_simple_ai_response(conv_id, text, status)
        elif status == "COMPLETED" or status == "READY_TO_GENERATE":
            text = output.get("message")
            if is_authenticated:
                new_ai_response_id = DBManager.add_ai_response(conv_id, output)
        elif status == "RESOURCE_EXHAUSTED":
            text = "Gemini resources exhausted"
        else:
            text = output.get("message")

        # Update chat history
        chat_history.append({'role': 'user', 'text': msg_text, 'image_id': image_id})
        
        ai_msg = {'role': 'model', 'text': text, 'outfits': output.get('outfits', []), 'outfit_plan': output.get('outfit_plan')}
        if is_authenticated and 'new_ai_response_id' in locals():
            ai_msg['message_id'] = new_ai_response_id
            
        chat_history.append(ai_msg)

        response = {
            "status" : status,
            "conv_id": conv_id,
            "img_url" : image_url,
            "content" : {
                "outfit" : output.get("outfit", []),
                "outfits" : output.get("outfits", []),
                "message" : text,
                "explanation": output.get("explanation"),
            },
            "message_id": new_ai_response_id if is_authenticated and 'new_ai_response_id' in locals() else None
        }
        if conv_title:
            response['conv_title'] = conv_title

        # Invalidate cache to force reload from DB on next request (ensures 'outfits' is fresh)
        cache.pop(conv_id, None)

        return response, 200

    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR in send_message: {str(e)}")
        print(traceback.format_exc())
        return {"error": str(e)}, 500

@app.route('/api/outfit/explain', methods=['POST'])
def explain_outfit():
    """
    Endpoint to generate an explanation for a specific outfit on demand.
    Expects JSON: { "user_prompt": "...", "outfit_data": [...] }
    Works for both authenticated users and guests.
    """
    try:
        data = request.get_json() or {}
        user_prompt = data.get('user_prompt')
        outfit_data = data.get('outfit_data')
        
        if not user_prompt or not outfit_data:
             return {"error": "Missing user_prompt or outfit_data"}, 400
             
        explanation = generate_explanation_only(user_prompt, outfit_data)
        
        return {"success": True, "explanation": explanation}, 200
        
    except Exception as e:
        return {"error": str(e)}, 500


def load_messages(conv_id, user_id):
    messages = DBManager.get_chat_messages(user_id, conv_id)
    messages.pop()  # because is the current prompt

    chat_history = []
    past_images = dict()

    for message in messages:
        simple_message = {
            "role": message.get("role"),
            "role": message.get("role"),
            "text": message.get("text"),
            "message_id": message.get("message_id")
        }

        if message.get("outfit"):
            simple_message["outfit"] = message["outfit"]
        
        if message.get("outfits"):
            simple_message["outfits"] = message["outfits"]

        raw_url = message.get("image_id")

        if message.get("role") == "user" and raw_url:
            try:
                parsed_path = urlparse(raw_url).path
                filename = os.path.basename(parsed_path)
                message_image_id = os.path.splitext(filename)[0]
                simple_message["image_id"] = message_image_id

                image_bytes = download_image(message_image_id)
                if image_bytes:
                    past_images[message_image_id] = image_bytes
                else:
                    print("Error while retrieving bytes from past images")

            except Exception as e:
                print(e)

        chat_history.append(simple_message)
    return chat_history, past_images


@app.route('/api/conversations/rename', methods=['PUT', 'POST'])
@login_required
def rename_conversation():
    """Rinomina una conversazione dell'utente autenticato.

    Body JSON: {"title": "Nuovo titolo"}
    Risposte:
      - 401 se non autenticato
      - 400 se manca il titolo
      - 404 se conversazione non trovata o non appartiene all'utente
      - 200 con {success: true}
    """
    try:
        data = request.get_json() or {}
        new_title = data.get('title')
        conversation_id = data.get("conv_id")

        if not new_title:
            return {"error": "Titolo mancante"}, 400

        user_id = int(current_user.get_id())
        updated = DBManager.rename_conversation(user_id, conversation_id, new_title)

        if not updated:
            return {"error": "Conversazione non trovata"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/conversations/delete', methods=['DELETE'])
@login_required
def delete_conversation():
    """Elimina una conversazione dell'utente autenticato.

    Risposte:
      - 401 se non autenticato
      - 404 se conversazione non trovata o non appartiene all'utente
      - 200 con {success: true}
    """
    try:
        data = request.get_json() or {}
        user_id = int(current_user.get_id())
        conversation_id = int(data.get("conv_id"))
        deleted = DBManager.delete_conversation(user_id, conversation_id)

        if not deleted:
            return {"error": "Conversazione non trovata"}, 404

        return {"success": True}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/conversations/delete-all', methods=['DELETE'])
@login_required
def delete_all_conversations():
    """Elimina tutte le conversazioni dell'utente autenticato.

    Risposte:
      - 401 se non autenticato
      - 200 con {success: true, deleted_count: N}
    """
    try:
        user_id = int(current_user.get_id())
        deleted_count = DBManager.delete_all_user_conversations(user_id)
        
        # Pulisce anche la cache per questo utente
        keys_to_remove = [key for key in cache.keys() if str(key).startswith(f"{user_id}_")]
        for key in keys_to_remove:
            cache.pop(key, None)

        return {"success": True, "deleted_count": deleted_count}, 200
    except Exception as e:
        return {"error": str(e)}, 500

@app.route('/api/preferences/all', methods=['GET'])
@login_required
def preferences_all():
    try:
        return DBManager.preferences()
    except Exception as e:
        return {"error": str(e)}, 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)