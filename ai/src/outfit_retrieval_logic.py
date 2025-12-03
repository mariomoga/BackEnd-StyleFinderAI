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

def search_product_candidates_with_vector_db(client: Client, parsed_item_list: List[dict], budget: float, gender: str) -> List[List[dict]] | List[dict]:
    """
    Finds best product matches using a SINGLE batch vector search in Supabase.
    """

    queries_payload = []

    for item in parsed_item_list:
        constraints = item.get('hard_constraints', {}) or {}

        embedding_list = item['embedding'].tolist() if isinstance(item['embedding'], np.ndarray) else item['embedding']

        query_obj = {
            "category": item['category'],
            "embedding": embedding_list,
            "color": constraints.get("color"),
            "material": constraints.get("material"),
            "brand": constraints.get("brand")
        }
        queries_payload.append(query_obj)

    try:
        response = client.rpc(
            "search_outfits_batch",
            {
                "queries": queries_payload,
                "match_threshold": -1000.0,
                "match_count": 20,
                "max_espense": budget,
                "gender": gender
            }
        ).execute()

        if not response.data:
            print("Warning: Batch search returned no data.")
            return [{"error": "No candidates found for any item."}]

        flat_results = pd.DataFrame(response.data)

        all_candidates = []

        for i in range(len(parsed_item_list)):
            sql_index = i + 1 # this because results indices starts from 1

            item_candidates_df = flat_results[flat_results['query_index'] == sql_index]

            if item_candidates_df.empty:
                item_desc = parsed_item_list[i].get('description', 'Unknown Item')
                category = parsed_item_list[i].get('category')
                print(f"Warning: No candidates found for {item_desc} ({category}).")
                return [{"error": f"Failed to find candidates for {category}. Cannot proceed with Knapsack optimization."}]

            candidates_list = item_candidates_df.drop(columns=['query_index']).to_dict('records')
            all_candidates.append(candidates_list)

        return all_candidates

    except Exception as e:
        print(f"Supabase Batch RPC search error: {e}")
        return [{"error": f"Database error: {str(e)}"}]
