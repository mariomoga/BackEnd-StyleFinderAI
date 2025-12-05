import os
import logging

from flask_login import current_user
from google import genai
import torch
from supabase import create_client, Client
from transformers import CLIPProcessor, CLIPModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Import custom modules
from ai.src.preferences_management import get_user_preferences
from ai.src.constraints_management import get_user_constraints
from ai.src.query_handler import generate_outfit_plan, parse_outfit_plan
from ai.src.query_embedder import get_text_embedding_vector
from ai.src.outfit_retrieval_logic import search_product_candidates_with_vector_db
from ai.src.assemble_outfit import get_outfit, select_final_outfit_and_metrics
from ai.src.get_explanations import explain_selected_outfit

# --- 1. Global Initialization (Loaded only ONCE when the server starts) ---

# Load environment variables (like the GEMINI_API_KEY)
load_dotenv()

SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_KEY: Optional[str] = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    # Handle environment variables missing: Critical, must stop.
    logging.critical("Supabase credentials (SUPABASE_URL, SUPABASE_KEY) are missing.")
    raise ValueError("Supabase credentials must be set in the environment or .env file.")
    
# 1. Supabase Client Initialization
try:
    SUPABASE_CLIENT: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Optional: Perform a small check query here to ensure connectivity (e.g., SELECT 1)
    logging.info("✅ Supabase client initialized successfully.")
except Exception as e:
    # Handle Supabase connection failure: Critical, must stop.
    logging.critical(f"❌ Error initializing Supabase client: {e}", exc_info=True)
    # Reraise the exception to stop the server process from starting
    raise ConnectionError("Failed to connect to Supabase.") from e

# 2. Gemini Client Initialization
try:
    GEMINI_CLIENT = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    logging.info("✅ Gemini client initialized successfully.")
except Exception as e:
    # Handle Gemini client initialization failure: Critical, must stop.
    logging.critical(f"❌ Error initializing Gemini client: {e}", exc_info=True)
    # Reraise the exception to stop the server process from starting
    raise RuntimeError("Failed to initialize the Google Gemini Client.") from e

GEMINI_MODEL_NAME = 'gemini-2.5-flash'

# 3. CLIP Model Initialization (Heavy/Critical Resource)
CLIP_MODEL_NAME = "patrickjohncyh/fashion-clip"
try:
    DEVICE = torch.device("cpu")
    MODEL = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
    PROC = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME, use_fast=True)
    MODEL.to(DEVICE)
    MODEL.eval()
    logging.info(f"✅ CLIP model initialized successfully on device: {DEVICE}")
except Exception as e:
    # Handle Model loading failure: Critical, must stop.
    logging.critical(f"❌ Error initializing CLIP model: {e}", exc_info=True)
    raise RuntimeError("Failed to load the CLIP model and processor.") from e

FASHION_CATEGORIES = ['top', 'bottom', 'dresses', 'outerwear', 'swimwear', 'shoes', 'accessories']

