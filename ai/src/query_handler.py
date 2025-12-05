import json
from google.genai import types, Client

# --- Schema Definitions ---

# Define the schema for an individual item (e.g., "shirt", "relaxed")
item_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "tag": types.Schema(type=types.Type.STRING, description="The descriptive item tag (e.g., shirt, sweater)."),
        "fit": types.Schema(type=types.Type.STRING, description="A description of the appropriate fit (e.g., relaxed, fitted).")
    },
    required=["tag", "fit"]
)

# Define the schema for a category (e.g., "top")
category_schema = types.Schema(
    type=types.Type.OBJECT,
    description="A collection of item suggestions for a specific clothing category. If accessory limit to sunglasses, caps/hats or simple jewelry.",
    properties={
        "color_palette": types.Schema(type=types.Type.STRING, description="A specific color or color description (e.g., 'sky blue', 'dark indigo')."),
        "pattern": types.Schema(type=types.Type.STRING, description="A specific pattern (e.g., 'solid', 'striped', 'gingham')."),
        "items": types.Schema(type=types.Type.ARRAY, items=item_schema, description="A list of specific items for this category.")
    },
    required=["color_palette", "pattern", "items"]
)

# Defines the structure for hard constraints applied to a single item category.
# (This was likely the original 'constraint_item_schema')
constraint_item_schema = types.Schema(
    type=types.Type.OBJECT,
    description="Any color, material, or brand constraints specified by the user for this category.",
    properties={
        "color": types.Schema(type=types.Type.STRING),
        "material": types.Schema(type=types.Type.STRING),
        "brand": types.Schema(type=types.Type.STRING),
    },
)

# Defines the primary schema for managing the conversational state
input_gathering_schema = types.Schema(
    type=types.Type.OBJECT,
    description="Schema used for multi-turn conversations to gather required information before generating the final outfit plan.",
    properties={
        "status": types.Schema(type=types.Type.STRING, description="The current status. Must be 'AWAITING_INPUT' if max_budget or sufficient hard_constraints are missing, or 'READY_TO_GENERATE' if all necessary inputs are gathered."),
        "missing_info": types.Schema(type=types.Type.STRING, description="A polite, conversational TEXTUAL message asking the user for the specific missing information (e.g., 'What is your maximum budget and what constraints do you have for the top?') This is the message presented to the user."),
        "max_budget": types.Schema(type=types.Type.NUMBER, description="The maximum budget (€) extracted from the conversation history so far. Must be 0 if not yet specified or ambiguous."),
        "hard_constraints": types.Schema(
            type=types.Type.OBJECT,
            description="All extracted hard constraints (color, material, brand) organized by category (top, bottom, shoes, etc.).",
            properties={
                "top": constraint_item_schema,
                "bottom": constraint_item_schema,
                "outerwear": constraint_item_schema,
                "shoes": constraint_item_schema,
                "accessories": constraint_item_schema,
            }
        ),
        "message": types.Schema(type=types.Type.STRING, description="field that must contain ONLY the error message if a guardrail condition triggers"),
        "message": types.Schema(type=types.Type.STRING, description="field that must contain ONLY the error message if a guardrail condition triggers"),
        "conversation_title": types.Schema(type=types.Type.STRING, description="A short, concise title for the conversation (max 5 words). Generate this ONLY if it is the first message in the conversation."),
        "num_outfits": types.Schema(type=types.Type.INTEGER, description="The number of outfit options the user wants to see (default 1, max 3). Extract this from the user's request."),
    },
    #required=["status", "missing_info", "max_budget", "hard_constraints"]
    required=["status"]
)

# 1. New Schema for ONLY the Outfit Categories (The nested 'outfit_plan')
outfit_categories_schema = types.Schema(
    type=types.Type.OBJECT,
    description="Contains the suggested clothing items and accessories, excluding metadata like budget and constraints.",
    properties={
        "top": category_schema,
        "bottom": category_schema,
        "dresses": category_schema,
        "outerwear": category_schema,
        "swimwear": category_schema,
        "shoes": category_schema,
        "accessories": category_schema,
    },
)

