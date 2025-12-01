def get_user_constraints() -> dict:
    """
    Gathers outfit constraints from the user via terminal input.

    The function prompts the user for optional constraints (color, material, brand)
    for each clothing category (top, bottom, shoes). If a user leaves an input
    blank, that constraint is ignored for the final dictionary.

    Returns:
        dict: A nested dictionary of user-specified constraints.
              Example: {'bottom': {'color': 'Red'}, 'top': {'material': 'wool'}}
    """
    print("\n--- Outfit Constraint Builder ---")
    print("Enter your constraints. Press Enter to skip any constraint.\n")

    categories = ["top", "bottom", "outerwear", "shoes"]
    constraints_keys = ["color", "material", "brand"]
    user_constraints = {}

    for category in categories:
        print(f"\n[Constraints for {category.upper()}]")
        category_constraints = {}

        for key in constraints_keys:
            # Prompt the user for input
            prompt = f"  - Desired {key} for {category}: "
            value = input(prompt).strip()

            # If the user provided a non-empty value, add it to the category constraints
            if value:
                category_constraints[key] = value

        # Only add the category to the main dictionary if at least one constraint was provided
        if category_constraints:
            user_constraints[category] = category_constraints

    print("\n--- Constraint Collection Complete ---")
    return user_constraints