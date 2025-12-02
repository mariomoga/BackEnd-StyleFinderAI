import os
import sys
import webbrowser 
import time
import json
import google.generativeai as genai
import torch
from supabase import create_client, Client
from transformers import CLIPProcessor, CLIPModel
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

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
    raise ValueError("Supabase credentials (SUPABASE_URL, SUPABASE_KEY) must be set in the environment or .env file.")
    
try:
    SUPABASE_CLIENT: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Error initializing Supabase client: {e}")
    # In a real app, you'd handle this more gracefully (e.g., logging and returning a 500 error)
    raise

# Initialize the Gemini Client ONCE
# This client object will be reused for every API call.
try:
    GEMINI_CLIENT = genai.Client()
except Exception as e:
    print(f"Error initializing Gemini client: {e}")
    # In a real app, you'd handle this more gracefully (e.g., logging and returning a 500 error)
    raise

GEMINI_MODEL_NAME = 'gemini-2.0-flash'

# --- Global Initialization (Loaded only ONCE) ---
CLIP_MODEL_NAME = "patrickjohncyh/fashion-clip"
MODEL = CLIPModel.from_pretrained(CLIP_MODEL_NAME)
PROC = CLIPProcessor.from_pretrained(CLIP_MODEL_NAME, use_fast=True)
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
MODEL.to(DEVICE)
MODEL.eval()

FASHION_CATEGORIES = ['top', 'bottom', 'dresses', 'outerwear', 'swimwear', 'shoes', 'accessories']

