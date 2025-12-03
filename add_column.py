
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'stylefinderai')

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.autocommit = True
    cursor = conn.cursor()

    # Check if column exists
    cursor.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='outfit_suggestion' AND column_name='outfit_index';
    """)
    
    if cursor.fetchone():
        print("Column 'outfit_index' already exists.")
    else:
        print("Adding 'outfit_index' column...")
        cursor.execute("ALTER TABLE outfit_suggestion ADD COLUMN outfit_index INTEGER DEFAULT 0;")
        print("Column added successfully.")

    cursor.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}")
