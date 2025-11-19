from flask import Flask
from config import Config
from utils import check_db_connection

db_status = check_db_connection()

app = Flask(__name__)
app.config.from_object(Config)

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
        conn = Config.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users_prova_preferences")
        results = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        cursor.close()
        conn.close()

        data = [dict(zip(columns, row)) for row in results]

        return {"data": data}, 200

    except Exception as e:
        return {"error": str(e)}, 500