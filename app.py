from flask import Flask
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

@app.route('/')
def index():
    return {'message': 'Welcome to StyleFinderAI API', 'status': 'running'}, 200

@app.route('/health')
def health():
    """Endpoint per verificare lo stato dell'applicazione e la connessione al database"""
    try:
        # Testa la connessione al database
        conn = Config.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.close()
        conn.close()
        return {'status': 'healthy', 'database': 'connected'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}, 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000)
