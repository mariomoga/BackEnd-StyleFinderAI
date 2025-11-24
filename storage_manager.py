from dotenv import load_dotenv
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

def upload_image(filename, image_file):
    file_path = f"public/{filename}"

    try:
        file_bytes = image_file.read()

        SUPABASE_CLIENT.storage.from_("images").upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": image_file.mimetype}
        )

        return get_image_url(file_path)

    except Exception as e:
        print(f"Errore upload Supabase: {e}")
        return None


def get_image_url(image_id: str) -> str:
    return SUPABASE_CLIENT.storage.from_("images").get_public_url(image_id)


def delete_images(images_id: list[str]):
    files = [f"public/{image_id}" for image_id in images_id]

    try:
        SUPABASE_CLIENT.storage.from_("images").remove(files)

        return True

    except Exception as e:
        print(f"Errore while deleting Supabase: {e}")
        return False
