from google.genai import types, Client

SYSTEM_PROMPT = """
You are an expert fashion stylist AI. Your task is to receive a user's request alongside the retrieved outfit that matches said request, and provide a justification for said outfit.

The final output MUST be textual explaining in detail how the retrieved outfit is appropriate given the user's request.

Focus on destailing how every clothing item matches the request, also highlighting how the different clothing itmes match and are coherent with one another.
"""

def explain_selected_outfit(CLIENT: Client, MODEL_NAME: str, user_prompt: str, retrieved_outfit) -> str:
    """
    Sends the user prompt to Gemini and enforces the structured JSON output.
    Returns the raw parsed JSON dictionary.
    """
    try:
        
        user_request_block = (
            "*** USER REQUEST ***\n"
            f"{user_prompt}"
            "\n**************************\n"
        )
                
        retrieved_outfit_block = (
            "*** OUTFIT RETRIEVED ***\n"
            f"{retrieved_outfit}"
            "\n**************************\n"
        )

        full_prompt = user_request_block + retrieved_outfit_block
    
        config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT
        )
        
        response = CLIENT.models.generate_content(
            model=MODEL_NAME,
            contents=[full_prompt],
            config=config,
        )
        return response.text
    except Exception as e:
        return f"Error generating outfit explanation: {e}"