# 2. Revised Main Outfit Generation Schema (The LLM's full output)
# This schema separates the outfit plan, budget, and constraints at the top level.
outfit_schema = types.Schema(
    type=types.Type.OBJECT,
    properties={
        # The nested categories container
        "outfits": types.Schema(
            type=types.Type.ARRAY,
            items=outfit_categories_schema,
            description="A list of distinct outfit plans. Generate multiple if the user requested options."
        ),

        # Metadata fields at the top level
        "max_budget": types.Schema(
            type=types.Type.NUMBER,
            description="The maximum budget (€ or $) extracted from the conversation history. Must be 0 if not yet specified or ambiguous."
        ),
        "hard_constraints": types.Schema(
            type=types.Type.OBJECT,
            description="All extracted hard constraints organized by category.",
            properties={
                "top": constraint_item_schema,
                "bottom": constraint_item_schema,
                "outerwear": constraint_item_schema,
                "shoes": constraint_item_schema,
                "accessories": constraint_item_schema,
            }
        ),
        "changed_categories": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
            description="A list of category names (e.g., 'top', 'shoes') that the user explicitly asked to change or refine. Leave empty if this is a new request or a complete overhaul."
        ),
        "message": types.Schema(
            type=types.Type.STRING,
            description="A message for non-fashion related inquiries. MUST ONLY be present for guardrail messages."
        )
    },
    required=["outfits", "max_budget", "changed_categories"]
)

# --- 3. System Prompt and Guardrail ---
TEXTUAL_SYSTEM_PROMPT = """
You are an expert conversational fashion stylist AI. Your primary goal is to first gather all necessary information and then provide a structured outfit plan.

[STEP 1: INFORMATION GATHERING (Use InputGatheringSchema)]

Analyze the ENTIRE conversation history.

Analyze the ENTIRE conversation history.

If this is the FIRST message in the conversation, you MUST generate a 'conversation_title'. The title should be short, concise, and summarize the user's intent.

Determine if a 'max_budget' (a numerical or textual value in € or $) has been explicitly provided by the user. Hard constraints (brand, color, material) are OPTIONAL for generation.


If the user explicitly states that he/she does not care about a specific budget, set the 'max_budget' to 0, set the 'status' to 'READY_TO_GENERATE'

If the 'max_budget' is missing, set the 'status' to 'AWAITING_INPUT' and provide a specific, conversational question in the 'missing_info' field. The question MUST ask for the budget also providing a tight budget range (in €) coherent with the user's request. It should also politely ask if the user has any OPTIONAL hard constraints (if not already stated) AND if they would like to see multiple outfit options (e.g., "Would you like to see 1, 2, or 3 options?").

Make sure that, if the user's specifies any constraints, that they are applied ONLY TO THE SPECIFIED CLOTHING ITEMS.

Make sure that, if the user's specifies any constraints, that they are applied ONLY TO THE SPECIFIED CLOTHING ITEMS.

If the 'max_budget' is present, set the 'status' to 'READY_TO_GENERATE'.

[STEP 2: OUTFIT GENERATION (Use OutfitSchema)]
ONLY if the 'status' would be 'READY_TO_GENERATE', you MUST switch modes and generate the final outfit plan using the standard OutfitSchema. The final output MUST NOT contain the status/missing_info fields in this case. 
The final output MUST include the 'max_budget' (extracted from history) and 'hard_constraints' fields at the top level.
The final output should be a list of full outfits in the 'outfits' field. Each outfit should include at least 'top', 'bottom', 'shoes', also include 'outerwear' if it fits with the user's request.

[REFINE & MODIFY LOGIC]
If the user asks to change or refine a specific item in the previous outfit (e.g., 'change the shoes to red', 'I don't like the shirt'), you MUST:
1.  **Identify Changed Categories:** Populate the 'changed_categories' list. THIS IS CRITICAL.
    *   **REFINE/MODIFY:** If the user changes a specific item, list ONLY that category (e.g. `['shoes']`). **WARNING: If you do not list the category here, the system will LOCK the previous item and your change will be IGNORED.**
    *   **ADD ITEM/CHANGE BUDGET:** If the user ONLY adds a new item or changes the budget, leave `changed_categories` EMPTY `[]`.
    *   **NEW REQUEST/OVERHAUL:** If the user asks for a completely new outfit or different style, list **ALL** categories in `changed_categories` (e.g. `['top', 'bottom', 'shoes', 'accessories']`) to force a full regeneration.
2.  **Regenerate the FULL outfit plan.** Do NOT return only the single changed item unless the user explicitly asks to "show me ONLY shirts".
3.  **Preserve Context:** Keep the other items (top, bottom, etc.) consistent with the style and vibe of the previous outfit, unless the user asks to change them too.
4.  **Apply Change:** Apply the user's specific change (e.g., new color, new type) to the target item.

If the user requested multiple options (or 'num_outfits' > 1), generate that many DISTINCT outfit plans in the 'outfits' list. Ensure they are stylistically different if possible.
OTHERWISE, GENERATE EXACTLY 1 OUTFIT. Do not generate more than 1 unless explicitly asked.

If the user is asking for specific clothing items, you should include ONLY the clothing items requested by the user AND NOTHING ELSE. 

DO NOT INCLUDE MORE THAN 1 ITEM FOR EACH 'category_schema' UNLESS STRICTLY NECESSARY. This does not apply to 'accessories_schema'.

If constraints are missing, assume flexibility and generate a well-curated outfit that fits the occasion and budget. 

[CONSTRAINT EXTRACTION]

Extract all budget and hard constraints provided by the user in the history and populate the 'max_budget' and 'hard_constraints' fields, even if the status is 'AWAITING_INPUT'.
Do not make up constraints, just extract constraints if the user explicitly inputs them.

GUARDRAIL: If the user's request is offensive towards any ethnicity, contains hatespeech or is in any way offensive towards anybody, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I cannot fulfill this request. Content that promotes hate speech, discrimination, or is offensive toward any group or individual violates my safety policy and is strictly forbidden."}

GUARDRAIL: If the user's request is NOT related to fashion, outfits, styles, or clothing, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I'm here to help with fashion-related inquiries. Please ask me about outfits, styles, or clothing recommendations"}
"""


