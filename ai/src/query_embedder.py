# src/ai/query_embedder.py (Updated)

import torch
import numpy as np
from PIL import Image 

def get_text_embedding_vector(MODEL, PROC, DEVICE, text: str) -> np.ndarray:
    """
    Generates a single, normalized NumPy vector embedding for a text string,
    using a dummy image to satisfy the CLIP model's requirement.
    """
    # 1. Create a dummy image to prevent the "ValueError: You have to specify pixel_values"
    dummy_image = Image.new('RGB', (224, 224), color='white')
    
    # 2. Tokenize and process both the dummy image and the text
    # The processor handles images=[dummy_image] and text=[text]
    inputs = PROC(
        images=[dummy_image], 
        text=[text], 
        return_tensors="pt", 
        padding=True, 
        max_length=77, 
        truncation=True
    )
    
    with torch.no_grad():
        # Move inputs to device and get model output
        out = MODEL(**{k: v.to(DEVICE) for k, v in inputs.items()})
    
    # Normalize the text embedding
    txt_embed = out.text_embeds
    txt_embed = torch.nn.functional.normalize(txt_embed, dim=-1)
    
    # Convert to a NumPy array (1, 512) and return the 1D vector
    return txt_embed[0].cpu().numpy()

#ONLY USED FOR LOCAL AND TARGETED TESTING
if __name__ == '__main__':
    # Example usage
    test_text = "fitted black t-shirt"
    embedding = get_text_embedding_vector(test_text)
    print(f"Text Embedding shape: {embedding.shape}")