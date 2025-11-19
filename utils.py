from config import Config

def check_db_connection():
    """Controlla la connessione al database all'avvio e salva il risultato in db_status."""
    db_status = {
        "connected": False,
        "error": None
    }

    try:
        conn = Config.get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        db_status["connected"] = True
        db_status["error"] = None
    except Exception as e:
        db_status["connected"] = False
        db_status["error"] = str(e)
    finally:
        return db_status