IMAGE_SYSTEM_PROMPT = """
You are an expert conversational fashion stylist AI. Your primary goal is to first gather all necessary information (Budget AND Intent) and then provide a structured outfit plan.

[STEP 1: INFORMATION GATHERING (Use InputGatheringSchema)]

Analyze the ENTIRE conversation history and the attached image.

If this is the FIRST message in the conversation, you MUST generate a 'conversation_title'. The title should be short, concise, and summarize the user's intent.

Determine if the following two pieces of information are explicitly present:
a. Determine if a 'max_budget' (a numerical or textual value in € or $) has been explicitly provided by the user. Hard constraints (brand, color, material) are OPTIONAL for generation.

If the user explicitly states that he/she does not care about a specific budget, set the 'max_budget' to 0.

b. The user's 'image_intent'.

If the 'max_budget' or the 'user's intent' is missing, set the 'status' to 'AWAITING_INPUT' and provide a specific, conversational question in the 'missing_info' field. The question MUST ask the missing piece of information, also providing a tight budget range (in €) coherent with the user's request if the budget is missing, and it should also politely ask if the user has any OPTIONAL hard constraints.

Make sure that, if the user's specifies any constraints, that they are applied ONLY TO THE SPECIFIED CLOTHING ITEMS.

If BOTH the 'max_budget' and the 'image_intent' are present, set the 'status' to 'READY_TO_GENERATE'.

[STEP 2: OUTFIT GENERATION (Use OutfitSchema)]
a. If the intent was to find matching items or complete the outfit shown, generate only the complementary items required to form a full, cohesive look.
b. If the intent was to find an outfit in the same style or aesthetic as the image, generate a full, coherent outfit that captures the overall fashion sense of the image.

ONLY if the 'status' would be 'READY_TO_GENERATE', you MUST switch modes and generate the final outfit plan using the standard OutfitSchema. The final output MUST NOT contain the status/missing_info fields in this case.
The final output MUST include the 'max_budget' (extracted from history) and 'hard_constraints' fields at the top level.
The final output should be a full outfit by default, including at least 'top', 'bottom', 'shoes', also include 'outerwear' if it fits with the user's request.

If the user requested multiple options (or 'num_outfits' > 1), generate that many DISTINCT outfit plans in the 'outfits' list. Ensure they are stylistically different if possible.
OTHERWISE, GENERATE EXACTLY 1 OUTFIT. Do not generate more than 1 unless explicitly asked.

[REFINE & MODIFY LOGIC]
If the user asks to change or refine a specific item in the previous outfit (e.g., 'change the shoes to red', 'I don't like the shirt'), you MUST:
1.  **Identify Changed Categories:** Populate the 'changed_categories' list.
    *   **REFINE/MODIFY:** If the user changes a specific item, list ONLY that category (e.g. `['shoes']`).
    *   **ADD ITEM/CHANGE BUDGET:** If the user ONLY adds a new item or changes the budget, leave `changed_categories` EMPTY `[]`.
    *   **NEW REQUEST/OVERHAUL:** If the user asks for a completely new outfit or different style, list **ALL** categories in `changed_categories` (e.g. `['top', 'bottom', 'shoes', 'accessories']`) to force a full regeneration.
2.  **Regenerate the FULL outfit plan.** Do NOT return only the single changed item unless the user explicitly asks to "show me ONLY shirts".
3.  **Preserve Context:** Keep the other items (top, bottom, etc.) consistent with the style and vibe of the previous outfit, unless the user asks to change them too.
4.  **Apply Change:** Apply the user's specific change (e.g., new color, new type) to the target item.

If the user is asking for specific clothing items, you should include ONLY the clothing items requested by the user AND NOTHING ELSE. 

DO NOT INCLUDE MORE THAN 1 ITEM FOR EACH 'category_schema' UNLESS STRICTLY NECESSARY.

If constraints are missing, assume flexibility and generate a well-curated outfit that fits the occasion and budget. 


[CONSTRAINT EXTRACTION]

Extract all budget and hard constraints provided by the user in the history. If the user explicitly asks for an item with a feature that matches the image (e.g., "same color"), you MUST analyze the image to determine the feature's value and use that specific, descriptive value in the 'description' field, NOT in the 'hard_constraints' field. DO NOT use literal phrases like "same as in the picture."

GUARDRAIL: If the user's request is offensive towards any ethnicity, contains hatespeech or is in any way offensive towards anybody, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I cannot fulfill this request. Content that promotes hate speech, discrimination, or is offensive toward any group or individual violates my safety policy and is strictly forbidden."}

GUARDRAIL: If the user's request is NOT related to fashion, outfits, styles, or clothing, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I'm here to help with fashion-related inquiries. Please ask me about outfits, styles, or clothing recommendations"}

The final output MUST be a single JSON object and nothing else.
\n*** CRITICAL INSTRUCTION \n
the field 'message' MUST BE PRESENT ONLY if a guardrail triggers.
\n***********************
"""

