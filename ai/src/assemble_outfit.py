
from typing import List, Dict, Tuple, Any


def format_results(outfit_list):
        """Formats the list of selected item dicts for final output."""
        formatted_list = []
        for item_match in outfit_list:
            # Recreate the expected output dictionary structure
            formatted_list.append({
                'title': item_match.get('title'),
                'url': item_match.get('url'),
                'id': item_match.get('id'),
                'similarity': float(f"{item_match.get('similarity'):.4f}"),
                'image_link': item_match.get('image_link'),
                'price': item_match.get('price'),
                'brand': item_match.get('brand'),
                'material': item_match.get('material')
            })
        return formatted_list


def _run_optimized_knapsack_with_skip(
    processed_candidates: List[List[Dict]], 
    max_budget_cents: int
) -> Tuple[List[Dict], int]:
    """
    Optimized DP for finding best outfit allowing category skips.
    Uses a dictionary-based DP to avoid allocating huge arrays.
    
    Returns: (outfit_items, total_cost_cents)
    """
    num_categories = len(processed_candidates)
    
    # dp[cost] = (similarity, path) where path is list of selected item indices
    # We use a dict to only store reachable states
    dp = {0: (0.0, [])}
    
    for cat_idx, category_items in enumerate(processed_candidates):
        new_dp = {}
        
        for current_cost, (current_similarity, current_path) in dp.items():
            # Option 1: Skip this category
            if current_cost not in new_dp or new_dp[current_cost][0] < current_similarity:
                new_dp[current_cost] = (current_similarity, current_path + [None])
            
            # Option 2: Select an item from this category
            for item_idx, item in enumerate(category_items):
                item_cost = item['price_in_cents']
                new_cost = current_cost + item_cost
                
                if new_cost <= max_budget_cents:
                    new_similarity = current_similarity + item['similarity']
                    
                    if new_cost not in new_dp or new_dp[new_cost][0] < new_similarity:
                        new_dp[new_cost] = (new_similarity, current_path + [item_idx])
        
        dp = new_dp
    
    # Find the best result
    best_similarity = -1.0
    best_cost = 0
    best_path = []
    
    for cost, (similarity, path) in dp.items():
        if similarity > best_similarity:
            best_similarity = similarity
            best_cost = cost
            best_path = path
    
    # Reconstruct outfit from path
    outfit = []
    for cat_idx, item_idx in enumerate(best_path):
        if item_idx is not None:
            outfit.append(processed_candidates[cat_idx][item_idx]['data'])
    
    return outfit, best_cost


def _find_best_full_outfit(processed_candidates: List[List[Dict]]) -> Tuple[List[Dict], int]:
    """
    Find the best full outfit (one item per category) that maximizes similarity.
    Simply picks the highest similarity item from each category.
    
    Returns: (outfit_items, total_cost_cents)
    """
    outfit = []
    total_cost = 0
    
    for category_items in processed_candidates:
        # Find item with highest similarity in this category
        best_item = max(category_items, key=lambda x: x['similarity'])
        outfit.append(best_item['data'])
        total_cost += best_item['price_in_cents']
    
    return outfit, total_cost


def get_outfit(all_candidates: List[List[Dict]], budget: float|None) -> Tuple[List[Dict], float, List[Dict], float]:
    """
    Implements an optimized Dynamic Programming solution, returning the best feasible (partial/full) 
    outfit and the best infeasible (full) outfit for suggestion.
    
    Returns: (feasible_outfit, feasible_remaining_budget, best_full_outfit, best_full_cost)
    """

    # --- PRE-PROCESSING CANDIDATES ---
    processed_candidates = []
    for category_list in all_candidates:
        category_items = []
        for item in category_list:
            category_items.append({
                'price_in_cents': int(round(item['price'] * 100)),
                'similarity': item['similarity'],
                'data': item
            })
        processed_candidates.append(category_items)

    # --- SCENARIO 0: UNLIMITED BUDGET ---
    if not budget:
        # Just pick the best item for each category (highest similarity)
        # We reuse _find_best_full_outfit logic as it does exactly that (greedy best similarity)
        best_full_outfit, best_full_cost_cents = _find_best_full_outfit(processed_candidates)
        best_full_cost = best_full_cost_cents / 100
        formatted_outfit = format_results(best_full_outfit)
        
        # Return same outfit for both feasible and "best full"
        return (
            formatted_outfit,
            999999.0, # Dummy remaining budget
            formatted_outfit,
            best_full_cost
        )

    max_budget_cents = int(round(budget * 100))
    
    # --- SCENARIO 1: BEST FEASIBLE (PARTIAL OR FULL) OUTFIT ---
    # Use optimized DP that allows skipping categories
    feasible_outfit, feasible_cost_cents = _run_optimized_knapsack_with_skip(
        processed_candidates, 
        max_budget_cents
    )
    
    feasible_remaining_budget = budget - (feasible_cost_cents / 100)
    
    # --- SCENARIO 2: BEST FULL OUTFIT (Must select one item per category) ---
    # Use greedy approach to find best similarity regardless of budget
    best_full_outfit, best_full_cost_cents = _find_best_full_outfit(processed_candidates)
    
    best_full_cost = best_full_cost_cents / 100

    # --- FINAL FORMATTING & RETURN ---
    formatted_feasible_outfit = format_results(feasible_outfit)
    formatted_best_full_outfit = format_results(best_full_outfit)
        
    return (
        formatted_feasible_outfit, 
        feasible_remaining_budget, 
        formatted_best_full_outfit, 
        best_full_cost
    )

