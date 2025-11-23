import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"

def generate_title(prompt: str) -> str:
    prompt_text = (
        f"Generate strictly ONE single title based on this prompt: '{prompt}'. "
        "The title must be short, concise and informative. "
        "Do not provide a list. Do not output intro text. Output ONLY the title."
    )

    try:
        print(f"Loading model: {MODEL_NAME}...")

        model = genai.GenerativeModel(MODEL_NAME)

        print("Sending request to Gemini...")

        response = model.generate_content(prompt_text)

        return str(response.text)

    except Exception as e:
        print(f"Si è verificato un errore: {e}")
        raise e