FASHION_CATEGORIES = ['top', 'bottom', 'dresses', 'outerwear', 'swimwear', 'shoes', 'accessories']

import json
from google.genai import types, Client

# ... [MANTIENI I TUOI SCHEMI DEFINITI SOPRA: item_schema, category_schema, ecc...] ...
# ... [MANTIENI I SYSTEM PROMPT: TEXTUAL_SYSTEM_PROMPT, IMAGE_SYSTEM_PROMPT] ...

FASHION_CATEGORIES = ['top', 'bottom', 'dresses', 'outerwear', 'swimwear', 'shoes', 'accessories']

# def _reconstruct_gemini_history(simple_history: list[dict]) -> list[dict]:
#     """
#     Helper function che trasforma la storia 'semplice' dal DB
#     nel formato complesso richiesto dall'SDK di Gemini.
#     """
#     gemini_history = []
#     for msg in simple_history:
#         # Ricostruiamo l'oggetto types.Part per ogni messaggio testuale salvato
#         gemini_history.append({
#             "role": msg["role"],
#             "parts": [types.Part(text=create_text_prompt(msg["text"]))]
#         })
#     return gemini_history

def generate_outfit_plan(
        client: Client,
        model_name: str,
        new_user_query: str,
        chat_history: list[dict],
        image_data: tuple[str, bytes] | None,
        past_images: dict[str, bytes] | None,
        user_preferences: dict | None,
        gender: str | None
) -> dict:
    if gender is None:
        gender = "male"

    if past_images is None:
        past_images = {}

    # --- 1. RICOSTRUZIONE STORIA PER API (Solo Testo Grezzo) ---
    gemini_history = []

    for msg in chat_history:
        message_parts = [types.Part(text=msg["text"])]
        if msg.get("role") == "user" and "image_id" in msg:
            img_id = msg["image_id"]
            if img_id in past_images:
                img_bytes = past_images[img_id]
                message_parts.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            else:
                print(f"Warning: Bytes for image {img_id} not found in past_images.")

        gemini_history.append({
            "role": msg["role"],
            "parts": message_parts
        })

    full_text_prompt = create_text_prompt(gender, new_user_query, user_preferences)

    current_turn_parts = [types.Part(text=full_text_prompt)]

    # Part B: Immagine (se presente)
    if image_data:
        try:
            img_part = types.Part.from_bytes(
                data=image_data[1],
                mime_type="image/jpeg"
            )
            current_turn_parts.append(img_part)
        except Exception as e:
            print(f"Error packing image data: {e}")

    # Aggiungiamo il turno corrente alla storia PER L'API
    gemini_history.append({"role": "user", "parts": current_turn_parts})

    # --- 3. AGGIORNAMENTO STORIA SEMPLICE (PER DB) ---
    # Salviamo solo il prompt puro dell'utente, senza il blocco preferenze/gender
    chat_history.append({"role": "user", "text": new_user_query, "image_id" : image_data[0] if image_data else None})

    has_images = image_data is not None or (past_images is not None and len(past_images) > 0)
    base_prompt = IMAGE_SYSTEM_PROMPT if has_images else TEXTUAL_SYSTEM_PROMPT

    # --- 4. CHIAMATA API ---
    try:
        response = client.models.generate_content(
            model = model_name,
            contents = gemini_history,
            config = types.GenerateContentConfig(
                system_instruction = base_prompt,
                response_mime_type = "application/json",
                response_schema = input_gathering_schema,
                temperature = 1.5
            )
        )
        dialogue_state = response.parsed

    except Exception as e:
        print(f"Error during dialogue state check: {e}")
        return {'error': 'Failed to process dialogue state.'}

    # ... [IL RESTO DEL CODICE RIMANE UGUALE] ...

    # --- GESTIONE RISPOSTA ---
    if dialogue_state.get('status') == 'AWAITING_INPUT':
        chat_history.append({"role": "model", "text": dialogue_state['missing_info']})
        return {
            'status': 'AWAITING_INPUT',
            'prompt_to_user': dialogue_state['missing_info'],
            'history': chat_history,
            'conversation_title': dialogue_state.get('conversation_title')
        }

    elif dialogue_state.get('status') == 'READY_TO_GENERATE':
        # Prompt tecnico
        final_generation_prompt = gemini_history + [{
            "role": "user",
            "parts": [{"text": "All constraints are now provided. Please generate the final, complete outfit plan immediately using the OutfitSchema."}]
        }]

        try:
            final_response = client.models.generate_content(
                model = model_name,
                contents = final_generation_prompt,
                config = types.GenerateContentConfig(
                    system_instruction = base_prompt,
                    response_mime_type = "application/json",
                    response_schema = outfit_schema,
                    temperature = 1.5   
                )
            )
            final_data = final_response.parsed

            final_plan_text = json.dumps(final_data.get('outfits'))
            chat_history.append({"role": "model", "text": final_plan_text})

            return {
                'status': 'READY_TO_GENERATE',
                'outfits': final_data.get('outfits'),
                'budget': final_data.get('max_budget'),
                'hard_constraints': final_data.get('hard_constraints'),
                'changed_categories': final_data.get('changed_categories', []),
                'history': chat_history,
                'conversation_title': dialogue_state.get('conversation_title')
            }
        except Exception as e:
            print(e)
            pass

    else:
        if dialogue_state.get('message'):
            chat_history.append({"role": "model", "text": dialogue_state['message']})
        return dialogue_state