if __name__ == '__main__':
    while True:
        image = input("Enter the path for an image to test the image_input functionality if you want to:")
        if image != "":
            image_data = encode_image_to_base64(image)
        else:
            image_data = None
        
        user_id_key = input("Enter your Supabase Auth User ID (UID) for preference lookup:\n> ")
        if user_id_key:
            user_preferences, gender = get_user_preferences(SUPABASE_CLIENT, user_id_key)
        else:
            user_preferences = None
            gender = "male"

        # 1. USER'S QUERY HANDLING
        budget = 10000
        user_constraints = {}
        outfit_ready = False
        chat_history = []
        over_budget_outfit = {}
        count = 0
        print("Input a request per cortesia bisogna testare")
        while not outfit_ready:
            user_prompt = input()
            print("\n--- Sending request to Gemini... ---")
            if count == 0:
                response = generate_outfit_plan(GEMINI_CLIENT, GEMINI_MODEL_NAME, user_prompt, chat_history, image_data, None, user_preferences, gender)
            else:
                response = generate_outfit_plan(GEMINI_CLIENT, GEMINI_MODEL_NAME, user_prompt, chat_history, None, image_data, user_preferences, gender)
            status = response.get('status')
            print(status)
            if not status:
                print("SUCCESSO CASINO")
                sys.exit(1)
            if status == "Guardrail":
                print("--- GUARDRAIL MESSAGE ---")
                print(response.get('message'))
                sys.exit(1)
            if status == "AWAITING_INPUT":
                chat_history = response.get('history')
                print(response.get('prompt_to_user'))
            elif status == "READY_TO_GENERATE":
                outfit = response.get('outfit_plan')
                budget = response.get('budget')
                user_constraints = response.get('hard_constraints')
                chat_history = response.get('history')
                outfit_ready = True
            elif status == 'Error':
                print(response.get('missing_info'))
                sys.exit(1)
            count += 1

        print("BUDGET: ", budget)
        print("CONSTRAINTS: ", user_constraints)
        parsed_item_list = parse_outfit_plan(outfit, user_constraints)
        print("OUTFIT CONTENT", parsed_item_list) #UNCOMMENT TO CHECK WHAT GEMINI COOKED
        
        #USER'S QUERY IS NOW RE-INTERPRETED TO BETTER UNDERSTAND USER'S INTENT AND WELL FORMATTED IN A JSON STRING
        #CHECK USER'S QUERY FOR HATE-SPEECH OR NOT CONFORMING TO OUTFIT REQUESTS
        if parsed_item_list is None:
            print("Something went wrong with the processing of your request, try again.")
            continue
        
        elif parsed_item_list and 'message' in parsed_item_list[0]:
            # ... (print guardrail message)
            print("\n--- GUARDRAIL MESSAGE ---")
            print(parsed_item_list[0]['message'])
            continue
            
        # 2. EXTENDED QUERY EMBEDDING
        start_time_embed = time.time()
        for item in parsed_item_list:
            query_vector = get_text_embedding_vector(MODEL, PROC, DEVICE, item['description']) #GEMINI EXTENDED QUERY EMBEDDING
            query_vector = query_vector.flatten().tolist() # Convert to list for Supabase (JSON standard)
            item['embedding'] = query_vector
        end_time_embed = time.time()

        # 3. CLOTHING ITEMS RETRIEVAL
        print(f"--- Retrieving {len(parsed_item_list)} matching products... ---")
        start_time_retrieval = time.time()
        
        all_candidates = search_product_candidates_with_vector_db(SUPABASE_CLIENT, parsed_item_list, budget, gender)
        if 'error' in all_candidates[0]:
            print(all_candidates[0])
            continue

        end_time_retrieval = time.time()

        # 4. FINAL OUTFIT ASSEMBLY (Knapsack)
        start_time_assembly = time.time()

        # --- UPDATED: Unpack the four return values from the new get_outfit ---
        feasible_outfit: List[Dict[str, Any]]
        remaining_budget: float
        best_full_outfit: List[Dict[str, Any]]
        best_full_cost: float
        
        (
            feasible_outfit, 
            remaining_budget, 
            best_full_outfit, 
            best_full_cost
        ) = get_outfit(all_candidates, budget)
        
        # Variables to hold the final selection for display and explanation
        outfit_to_display: List[Dict[str, Any]] = []
        display_cost: float = 0.0

        # --- LOGIC TO SELECT WHICH OUTFIT TO DISPLAY ---
        
        if len(feasible_outfit) == len(all_candidates):
            # Case 1: Full outfit found within budget
            print("--- Full Outfit Found (Within Budget) ---")
            outfit_to_display = feasible_outfit
            display_cost = budget - remaining_budget # Actual cost of the feasible full outfit
        
        elif len(feasible_outfit) > 0 and len(feasible_outfit) < len(all_candidates):
            # Case 2: Partial outfit found within budget (Primary recommendation)
            print("--- Primary Recommendation (Partial, Within Budget) ---")
            print(f"We found the best outfit of {len(feasible_outfit)} items under your budget of €{budget:.2f}.")
            # Offer the full outfit as an alternative
            print("\n--- Alternative Full Outfit (Over Budget) ---")
            print(f"The best possible full outfit (all categories) costs €{best_full_cost:.2f}.")
            print("Displaying the partial outfit now. If you want the full outfit, you'll go over budget.")
            outfit_to_display = feasible_outfit
            over_budget_outfit = best_full_outfit
            display_cost = budget - remaining_budget # Actual cost of the feasible partial outfit

        else:
            # Case 3: No feasible items found (Default to best full outfit as the only suggestion)
            print("--- No Feasible Items Found Within Budget ---")
            print(f"Your budget (€{budget:.2f}) is too low to purchase any combination of items.")
            print(f"**Suggestion:** The best possible full outfit (all categories) costs €{best_full_cost:.2f}. Displaying this alternative.")
            outfit_to_display = best_full_outfit
            # Note: remaining_budget will be negative here if we use the original budget, so we set a clear cost
            remaining_budget = budget - best_full_cost 
            display_cost = best_full_cost


        # --- ERROR CHECK (if outfit_to_display is still empty/has an error) ---
        is_error = not outfit_to_display or ('error' in outfit_to_display[0] if outfit_to_display else False)
        
        if is_error:
            if outfit_to_display:
                print(outfit_to_display[0])
            else:
                print({"error": "Outfit assembly returned an unexpected empty result list after processing."})
            continue

        end_time_assembly = time.time()

        # 5. GENERATE EXPLANATIONS for the selected outfit (outfit_to_display)
        # start_time_explanations = time.time()
        # explanations = explain_selected_outfit(GEMINI_CLIENT, GEMINI_MODEL_NAME, user_prompt, outfit_to_display)
        # end_time_explanations = time.time()
        # print("Explanations for the retrieved outfit:\n", explanations)

        # ... (Print JSON Results)
        print("\n--- Final Outfit Retrieval Results (JSON Data) ---")
        print(f"Displaying Outfit Cost: €{display_cost:.2f}")
        print(f"Remaining Budget (based on original budget): €{remaining_budget:.2f}")

        # Print the selected outfit
        print("BEST OUTFIT UNDER BUDGET:")
        print(json.dumps(outfit_to_display, indent=2))
        print("\n" + "="*50)

        if over_budget_outfit:
            print("BEST OUTFIT OVER BUDGET:")
            print(json.dumps(over_budget_outfit, indent=2))
            print("\n" + "="*50)
        
        # ... (6. Terminal Visualization Block)
        start_time_viz = time.time()
        for item in outfit_to_display:
            if item.get('image_link'):
                image_url = item['image_link']
                url = item['url']
                print(f"  Title: {item.get('title')}")
                print(f"  Image URL: {image_url}")
                print(f"  URL for Purchase: {url}")
                try:
                    webbrowser.open_new_tab(image_url)
                    print("  --> Image opened in your default web browser.")
                except Exception as e:
                    print(f"  Could not automatically open browser: {e}")
            
            elif item.get('status'):
                print(f"No match found for {item['requested_item']}: {item['status']}\n")
        end_time_viz = time.time()