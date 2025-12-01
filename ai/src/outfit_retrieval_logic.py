# src/ai/outfit_retrieval_logic.py (Complete updated file)

import numpy as np
import pandas as pd
from typing import List
from supabase import Client

def vector_search_rpc_candidates(client: Client, query_vector: np.ndarray, category: str, budget: float, gender: str, constraints: dict | None, limit: int = 20, threshold: float = -1000.0) -> pd.DataFrame:
    """
    Calls the optimized PostgreSQL RPC function (search_outfits) to find the best match 
    for a single query vector within a specified category, including hard constraints.
    """
    try:
        # 1. Initialize constraint variables to None
        color_in = None
        material_in = None
        brand_in = None

        # 2. Safely unpack constraints if the dictionary is provided
        if constraints:
            color_in = constraints.get("color")
            material_in = constraints.get("material")
            brand_in = constraints.get("brand")
        
        # Call the RPC function defined in PostgreSQL
        response = client.rpc(
            "search_outfits",
            {
                "query_embedding": query_vector,
                "match_threshold": threshold,
                "match_count": limit,
                "category_in": category, # The main_category filter
                "max_espense": budget,
                "gender": gender,
                # 3. Pass the extracted (or None) constraints to the RPC
                "color_in": color_in,
                "material_in": material_in,
                "brand_in": brand_in
            }
        ).execute()

        if not response.data:
            return pd.DataFrame()
            
        # The result already includes the calculated 'similarity' score
        df = pd.DataFrame(response.data)
        
        return df

    except Exception as e:
        print(f"Supabase RPC search error for category '{category}': {e}")
        return pd.DataFrame()

def search_product_candidates_with_vector_db(client, parsed_item_list: List[dict], budget: float, gender: str) -> List[List[dict]] | List[dict]:
    """
    Finds the single best product match using an indexed vector search in Supabase,
    applying item-specific constraints (color, material, brand).
    """
    all_candidates = []

    # 2. TIME AND EXECUTE VECTOR SEARCH (The database handles the filtering and ranking)

    for item in parsed_item_list:
        # Extract the specific constraints for the current item.
        # This will be None if the key is missing, or a dictionary.
        item_constraints = item.get('hard_constraints')
        print(item_constraints)
        # NOTE: item['description'] is used for logging/error reporting
        
        df_candidates = vector_search_rpc_candidates(
            client, 
            item['embedding'],
            item['category'],
            budget, 
            gender,
            # PASS THE ITEM-SPECIFIC CONSTRAINTS HERE
            constraints=item_constraints 
        )

        if not df_candidates.empty:
            candidate_list = df_candidates.to_dict('records')
            all_candidates.append(candidate_list)
        else:
            print(f"Warning: No candidates found for {item.get('description', 'Unknown Item')} ({item['category']}). Cannot form a full outfit.")
            # Return an error signal if any part of the outfit fails to find candidates
            return [{"error": f"Failed to find candidates for {item['category']}. Cannot proceed with Knapsack optimization."}]
                        
    # Return the entire DataFrame of candidates
    return all_candidates