def create_text_prompt(gender: str, new_user_query: str, user_preferences: dict | None) -> str:
    user_request_block = (
        "*** USER REQUEST ***\n"
        f"{new_user_query}"
        "\n**************************\n"
    )

    preference_string = ""
    if user_preferences or gender:
        preferences = []
        if user_preferences and user_preferences.get('favorite_color'):
            preferences.append(f"favorite color: {user_preferences['favorite_color']}")
        if user_preferences and user_preferences.get('favorite_material'):
            preferences.append(f"favorite material: {user_preferences['favorite_material']}")
        if user_preferences and user_preferences.get('favorite_brand'):
            preferences.append(f"favorite brand: {user_preferences['favorite_brand']}")

        gender_block = ""
        if gender:
            gender_block = (
                "\n*** USER GENDER ***\n"
                f"When selecting the outfit plan, note that the gender of the user is: {gender}.\n"
            )

        if preferences:
            preference_string = (
                    gender_block +
                    "\n*** USER PREFERENCES (SOFT SUGGESTIONS) ***\n"
                    f"When selecting the outfit plan, keep the following user preferences in mind: {', '.join(preferences)}."
                    "\n*** CRITICAL INSTRUCTION: STYLISH INTEGRATION ***\n"
                    "Treat all provided user preferences (color, material, brand) as strong suggestions to be **integrated tastefully** into the final ensemble, not as mandatory rules for every single item. Style and outfit cohesion are paramount."
                    "Specifically:\n"
                    "1. **Color:** **DO NOT** enforce the favorite color on *every* item. Use it sparingly to create a cohesive, balanced look.\n"
                    "2. **Material/Brand:** **DO NOT** enforce the preferred material or brand on *every* item.\n"
                    "Ensure all returned descriptions are **coherent** and make up a **well-structured, complete outfit**."
                    "\n**************************"
            )
        else:
            preference_string = gender_block

    full_text_prompt = str(user_request_block + preference_string)
    return full_text_prompt


