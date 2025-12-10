"""
Model Fallback Helper Module

Provides automatic fallback to alternative Gemini models when rate limit (429) errors occur.
"""

import time
import logging
from typing import Any, List, Optional
from google import genai
from google.genai import types

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Default fallback model sequence
DEFAULT_FALLBACK_MODELS = [
    "gemini-2.0-flash",           # Primary model
    "gemini-2.5-flash",         # Fallback 1: faster variant
    "gemini-2.5-flash-lite",    # Fallback 2: lite variant
]

# Retry configuration
MAX_RETRIES_PER_MODEL = 2  # Number of retries before switching to next model
INITIAL_RETRY_DELAY = 1.0  # Seconds to wait before first retry
BACKOFF_MULTIPLIER = 2.0   # Multiply delay for each retry


def is_rate_limit_error(exception: Exception) -> bool:
    """
    Check if the exception is a 429 rate limit error.
    """
    error_str = str(exception).lower()
    # Check for common rate limit indicators
    return (
        "429" in error_str or 
        "rate limit" in error_str or 
        "quota exceeded" in error_str or
        "resource exhausted" in error_str or
        "too many requests" in error_str
    )


def generate_content_with_fallback(
    client: genai.Client,
    contents: Any,
    config: types.GenerateContentConfig,
    models: Optional[List[str]] = None,
    initial_model: Optional[str] = None
) -> Any:
    """
    Attempts to generate content with automatic fallback on 429 errors.
    
    Args:
        client: The Gemini client instance
        contents: The content to send to the model
        config: GenerateContentConfig for the request
        models: Optional list of models to try (defaults to DEFAULT_FALLBACK_MODELS)
        initial_model: Optional specific model to try first (will be prepended to models list)
    
    Returns:
        The response from generate_content
        
    Raises:
        Exception: If all models fail
    """
    fallback_models = models or DEFAULT_FALLBACK_MODELS.copy()
    
    # If an initial model is specified, ensure it's tried first
    if initial_model and initial_model not in fallback_models:
        fallback_models = [initial_model] + fallback_models
    elif initial_model and initial_model in fallback_models:
        # Move initial_model to the front
        fallback_models.remove(initial_model)
        fallback_models = [initial_model] + fallback_models
    
    last_exception = None
    
    for model_index, model_name in enumerate(fallback_models):
        retry_delay = INITIAL_RETRY_DELAY
        
        for retry in range(MAX_RETRIES_PER_MODEL):
            try:
                if retry > 0:
                    logging.info(f"🔄 Retry {retry}/{MAX_RETRIES_PER_MODEL} for model {model_name}...")
                else:
                    logging.info(f"📡 Using model: {model_name}")
                
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                
                # Success!
                if model_index > 0:
                    logging.info(f"✅ Successfully used fallback model: {model_name}")
                return response
                
            except Exception as e:
                last_exception = e
                
                if is_rate_limit_error(e):
                    logging.warning(f"⚠️ Rate limit hit on {model_name}: {e}")
                    
                    # If we have more retries for this model, wait and retry
                    if retry < MAX_RETRIES_PER_MODEL - 1:
                        logging.info(f"⏳ Waiting {retry_delay:.1f}s before retry...")
                        time.sleep(retry_delay)
                        retry_delay *= BACKOFF_MULTIPLIER
                    else:
                        # Move to next model
                        if model_index < len(fallback_models) - 1:
                            logging.info(f"🔀 Switching to fallback model: {fallback_models[model_index + 1]}")
                        break
                else:
                    # Non-rate-limit error, raise immediately
                    logging.error(f"❌ Non-rate-limit error on {model_name}: {e}")
                    raise e
    
    # All models exhausted
    logging.error(f"❌ All models exhausted. Last error: {last_exception}")
    raise last_exception or Exception("All fallback models failed")


def get_default_model() -> str:
    """Returns the default (primary) model name."""
    return DEFAULT_FALLBACK_MODELS[0]


def get_fallback_models() -> List[str]:
    """Returns the list of fallback models."""
    return DEFAULT_FALLBACK_MODELS.copy()