def outfit_recommendation_handler(user_prompt: str, chat_history: List[Dict[str, Any]], user_id_key: int | None, image_data:tuple[str, bytes] | None, past_images:dict[str, bytes] | None, selected_outfit_index: int | None = None, selected_message_id: str | None = None, guest_gender: str | None = None) -> Dict[str, Any]:
    
    #CRITICAL: IMAGE_DATA NEEDS TO BE ALREADY ENCODED IN base64 BY THE FRONTEND
    #BEFORE GETTING PASSED TO THIS METHOD, ALSO THE mimeType NEEDS TO BE PASSED

    #THIS PROBABLY NEEDS TO BE DONE AS SOON AS THE USER LOGS IN AND THEN PASSED TO THE FUNCTION
    #DON'T KNOW IF THAT'S THE CASE SO I'LL LEAVE IT AS IS FOR NOW
    # Use guest_gender if provided (for non-authenticated users), otherwise use current_user.gender
    gender = guest_gender
    if not gender:
        try:
            if current_user and current_user.is_authenticated:
                gender = current_user.gender
        except Exception:
            gender = None
    
    if user_id_key:
        #get_user_preferences FOR NOW QUERIES THE MOCK-UP USER DB I MADE
        #NEEDS TO BE CHANGED SO THAT IT QUERIES THE RIGHT DB OR REMOVED
        #ALTOGETHER IF NOT NEEDED
        user_preferences = get_user_preferences(SUPABASE_CLIENT, user_id_key)
    else:
        user_preferences = None

    print(user_preferences, gender)

    # 1. Recupera items dall'outfit precedente (se esiste) per il refinement
    target_outfit_items = []
    
    # Logic to find the target outfit based on selection
    target_outfit_message = None

    if selected_message_id:
        # Find the specific message in history
        for msg in reversed(chat_history):
            if str(msg.get('message_id')) == str(selected_message_id) and msg.get('role') == 'model':
                target_outfit_message = msg
                break
    elif chat_history:
        # Default to the last AI message if no specific message selected
        for msg in reversed(chat_history):
            if msg.get('role') == 'model':
                target_outfit_message = msg
                break

    if target_outfit_message:
        outfits = target_outfit_message.get('outfits', [])
        # If selected_outfit_index is provided, use it. Otherwise default to 0 (first outfit)
        target_index = selected_outfit_index if selected_outfit_index is not None else 0
        
        if outfits and len(outfits) > target_index:
            target_outfit_items = outfits[target_index].get('outfit', [])
            print(f"DEBUG: Using items from message {target_outfit_message.get('message_id')}, outfit index {target_index} for refinement.")
        else:
             print(f"DEBUG: Target outfit index {target_index} not found in message {target_outfit_message.get('message_id')}.")
    else:
        print("DEBUG: No suitable previous outfit found for refinement.")

    # 1. USER'S QUERY HANDLING
    logging.info("--- Sending request to Gemini for state transition... ---")

    response = generate_outfit_plan(GEMINI_CLIENT, GEMINI_MODEL_NAME, user_prompt, chat_history, image_data, past_images, user_preferences, gender)
    status = response.get('status')

    # --- Status Check & Dialogue Termination ---
    if status in ["Guardrail", "Error"]:
        error_message = response.get('message') or response.get('missing_info', "An unexpected error occurred during LLM processing.")
        logging.error(f"LLM returned status {status}: {error_message}")
        # Return structured error response for the API
        return {"status": status, "message": error_message, "status_code": 400 if status == "Guardrail" else 500}
    
    if status == "AWAITING_INPUT":
        # Conversation must continue. Return necessary state info to the frontend.
        logging.info("LLM is AWAITING_INPUT. Returning dialogue prompt.")
        return {
            "status": "AWAITING_INPUT",
            "prompt_to_user": response.get('prompt_to_user'),
            "chat_history": response.get('history', chat_history),
            "conversation_title": response.get('conversation_title'),
            "status_code": 202 # Accepted (partial content)
        }
    
    # --- Status READY_TO_GENERATE: Proceed to heavy Retrieval and Assembly ---

    # Extract final plan and constraints from the LLM response
    outfits_list = response.get('outfits')
    if not outfits_list:
        # Fallback for backward compatibility or if LLM messes up
        single_outfit = response.get('outfit_plan')
        if single_outfit:
            outfits_list = [single_outfit]
        else:
            logging.error("Either LLM returned READY_TO_GENERATE but 'outfits' is missing or LLM returned an unexpected status")
            return {"status": "Error", "message": "Failed to generate an outfit plan after successful budget confirmation.", "status_code": 500}

    logging.info(f"Raw LLM Response: {response}")

    budget = response.get('max_budget')
    if not budget:
        budget = response.get('budget')

    if not budget or budget == 0:
        budget = None
    user_constraints = response.get('hard_constraints', {})

    logging.info(f"LLM is READY_TO_GENERATE. Final Budget: {budget}. Generating {len(outfits_list)} outfits.")

    final_outfits_results = []

    # Helper for normalization
    def normalize(s):
        if not s: return ""
        s = s.lower().strip()
        if s.endswith('s'): return s[:-1] # Simple singularization
        return s

    changed_categories = response.get('changed_categories', [])
    logging.info(f"DEBUG: changed_categories from LLM: {changed_categories}")

    # --- SAFEGUARD: Enforce single outfit for refinement unless explicitly requested ---
    if changed_categories and len(outfits_list) > 1:
        # Simple heuristic: check if user asked for "options" or numbers in the current prompt
        keywords = ["option", "choice", "variant", " 1 ", " 2 ", " 3 ", " one ", " two ", " three "]
        is_explicit_request = any(k in user_prompt.lower() for k in keywords)
        
        if not is_explicit_request:
            logging.info("DEBUG: Refinement detected without explicit option request. Enforcing single outfit.")
            outfits_list = outfits_list[:1]

    last_outfit = None
    # Use the target_outfit_items we identified at the start of the function
    if target_outfit_items:
         last_outfit = target_outfit_items
         logging.info(f"DEBUG: last_outfit set for locking: {len(last_outfit)} items.")
    else:
         # Fallback: check if response has it (unlikely but safe)
         if response.get('previous_outfit_items'):
             last_outfit = response.get('previous_outfit_items')
             logging.info(f"DEBUG: last_outfit set from response: {len(last_outfit)} items.")
         else:
             logging.info("DEBUG: No previous outfit items found for locking.")

    # 2. Setup locking logic
    locked_items = []
    if last_outfit:
        # ... (existing locking logic)
        # The DB stores it as a list of dicts with 'main_category'
        if isinstance(last_outfit, dict) and 'outfit' in last_outfit:
             last_outfit = last_outfit['outfit']
        logging.info(f"DEBUG: Found last outfit with {len(last_outfit)} items.")

    for i, outfit_plan in enumerate(outfits_list):
        logging.info(f"Processing outfit {i+1}/{len(outfits_list)}...")
        
        parsed_item_list = parse_outfit_plan(outfit_plan, user_constraints)

        if parsed_item_list is None:
            logging.error(f"Parsing failed for outfit {i+1}")
            continue # Skip this outfit if parsing fails
        
        elif parsed_item_list and 'message' in parsed_item_list[0]:
            error_msg = parsed_item_list[0]['message'] if parsed_item_list else "Parsing failed."
            logging.error(f"Post-LLM parsing failed for outfit {i+1}: {error_msg}")
            continue

        # --- CARRY-OVER LOGIC ---
        if last_outfit:
             new_plan_categories = set(normalize(item['category']) for item in parsed_item_list)
             for prev_item in last_outfit:
                 prev_cat = prev_item.get('main_category', '')
                 if not prev_cat: continue
                 
                 norm_prev_cat = normalize(prev_cat)
                 
                 # Check if missing and not changed
                 if norm_prev_cat not in new_plan_categories:
                     is_changed = False
                     for changed_cat in changed_categories:
                         if normalize(changed_cat) == norm_prev_cat:
                             is_changed = True
                             break
                     
                     if not is_changed:
                         logging.info(f"DEBUG: Category '{prev_cat}' missing and not changed. Carrying over.")
                         # Add a placeholder item to parsed_item_list to trigger locking logic
                         # We need 'description' for embedding if it ends up being searched (unlikely if locked, but safe to have)
                         parsed_item_list.append({
                             'category': prev_cat, 
                             'items': [], 
                             'color_palette': '', 
                             'pattern': '',
                             'description': f"{prev_cat}" # Dummy description
                         })

        # --- LOCKING & RETRIEVAL ---
        all_candidates = []
        items_to_search = []
        indices_to_search = []

        for idx, item in enumerate(parsed_item_list):
            category = item['category']
            is_locked = False
            locked_candidate = None
            
            # Locking condition: last_outfit exists AND category NOT in changed_categories
            if last_outfit:
                 is_changed = False
                 for changed_cat in changed_categories:
                     if normalize(changed_cat) == normalize(category):
                         is_changed = True
                         break
                 
                 if not is_changed:
                     # Find item in last_outfit
                     for prev_item in last_outfit:
                         prev_cat = prev_item.get('main_category', '')
                         if normalize(prev_cat) == normalize(category):
                             logging.info(f"DEBUG: Locking item {category}")
                             is_locked = True
                             locked_candidate = {
                                 'price': prev_item.get('price', 0),
                                 'similarity': 1.0,
                             }
                             locked_candidate.update(prev_item)
                             break
            
            if is_locked and locked_candidate:
                all_candidates.append([locked_candidate])
            else:
                all_candidates.append(None) # Placeholder
                items_to_search.append(item)
                indices_to_search.append(idx)

        # Batch search for unlocked items
        if items_to_search:
            logging.info(f"Generating embeddings for {len(items_to_search)} items...")
            for item in items_to_search:
                query_vector = get_text_embedding_vector(MODEL, PROC, DEVICE, item['description']) 
                query_vector = query_vector.flatten().tolist() 
                item['embedding'] = query_vector

            logging.info("Searching product candidates in vector DB...")
            search_results = search_product_candidates_with_vector_db(SUPABASE_CLIENT, items_to_search, budget, gender)
            
            if search_results:
                # If search_results is shorter than items_to_search (error?), handle it.
                # Assuming 1-to-1 mapping if no error.
                for j, result in enumerate(search_results):
                    if j < len(indices_to_search):
                        original_idx = indices_to_search[j]
                        all_candidates[original_idx] = result
            
        # Check for retrieval errors in unlocked items
        if any(c and 'error' in c[0] for c in all_candidates if c and isinstance(c, list) and len(c)>0 and isinstance(c[0], dict)):
             # If any candidate list has an error
             # We can log it.
             pass

        # 4. OUTFIT ASSEMBLY
        logging.info("Assembling outfit...")
        (feasible_outfit, remaining_budget, best_full_outfit, best_full_cost) = get_outfit(all_candidates, budget)
        
        final_result_single = select_final_outfit_and_metrics(all_candidates, budget, feasible_outfit, remaining_budget, best_full_outfit, best_full_cost)
        
        if 'error' in final_result_single:
             logging.error(f"Selection failed for outfit {i+1}: {final_result_single}")
             continue
        
        logging.info(f"Outfit {i+1} result: Cost={final_result_single.get('cost')}, Budget={budget}, Remaining={final_result_single.get('remaining_budget')}")
        final_outfits_results.append(final_result_single)

    # Filter out over-budget outfits if we have at least one valid outfit
    within_budget_outfits = [o for o in final_outfits_results if o.get('remaining_budget') is None or o.get('remaining_budget', 0) >= 0]
    
    if within_budget_outfits:
        final_outfits_results = within_budget_outfits
        logging.info(f"Filtered out {len(final_outfits_results) - len(within_budget_outfits)} over-budget outfits.")
    else:
        logging.warning("No outfits within budget found. Returning all (potentially over-budget) results or empty.")

    if not final_outfits_results:
        return {"status": "Error", "message": "Failed to generate any valid outfits.", "status_code": 500}

    final_response = {
        'status': 'COMPLETED',
        'message': "Here are your outfit options.",
        'status_code': 200,
        'chat_history': response.get('history', chat_history),
        'conversation_title': response.get('conversation_title'),
        'outfits': final_outfits_results 
    }
    
    logging.info(f"Successfully assembled {len(final_outfits_results)} outfits.")
    return final_response 

def generate_explanation_only(user_prompt: str, outfit_data: List[Dict[str, Any]]) -> str:
    """
    Helper function to generate explanations on demand.
    """
    logging.info("Generating outfit explanation (On-Demand)...")
    try:
        explanations = explain_selected_outfit(GEMINI_CLIENT, GEMINI_MODEL_NAME, user_prompt, outfit_data)
        return explanations
    except Exception as e:
        logging.error(f"Error generating explanation: {e}")
        return "Sorry, I couldn't generate an explanation at this time."