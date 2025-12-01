import os
import base64

# --- Utility Functions ---

def encode_image_to_base64(image_path: str) -> tuple[str, str] | tuple[None, None]:
    """Encodes an image file into a Base64 string and determines its MIME type."""
    
    if not os.path.exists(image_path):
        print(f"Error: Image file not found at {image_path}")
        return None, None
        
    try:
        # Infer MIME type from file extension
        ext = os.path.splitext(image_path)[1].lower()
        if ext in ['.jpg', '.jpeg']:
            mime_type = 'image/jpeg'
        elif ext == '.png':
            mime_type = 'image/png'
        else:
            print(f"Warning: Unsupported image type '{ext}'. Using 'image/jpeg'.")
            mime_type = 'image/jpeg'

        with open(image_path, "rb") as image_file:
            # Read the binary data and encode it
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
            return encoded_string, mime_type
            
    except Exception as e:
        print(f"Error during image encoding: {e}")
        return None, None