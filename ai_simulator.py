import json
import random
import uuid
from decimal import Decimal

from db_manager import DBManager

def simulate_ai_outfit_generator(
        prompt: str,
        image = None,
        num_items: int = 5,
        max_budget: float = 1000.0
) -> dict:
    """
    Simula la generazione di outfit AI recuperando prodotti casuali dal database.

    Args:
        prompt: Il prompt dell'utente (non utilizzato nello stub)
        image: the image
        num_items: Numero di item da includere nell'outfit (default: 5)
        max_budget: Budget massimo considerato (default: 1000.0)

    Returns:
        Dict contenente l'outfit generato nel formato richiesto
    """

    # Query per recuperare prodotti casuali
    query = """
            SELECT id, title, url, image_link, price
            FROM product_data
            WHERE price IS NOT NULL
            ORDER BY RANDOM()
            LIMIT %s \
            """

    conn = DBManager.get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, (num_items,))
    products = cursor.fetchall()
    cursor.close()

    outfit_items = []
    total_cost = 0.0

    for product in products:
        product_id, title, url, image_link, price = product
        price_float = float(price) if isinstance(price, Decimal) else price

        outfit_item = {
            "title": title,
            "url": url,
            "id": str(product_id) if isinstance(product_id, uuid.UUID) else product_id,
            "similarity": round(random.uniform(0.25, 0.40), 4),
            "image_link": image_link,
            "price": price_float
        }
        outfit_items.append(outfit_item)
        total_cost += price_float

    messages = [
        "Full Outfit Found: All requested items were successfully matched within your budget.",
        "Great Outfit Match: We found perfect items that suit your style preferences.",
        "Outfit Complete: Your personalized selection is ready based on your request.",
        "Style Match Found: All pieces harmoniously complement each other.",
        "Perfect Combination: We've curated an outfit tailored to your needs."
    ]

    explanations = [
        "This outfit perfectly balances style and comfort for any occasion. Each piece has been carefully selected to create a cohesive look that reflects modern trends while maintaining timeless elegance.",
        "A versatile ensemble that transitions seamlessly from day to night. The combination of these items ensures you'll look polished and put-together, regardless of the setting.",
        "This curated selection brings together quality pieces that work harmoniously. The color palette and style create a sophisticated appearance suitable for various events.",
        "An expertly matched outfit that showcases attention to detail. Each item complements the others, creating a refined and contemporary aesthetic that's both practical and stylish.",
        "This outfit combines functionality with fashion-forward design. The pieces selected offer versatility and can be mixed and matched with other items in your wardrobe."
    ]

    result = {
        "outfit": outfit_items,
        "message": random.choice(messages),
        "status_code": 200,
        "explanation": random.choice(explanations)
    }

    return result