import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

from ai.src.model_fallback import generate_content_with_fallback, get_default_model

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")

# Create client once at module level
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=API_KEY)
    return _client

def generate_title(prompt: str) -> str:
    prompt_text = (
        f"Generate strictly ONE single title based on this prompt: '{prompt}'. "
        "The title must be short, concise and informative. "
        "Do not provide a list. Do not output intro text. Output ONLY the title."
    )

    try:
        client = _get_client()
        
        print("Sending request to Gemini (with fallback)...")

        config = types.GenerateContentConfig()
        
        response = generate_content_with_fallback(
            client=client,
            contents=prompt_text,
            config=config
        )

        return str(response.text)

    except Exception as e:
        print(f"Si è verificato un errore: {e}")
        raise e