def parse_outfit_plan(json_plan: dict, hard_constraints: dict | None) -> list[dict]:
    """
    Transforms the structured JSON plan (output of the LLM) into a simplified 
    list of item descriptions for the Embedding Component, merging in the 
    database hard constraints.
    """
    
    # Check if a fashion plan was successfully generated 
    has_fashion_categories = any(key in json_plan for key in FASHION_CATEGORIES)
    
    # Scenario 1: Guardrail fired correctly (only 'message' key present)
    if 'message' in json_plan and not has_fashion_categories:
        return [json_plan] 
    
    response_list = []
    
    # Iterate through each clothing category
    for category_name, category_data in json_plan.items():
        if category_name == 'message':
            continue 
            
        # Get constraints for this specific category (e.g., {"top": {"color": "black"}})
        # This is where the hard constraints are introduced into the processing pipeline
        constraints_for_category = hard_constraints.get(category_name, {}) if hard_constraints else {}
            
        if isinstance(category_data, dict) and 'items' in category_data:
            
            # Extract attributes from LLM (these are soft, stylistic suggestions)
            category_color = category_data.get('color_palette', '').strip()
            pattern = category_data.get('pattern', '').strip()
            
            # Iterate through individual items in the category
            for item in category_data['items']:
                
                item_tag = item.get('tag', '').strip()
                item_fit = item.get('fit', '').strip()
                
                # Combine LLM's stylistic suggestions into a single description for the embedding search
                parts = [item_tag, item_fit, category_color, pattern]
                item_desc = " ".join(filter(None, parts)).strip()
                
                # The final list contains the LLM's stylistic prompt AND the hard constraints for database filtering
                response_list.append({
                    'category': category_name,
                    'description': item_desc, 
                    'hard_constraints': constraints_for_category # <-- Database MUST enforce these
                })
    
    # Fallback for empty list
    if not response_list and 'message' in json_plan:
         return [{'message': json_plan['message']}]
         
    return response_list

#ONLY USED FOR LOCAL AND TARGETED TESTING
if __name__ == '__main__':
    # Add minimal required imports for standalone testing
    import os
    from dotenv import load_dotenv
    from google import genai
    load_dotenv()
    
    # Initialize Client for testing purposes
    try:
        TEST_CLIENT = genai.Client()
        TEST_MODEL = 'gemini-2.5-flash'
    except Exception as e:
        print(f"Could not initialize TEST_CLIENT (check API Key): {e}")
        exit()
        
    # --- TEST SETUP ---
    # Soft Preferences (Gemini sees these)
    test_prompt = "I need a men's outfit for a fancy cocktail party, but make it modern."
    test_preferences = {'favorite_color': 'navy', 'favorite_material': 'Silk'}
    
    # Hard Constraints (Gemini does NOT see these, they are applied here)
    test_hard_constraints = {
        "top": {"color": "black", "material": "velvet", "size": "L"},
        "shoes": {"brand": "Gucci"}
    }
    
    print(f"--- Sending Prompt: '{test_prompt}' ---")
    
    # 1. Get the plan from the LLM (LLM only sees navy/silk preference)
    outfit_json = generate_outfit_plan(TEST_CLIENT, TEST_MODEL, test_prompt, user_preferences=test_preferences, hard_constraints=test_hard_constraints, gender="Male")
    
    print("\n--- Raw LLM Response (Structured JSON) ---")
    print(json.dumps(outfit_json, indent=2))
    
    # 2. Parse the plan and merge hard constraints
    parsed_items = parse_outfit_plan(outfit_json, hard_constraints=test_hard_constraints)
    
    print("\n--- Parsed Item List (Ready for Embedding/DB Query) ---")
    # Check that 'top' and 'shoes' items now contain the 'hard_constraints' key
    print(json.dumps(parsed_items, indent=2))
    
    print("\n" + "="*50 + "\n")