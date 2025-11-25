from dotenv import load_dotenv
from PIL import Image
import io
import os

from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_RLS_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Supabase credentials (SUPABASE_URL, SUPABASE_KEY) must be set in the environment or .env file.")

try:
    SUPABASE_CLIENT: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    raise

def upload_image(filename, image: bytes):
    file_path = f"public/{filename}.jpg"

    try:
        SUPABASE_CLIENT.storage.from_("images").upload(
            path=file_path,
            file=image,
            file_options={"content-type": "image/jpeg"}
        )

        return get_image_url(file_path)

    except Exception as e:
        print(f"Errore upload Supabase: {e}")
        return None


def get_image_url(image_id: str) -> str:
    return SUPABASE_CLIENT.storage.from_("images").get_public_url(image_id)


def delete_images(images_id: list[str]):
    files = [f"public/{image_id}.jpg" for image_id in images_id]

    try:
        SUPABASE_CLIENT.storage.from_("images").remove(files)

        return True

    except Exception as e:
        print(f"Errore while deleting Supabase: {e}")
        return False

def compress_image(image_bytes: bytes, quality: int = 80, max_size: tuple = None) -> bytes:
    """
    Comprime un'immagine, la ridimensiona (opzionale) e la converte in JPEG.

    Args:
        image_bytes (bytes): L'immagine originale in formato bytes.
        quality (int): La qualità della compressione JPEG (1-100). Default 85.
        max_size (tuple): Opzionale. Una tupla (larghezza, altezza) per il ridimensionamento massimo.
                          Mantiene l'aspect ratio. Esempio: (1920, 1080).

    Returns:
        bytes: L'immagine compressa e convertita in bytes.
    """
    try:
        img_stream = io.BytesIO(image_bytes)
        img = Image.open(img_stream)

        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output_stream = io.BytesIO()
        img.save(
            output_stream,
            format="JPEG",
            quality=quality,
            optimize=True
        )

        compressed_data = output_stream.getvalue()

        return compressed_data

    except Exception as e:
        # Logga l'errore o gestiscilo come preferisci nel contesto Flask
        print(f"Errore durante la compressione dell'immagine: {e}")
        raise e