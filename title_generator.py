import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("GEMINI_API_KEY")
# genai.configure(api_key=API_KEY) # Not needed with new Client

MODEL_NAME = "gemini-2.0-flash" # Updated model name as well to match others

def generate_title(prompt: str) -> str:
    prompt_text = (
        f"Generate strictly ONE single title based on this prompt: '{prompt}'. "
        "The title must be short, concise and informative. "
        "Do not provide a list. Do not output intro text. Output ONLY the title."
    )

    try:
        print(f"Loading model: {MODEL_NAME}...")

        client = genai.Client(api_key=API_KEY)

        print("Sending request to Gemini...")

        response = client.models.generate_content(
            model=MODEL_NAME, 
            contents=prompt_text
        )

        return str(response.text)

    except Exception as e:
        print(f"Si è verificato un errore: {e}")
        raise e