def select_final_outfit_and_metrics(
    all_candidates: List[List[Dict[str, Any]]],
    budget: float|None,
    feasible_outfit: List[Dict[str, Any]],
    remaining_budget: float,
    best_full_outfit: List[Dict[str, Any]],
    best_full_cost: float
) -> Dict[str, Any]:
    """
    Selects the final outfit to display based on feasibility and constructs the result dictionary.
    """
    num_required_items = len(all_candidates)
    num_feasible_items = len(feasible_outfit)
    
    # Initialize variables to hold the selection
    outfit_to_display: List[Dict[str, Any]] = []
    display_cost: float = 0.0
    final_remaining_budget: float|None = 0.0
    message: str = ""

    # Case 0: Unlimited Budget (budget is None)
    if budget is None:
        message = "Unlimited Budget: Displaying the best possible outfit based on style match."
        outfit_to_display = best_full_outfit
        display_cost = best_full_cost
        final_remaining_budget = None # Unlimited
    
    # Case 1: Full outfit found within budget
    elif num_feasible_items == num_required_items:
        message = "Full Outfit Found: All requested items were successfully matched within your budget."
        outfit_to_display = feasible_outfit
        display_cost = budget - remaining_budget # Actual cost of the feasible full outfit
        final_remaining_budget = remaining_budget

    # Case 2: Partial outfit found within budget (Primary recommendation)
    elif num_feasible_items > 0 and num_feasible_items < num_required_items:
        message = (
            f"Partial Outfit Recommendation: We found the best outfit of {num_feasible_items} out of {num_required_items} items under your budget (€{budget:.2f}). "
            f"The best possible full outfit (all categories) costs €{best_full_cost:.2f}."
        )
        outfit_to_display = feasible_outfit
        display_cost = budget - remaining_budget # Actual cost of the feasible partial outfit
        final_remaining_budget = remaining_budget
    
    # Case 3: No feasible items found (Default to best full outfit as the only suggestion)
    else:
        # Check if even the best_full_outfit is empty (database issue)
        if not best_full_outfit:
             return {
                "error": "No Candidates Found",
                "detail": "Failed to find *any* matching items across all categories in the database.",
                "status_code": 404
            }

        message = (
            f"Budget Constraint Issue: Your budget (€{budget:.2f}) is too low to purchase any feasible combination of items. "
            f"Suggestion: Displaying the best possible full outfit, which costs €{best_full_cost:.2f}."
        )
        outfit_to_display = best_full_outfit
        display_cost = best_full_cost
        # Recalculate remaining budget to be clearly negative based on the suggestion
        final_remaining_budget = budget - best_full_cost 
    
    
    # Check for a complete failure to find any item (even over budget)
    if not outfit_to_display:
        return {
            "error": "Critical Assembly Error",
            "detail": "Outfit assembly returned an empty result list after processing. Check database connectivity and retrieval logic.",
            "status_code": 500
        }

    # Final Output Structure for the API
    return {
        "outfit": outfit_to_display,
        "cost": round(display_cost, 2),
        "remaining_budget": round(final_remaining_budget, 2) if final_remaining_budget is not None else None,
        "message": message,
        "status_code": 200 # Indicate success, even if it's a partial outfit
    }