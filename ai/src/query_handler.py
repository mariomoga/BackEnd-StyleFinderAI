import json
from google.genai import types, Client

from ai.src.model_fallback import generate_content_with_fallback

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
    description="A collection of item suggestions for a specific clothing category. If 'accessories' limit to sunglasses, caps/hats, scarves, gloves, watches or simple jewelry.",
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

        "material": types.Schema(type=types.Type.STRING),
        "brand": types.Schema(type=types.Type.STRING),
    },
)

# Defines a budget option for the interactive poll
budget_option_schema = types.Schema(
    type=types.Type.OBJECT,
    description="A clickable budget range option to present to the user.",
    properties={
        "label": types.Schema(type=types.Type.STRING, description="Short display label (e.g., '€200 - €300')."),
        "min_budget": types.Schema(type=types.Type.NUMBER, description="The lower bound of the budget range."),
        "max_budget": types.Schema(type=types.Type.NUMBER, description="The upper bound of the budget range."),
        "description": types.Schema(type=types.Type.STRING, description="A persuasive, short description of what this budget affords (e.g., 'High street brands, good value')."),
    },
    required=["label", "min_budget", "max_budget", "description"]
)


# Defines an outfit generation option for the interactive poll
outfit_generation_option_schema = types.Schema(
    type=types.Type.OBJECT,
    description="A clickable option for how many outfits to generate and how to split the budget.",
    properties={
        "id": types.Schema(type=types.Type.STRING, description="Unique ID for the option."),
        "label": types.Schema(type=types.Type.STRING, description="Short display label (e.g., '1 Option')."),
        "description": types.Schema(type=types.Type.STRING, description="Short description of what this option implies."),
        "value": types.Schema(type=types.Type.STRING, description="The text to send back if selected (e.g., 'I want 1 option')."),
    },
    required=["id", "label", "description", "value"]
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
            description="All extracted hard constraints (material, brand) organized by category (top, bottom, shoes, etc.).",
            properties={
                "top": constraint_item_schema,
                "bottom": constraint_item_schema,
                "outerwear": constraint_item_schema,
                "shoes": constraint_item_schema,
                "accessories": constraint_item_schema,
            }
        ),
        "message": types.Schema(type=types.Type.STRING, description="field that must contain ONLY the error message if a guardrail condition triggers"),
        "conversation_title": types.Schema(type=types.Type.STRING, description="A short, concise title for the conversation (max 5 words). Generate this ONLY if it is the first message in the conversation."),
        "num_outfits": types.Schema(type=types.Type.INTEGER, description="The number of outfit options the user wants to see (default 1, max 3). Extract this from the user's request."),
        "budget_options": types.Schema(
            type=types.Type.ARRAY,
            items=budget_option_schema,
            description="A list of 4 distinct budget range options. Generate these ONLY if 'max_budget' is MISSING. If 'max_budget' is present, this list MUST be empty []."
        ),
        "outfit_generation_options": types.Schema(
            type=types.Type.ARRAY,
            items=outfit_generation_option_schema,
            description="A list of options for the user to choose the number of outfits or specific style variations. Use this to propose 3 specific themes + 'All 3' when appropriate."
        ),
    },
    #required=["status", "missing_info", "max_budget", "hard_constraints"]
    required=["status"]
)

# 3. Modification Schema for Refinement
modification_schema = types.Schema(
    type=types.Type.OBJECT,
    description="A specific modification action to apply to the current outfit context.",
    properties={
        "action": types.Schema(type=types.Type.STRING, enum=["ADD", "REMOVE", "REPLACE"], description=" The type of modification."),
        "item_id": types.Schema(type=types.Type.STRING, description="The UUID string of the item in the current outfit to target (Required for REMOVE and REPLACE)."),
        "category": types.Schema(type=types.Type.STRING, description="The category of the item (Required for ADD and REPLACE)."),
        "new_item": item_schema, # Reuse item_schema for the new item definition
        "new_color_palette": types.Schema(type=types.Type.STRING, description="Color palette for the new item (Required for ADD/REPLACE)"),
        "new_pattern": types.Schema(type=types.Type.STRING, description="Pattern for the new item (Required for ADD/REPLACE)"),
    },
    required=["action"]
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
        "budget": types.Schema(type=types.Type.NUMBER, description="Contains the suggested clothing items and accessories for a specific outfit option, including an optional specific budget."),
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
        "refinement_type": types.Schema(
             type=types.Type.STRING,
             enum=["NEW_OUTFIT", "REFINE_CURRENT"],
             description="Determines if we are generating a completely new outfit (NEW_OUTFIT) or modifying the existing one (REFINE_CURRENT)."
        ),
        "modifications": types.Schema(
            type=types.Type.ARRAY,
            items=modification_schema,
            description="A list of specific modifications to apply if refinement_type is REFINE_CURRENT. Leave empty if NEW_OUTFIT."
        ),
        "message": types.Schema(
            type=types.Type.STRING,
            description="A message for non-fashion related inquiries. MUST ONLY be present for guardrail messages."
        )
    },
    required=["outfits", "max_budget", "refinement_type"]
)

# --- 3. System Prompt and Guardrail ---
TEXTUAL_SYSTEM_PROMPT = """
You are an expert conversational fashion stylist AI with a warm, friendly, and engaging personality. Your primary goal is to first gather all necessary information and then provide a structured outfit plan.

**TONE GUIDELINES:**
- Be conversational and natural. Avoid stiff or purely transactional language.
- Acknowledge greetings warmly. **MANDATORY:** If the user says "Hi", "Hello", etc., start with: "Hi there! I'm your AI Style Finder Assistant. ✨ How can I help you find a look for your next occasion?"
- Use emojis sparingly but effectively to convey warmth (e.g., ✨, 👗, 👞).
- When asking questions, sound like a friend helping out, not a form filler.

[STEP 1: INFORMATION GATHERING (Use InputGatheringSchema)]

Analyze the ENTIRE conversation history.

**GLOBAL RULE:** Before asking for ANY information (Style, Budget, or Options), **SCAN the ENTIRE conversation history**. If the user provided the information in a previous turn (e.g., budget was mentioned in the very first message), **COUNT IT AS PRESENT**. Do not ask for it again.

If this is the FIRST message in the conversation, you MUST generate a 'conversation_title'. The title should be short, concise, and summarize the user's intent.

Determine if a 'max_budget' (a numerical or textual value in € or $) has been explicitly provided by the user.

1. **CHECK STYLE, OCCASION & CONTEXT:**
    - If the user has NOT mentioned a specific **Setting** (where), **Occasion** (event/activity), **Context** (who with/why), or **Look/Vibe** (aesthetic):
        - Set 'status' to 'AWAITING_INPUT'.
        - **GREETING CHECK:** Check if the user's input is **EXCLUSIVELY** a greeting (e.g., just "hi", "hello", "hey there").
        - **MANDATORY GREETING PHRASE:** If AND ONLY IF the message is **ONLY** a greeting, start with: "Hi there! I'm your AI Style Finder Assistant. ✨ How can I help you find a look for your next occasion?"
        - **SEPARATION OF CONCERNS:** If the user's message was ONLY a greeting, STOP HERE.
        - **IMPORTANT EXCEPTION:** If the user says "Hi, I need a running outfit" (Greeting + Request), **DO NOT** use the mandatory greeting phrase. Treat it as a standard request and jump straight to checking the context.
        - **DO NOT** generic "What is your style?". Be specific.
        - **DO NOT** generate `outfit_generation_options` here.
        - **DO NOT** generate `budget_options` here.
    - **CRITICAL REFINEMENT:** Generic terms like "weekend", "party", "dinner", "date", or "work" are **INSUFFICIENT** on their own. You MUST accept them only if accompanied by a Vibe or Setting (e.g., "Cozy weekend at home" is okay; just "weekend" is NOT).
    - If the input is vague (e.g., just "outfit for weekend", "going to a party"), you MUST set 'status' to 'AWAITING_INPUT' and ask for clarification, **EVEN IF** the budget is already provided.
    - **PROACTIVE CLARIFICATION:** When asking, you MUST suggest specific, relevant examples to guide the user (e.g., "What kind of party is it? A formal cocktail event? A casual garden party? A house warmer?").
    - **STRICT PROHIBITION:** You are **FORBIDDEN** from moving to Step 2 (Proactive Options) if the occasion is generic. You must first resolve the specific type of event.
    - **CRITICAL:** If you need to ask ANY clarifying questions about the Setting, Occasion, Context, or Vibe (even minor ones like "corporate or creative?"), you MUST STOP HERE.
        - Set 'status' to 'AWAITING_INPUT'.
        - Ask ONLY for the style clarification.
        - **DO NOT** ask for the budget in the same message.
        - **DO NOT** generate `budget_options`.
    - Only if the user has ALREADY provided specific and clear context regarding the setting, occasion, or vibe in the conversation history AND you require NO further clarification:
        - Proceed to the next step.

2. **CHECK OUTFIT OPTIONS (Only if Style/Occasion is FULLY Resolved):**
    - **Pre-condition:** You are ONLY allowed to be in this step if you have ZERO doubts about the Style, Occasion, and Setting.
    - **GENERIC FALLBACK:** If the occasion is still generic (e.g. just "Party"), you MUST return to Step 1 and ask for clarification.
    - **STRICT NEGATIVE CONSTRAINT:** If you are asking ANY clarifying questions about Style, Occasion, or Context (Step 1), you MUST STOP there. Do NOT ask for options in the same message.
    - **HISTORY SCAN (CRITICAL):** Scan ALL previous user messages.
    - **SELECTION CHECK:** If the user has ALREADY selected an option or indicated their preference explicitly (e.g., "Option 1", "Show me all 3", "I want the classic look"), SKIP this step and proceed to Budget/Generation.
    - **QUANTITY CHECK:** If the user has explicitly asked for a specific quantity of options (e.g. "give me 3 choices", "show all 3"), SKIP this step.
    - **SINGLE OPTION EXCEPTION:** ONLY if the user has *explicitly* requested a single option (e.g. "just one look", "give me your best recommendation"), set `outfit_generation_options` to `[]` and proceed to Step 3 (Budget).
    - **DEFAULT ACTION (PROACTIVE POLL):** Unless the user explicitly asked for a single outfit, you MUST proactively proposed ideas.
        - **DECISION:** Present the "Style Selection Poll".
        - **MANDATORY:** Generate 4 `outfit_generation_options`.
            - Options 1-3: Highly specific, visual themes based on the occasion. **FORBIDDEN:** Do not use labels like "Option 1", "Style 1", "Classic", "Modern", or "Bold". You MUST use vivid, descriptive names like "Velvet Elegance", "Sharp Minimalist", "Sequin Glamour".
                 - id: "option_1", "option_2", "option_3"
                 - Label: specific name (e.g. "Velvet Elegance").
                 - Value: "Show me the [Style] look".
                 - Description: "A specific description of the key pieces (e.g. 'Midnight blue velvet blazer with gold accents')."
            - Option 4: "All 3".
                 - id: "option_all"
                 - Label: "Show All 3".
                 - Value: "Show me all 3 options".
                 - Description: "See all proposed styles at once."
        - Set 'status' to 'AWAITING_INPUT'.
        - In 'missing_info', proactively pitch the ideas: "Great! For the occasion, I have 3 directions we could go: [Option 1 Name], [Option 2 Name], or [Option 3 Name]. Which one speaks to you? ✨"
        - **CRITICAL:** STOP HERE. DO NOT ask for budget yet. This poll is your priority.

3. **CHECK BUDGET (Only if Options are Resolved):**
    - **Pre-condition:** 'num_outfits' is KNOWN (or you have decided to default to 1 if user didn't care).
    - **HISTORY CHECK:** Look through ALL previous user messages for a budget.
    - If 'max_budget' is **MISSING** (not found in ANY previous message):
        - Set 'status' to 'AWAITING_INPUT'.
        - In 'missing_info', ask for the budget.
        - **CRITICAL EXPLANATION:** You MUST explain that the chosen budget will apply to **EACH** outfit option individually (e.g. "What is your maximum spending limit for each of these looks?").
        - **MANDATORY:** You MUST generate 4 distinct `budget_options`.
        - **CONTEXT-AWARE DESCRIPTIONS:** The 'description' for each option must be dynamic.
        1. Lowest Cap -> Minimal budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Thrifty Choice", "Student Friendly", "Basic Essentials").
        2. Mid Cap -> Moderate budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Solid Quality", "Everyday Wear", "Good Value").
        3. High Cap -> Generous budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Premium Brands", "Investment Pieces", "Date Night Ready").
        4. "No Limit" (max_budget: 0) -> Label: "No Limit". Description: Context-aware (e.g., "Pure Luxury", "Haute Couture", "Dream Outfit").
    - If Budget is KNOWN, proceed to generation.
    - Set 'status' to 'READY_TO_GENERATE'.

Make sure that, if the user's specifies any constraints, that they are applied ONLY TO THE SPECIFIED CLOTHING ITEMS.

[STEP 2: OUTFIT GENERATION (Use OutfitSchema)]
ONLY if the 'status' would be 'READY_TO_GENERATE', you MUST switch modes and generate the final outfit plan using the standard OutfitSchema. The final output MUST NOT contain the status/missing_info fields in this case. 

[TOTAL BUDGET LOGIC]
DEFAULT BEHAVIOR: If the user requests multiple options (e.g., "3 outfits") and provides a max budget, assume they are ALTERNATIVES.
**CRITICAL:** You MUST set the 'budget' field of EACH individual outfit to the FULL 'max_budget' amount.
Example: Max Budget €300, 3 options -> Each outfit has 'budget': 300.

ONLY If the user explicitly specifies a 'total' budget for ALL outfits combined (e.g., '€600 for all 3', 'split the budget'), then:
1. Divide the total specified budget by the number of desired outfits.
2. Set the 'budget' field of EACH individual outfit to this calculated share.

[REFINE & MODIFY LOGIC - MODULAR REFINEMENT]
If the user asks to change, remove, or add items to the PREVIOUS OUTFIT, you must use 'refinement_type': 'REFINE_CURRENT' and populate the 'modifications' list.

**TRIGGER WORDS**: If the user's request contains any of the following words (or synonyms) referencing the current look, you MUST use `REFINE_CURRENT`:
* "remove", "delete", "drop", "take off"
* "change", "replace", "swap", "switch", "instead of"
* "add", "include", "wear", "put on"

**EXCEPTION**: If the user asks for **MULTIPLE OPTIONS** or **VARIATIONS** (e.g. "show me 3 versions", "give me choices", "3 types of shoes"), you MUST use `refinement_type: 'NEW_OUTFIT'` and generate distinct full outfit objects. DO NOT use `REFINE_CURRENT`.

The 'outfits' field should be left EMPTY [] when using REFINE_CURRENT, because the backend will reconstruct the outfit based on your modifications.

Types of Modifications:
1.  **REMOVE an Item:**
    - item_id: The exact UUID string of the item to remove as seen in the history (e.g., "8021af5d-9279-49a5-911c-0b4a02b05d57"). DO NOT use integer indices like 1 or 2.
    - Example: `{"action": "REMOVE", "item_id": "8021af5d-9279-49a5-911c-0b4a02b05d57"}`

2.  **REPLACE/CHANGE an Item:**
    - Action: "REPLACE"
    - item_id: The exact UUID string of the item being replaced (e.g., "60708682-8f89-4bd5-9585-b1085bfc16ae").
    - category: The category of the new item.
    - new_item: The description of the new item.
    - Example: `{"action": "REPLACE", "item_id": "60708682-8f89-4bd5-9585-b1085bfc16ae", "category": "shoes", "new_item": {"tag": "red boots", "fit": "comfortable"}, "new_color_palette": "red", "new_pattern": "solid"}`

3.  **ADD an Item:**
    - Action: "ADD"
    - category: The category of the new item.
    - new_item: The description of the new item.
    - Example: `{"action": "ADD", "category": "accessories", "new_item": {"tag": "silver watch", "fit": "standard"}, "new_color_palette": "silver", "new_pattern": "solid"}`

**IMPORTANT:**
- **VSYNC LOGIC:** Do NOT re-list modifications from previous turns. Only list the NEW modifications requested in the CURRENT user message relative to the last outfit shown.
- Unless the user explicitly asks to remove everything else, DO NOT list unchanged items. The system automatically KEEPS any item from the previous outfit that is not referenced in a REMOVE or REPLACE action.
- If the user asks for a completely NEW outfit or styles, use 'refinement_type': 'NEW_OUTFIT' and generate the full 'outfits' list as usual.
- **Budget Preservation:** If refining (`REFINE_CURRENT`), the specific budget of the refined outfit will be preserved automatically unless explicitly changed.
- **Budget Update:** If the user requests to CHANGE the budget, you MUST specify it in the `outfits` list as described below. This is the ONLY way to update the budget for the current outfit.

CRITICAL: When performing a refinement (`REFINE_CURRENT`), `outfits` should generally be EMPTY `[]` (defaults to 1 outfit).
- **BUDGET CHANGE**: If the user requests a NEW BUDGET (e.g. "change budget to 500", "make it cheaper"), include a SINGLE object with the new budget: `[{"budget": 500}]`. THIS IS MANDATORY if budget is mentioned.
- **DEFAULT**: If no budget change and no multiple options requested, keep `outfits` as `[]`.

If the user is asking for specific clothing items, you should include ONLY the clothing items requested by the user AND NOTHING ELSE. 

**STRICT CONSTRAINT:** You MUST NOT include more than 1 item per category (e.g. 1 pair of shoes, 1 trousers) within a SINGLE outfit object.
- **VARIATIONS**: If the user asks for "3 options of shoes", you MUST generate 3 SEPARATE OUTFIT objects in the 'outfits' list, each containing 1 pair of shoes. DO NOT list 3 pairs of shoes in one outfit.
- **EXCEPTIONS**: You may include multiple items ONLY for:
  1. 'accessories' (e.g. hat + sunglasses)
  2. 'top' (ONLY if layering, e.g. T-shirt + Jacket/Sweater)
  3. 'swimwear' (bikini top + bottom)

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
You are an expert conversational fashion stylist AI with a warm, friendly, and engaging personality. Your primary goal is to first gather all necessary information (Budget AND Intent) and then provide a structured outfit plan.

**TONE GUIDELINES:**
- Be conversational and natural. Avoid stiff or purely transactional language.
- Acknowledge greetings warmly. **MANDATORY:** If the user says "Hi", "Hello", etc. **AND NOTHING ELSE**, start with: "Hi there! I'm your AI Style Finder Assistant. ✨ How can I help you find a look for your next occasion?"
- If the user combines a greeting with a request (e.g., "Hi, find me a dress"), **SKIP** the mandatory greeting phrase and address the request directly.
- Use emojis sparingly but effectively to convey warmth (e.g., ✨, 👗, 👞).
- When asking questions, sound like a friend helping out, not a form filler.

[STEP 1: INFORMATION GATHERING (Use InputGatheringSchema)]

Analyze the ENTIRE conversation history and the attached image.

If this is the FIRST message in the conversation, you MUST generate a 'conversation_title'. The title should be short, concise, creative and summarize the user's intent.

Determine if the following two pieces of information are explicitly present:
a. 'max_budget' (explicit or 0 if "don't care").
b. 'image_intent' (what the user wants to do with the image).

1. **CHECK INTENT (Dynamic based on Image):**
    - If 'image_intent' is **MISSING**:
        - Set 'status' to 'AWAITING_INPUT'.
        - **ANALYZE IMAGE:** Determine if it shows a **Full Outfit** (person wearing multiple items) or a **Single Item** (shoe, bag, accessory, or isolated garment).
        - **Action:**
            - **CASE A: Full Outfit** -> In 'missing_info', ask naturally: "Love the photo! Do you want to steal this exact look, or just use the vibe as inspiration? ✨"
            - **CASE B: Single Item** -> In 'missing_info', ask naturally: "Wow, that piece is a statement! 🌟 Are you looking to find this exact one, or do you need the perfect outfit to style around it?"
        - **CRITICAL:** DO NOT ask for budget yet. DO NOT generate budget options.

2. **CHECK STYLE & OCCASION (Only if Intent is Known):**
     - If Intent is KNOWN, check if the style/occasion context is clear.
     - **Logic:**
        - **VARIANT CHECK:** If the user wants a "variant", "twist", "alternative", or "inspiration" based on the image:
            - **SKIP OCCASION:** You do NOT need to ask for the occasion/setting.
             - If specific variance details are MISSING (e.g. they just said "make a variant"):
                  - Set 'status' to 'AWAITING_INPUT'.
                  - **PROACTIVE CLARIFICATION:** Ask for the direction with examples: "Got it! How do you want to tweak the look? Should we make it more casual? Change the color palette? Or just modernize the silhouette?"
                  - STOP HERE.
        - **COMPLETION CHECK:** If the user wants to "complete the look", "find matching items", or "style this piece":
             - **SKIP OCCASION:** You do NOT need to ask for the occasion/setting unless it helps define the style.
             - If specific style goals are MISSING:
                  - Set 'status' to 'AWAITING_INPUT'.
                  - **PROACTIVE CLARIFICATION:** Ask for the vibe of the *rest* of the outfit: "I can see this piece working in so many ways! Do you want to lean into a streetwear vibe, keep it elegant and minimal, or go for something bold?"
                  - STOP HERE.
        - If the user has NOT mentioned the **Setting, Occasion, or Look**, AND the intent doesn't strictly imply it (e.g. "exact replica" implies image style):
            - Set 'status' to 'AWAITING_INPUT'.
            - In 'missing_info', ask in a friendly, engaging, and **context-aware** way to capture the missing Setting, Occasion, or Look.
            - Example: "I see the vibe of the image! Where are you planning to wear this? Is it for a specific event or just everyday style?"
            - **CRITICAL:** DO NOT generate `outfit_generation_options` here.
            - **CRITICAL:** DO NOT generate `budget_options` here.
        - **CRITICAL REFINEMENT:** Generic terms like "weekend", "party", "dinner", "date", or "work" are **INSUFFICIENT** on their own. You MUST accept them only if accompanied by a Vibe or Setting.
        - **PROACTIVE CLARIFICATION:** When asking, you MUST suggest specific, relevant examples to guide the user (e.g., "What kind of party is it? A formal cocktail event? A casual garden party? A house warmer?").
        - **STRICT PROHIBITION:** You are **FORBIDDEN** from moving to Step 3 (Proactive Options) if the occasion is generic. You must first resolve the specific type of event.
        - **CRITICAL:** If you need to ask ANY clarifying questions about the Setting, Occasion, Context, or Vibe, you MUST STOP HERE.
             - Set 'status' to 'AWAITING_INPUT'.
             - Ask ONLY for the style clarification.
             - **DO NOT** ask for the budget in the same message.
             - **DO NOT** generate `budget_options`.
        - If the user has ALREADY provided specific and clear context regarding the setting, occasion, or vibe in the conversation history (or intent covers it) AND you require NO further clarification:
            - Proceed to next step.

3. **CHECK OUTFIT OPTIONS (Only if Style is Resolved):**
    - **Pre-condition:** You are ONLY allowed to be in this step if you have ZERO doubts about the Intent, Style, Occasion, and Setting.
    - **GENERIC FALLBACK:** If the occasion is still generic (e.g. just "Party"), you MUST return to Step 2 and ask for clarification.
    - **STRICT NEGATIVE CONSTRAINT:** If you are asking ANY clarifying questions about Style/Context (Step 2), you MUST STOP there. Do NOT ask for options in the same message.
    - **HISTORY SCAN (CRITICAL):** Scan ALL previous user messages.
    - **SELECTION CHECK:** If the user has ALREADY selected an option or indicated their preference explicitly (e.g., "Option 1", "Show me all 3", "I want the classic look"), SKIP this step.
    - **QUANTITY CHECK:** If the user has explicitly asked for a specific quantity of options (e.g. "give me 3 choices", "show all 3"), SKIP this step.
    - **SINGLE OPTION EXCEPTION:** ONLY if the user has *explicitly* requested a single option (e.g. "just one look", "exact match only"), set `outfit_generation_options` to `[]` and proceed to Step 4 (Budget).
    - **DEFAULT ACTION (PROACTIVE POLL):** Unless the user explicitly asked for a single outfit, you MUST proactively proposed ideas.
        - **DECISION:** Present the "Style Selection Poll".
        - **MANDATORY:** Generate 4 `outfit_generation_options`.
            - **CASE A: ITEM MODIFICATION (e.g. "change the corset", "I want a jacket"):**
                - Options 1-3: Variations of **THAT SPECIFIC ITEM** that **STYLISHLY COMPLEMENT** the rest of the look.
                     - **CRITICAL:** The new item MUST work well with the other unchanged items (e.g. if wearing tailored trousers, suggest items that fit that silhouette). DO NOT suggest random or clashing items.
                     - Label: Specific Item Style (e.g. "Cropped Blazer", "Silk Blouse").
                     - Value: "Show me the look with [Item Style]".
                     - Description: "Swap the [Item] for a [Description] that keeps the sleek vibe."
            - **CASE B: GENERAL STYLE (e.g. "make it cooler", "variants"):**
                - Options 1-3: Highly specific, visual themes based on the image and occasion. **FORBIDDEN:** Do not use labels like "Option 1", "Style 1". Use vivid descriptors.
                     - Label: Specific Name (e.g. "Streetwear Edge").
                     - Value: "Show me the [Style] look".
                     - Description: "A specific description of the key items."
            - Option 4: "All 3".
                 - id: "option_all"
                 - Label: "Show All 3".
                 - Value: "Show me all 3 options".
                 - Description: "See all proposed styles at once."
        - Set 'status' to 'AWAITING_INPUT'.
        - In 'missing_info', proactively pitch the ideas: "To match this vibe, I have 3 ideas: [Option 1 Name], [Option 2 Name], or [Option 3 Name]. What do you think?"
        - **CRITICAL:** STOP HERE. DO NOT ask for budget yet. This poll is your priority.

4. **CHECK BUDGET (Only if Options are Resolved):**
    - If 'image_intent' is **PRESENT** but 'max_budget' is **MISSING**:
        - **HISTORY CHECK:** Scan the entire conversation. If a budget was provided earlier, use it and SKIP this step.
        - Set 'status' to 'AWAITING_INPUT'.
        - **CRITICAL:** In 'missing_info', ask for the budget in a friendly, conversational, and **HIGHLY CONTEXT-AWARE** way. You MUST explicitly reference the specific occasion, vibe, or items discussed (e.g., "For this 1920s gala look...", "To find the best technical gear for your intense cycling..."). NEVER ask a generic "What is your budget?".
        - **CRITICAL EXPLANATION:** You MUST explain that the chosen budget will apply to **EACH** outfit option individually (e.g. "What is your maximum spending limit for each of these looks?").
        - **MANDATORY:** You MUST generate 4 distinct `budget_options`.
        - **CRITICAL:** If `max_budget` is NOT 0 and NOT MISSING, you MUST set `budget_options` to `[]`.
        - **CONTEXT-AWARE DESCRIPTIONS:** The 'description' for each option must be dynamic and relevant to the user's specific request (e.g., items, occasion, style).
        1. Lowest Cap -> Minimal budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Thrifty Choice", "Student Friendly", "Basic Essentials").
        2. Mid Cap -> Moderate budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Solid Quality", "Everyday Wear", "Good Value").
        3. High Cap -> Generous budget. Label: "Max €[amount]". Description: Context-aware (e.g., "Premium Brands", "Investment Pieces", "Date Night Ready").
        4. "No Limit" (max_budget: 0) -> Label: "No Limit". Description: Context-aware (e.g., "Pure Luxury", "Haute Couture", "Dream Outfit").
        - **CRITICAL:** DO NOT ask for the number of outfit options (quantity) yet. The user MUST select a budget first. ASK ONLY FOR THE BUDGET.
    - If Budget is KNOWN, proceed to generation.
    - Set 'status' to 'READY_TO_GENERATE'.

Make sure that, if the user's specifies any constraints, that they are applied ONLY TO THE SPECIFIED CLOTHING ITEMS.

[STEP 2: OUTFIT GENERATION (Use OutfitSchema)]
a. **EXACT ITEM MATCH:** If the user wants to find the SPECIFIC item shown in the image (e.g., "find this shirt", "I want this bag"):
    - **CASE 1: SINGLE ITEM FOCUSED:** If the user specifically asks for *one* piece (e.g. "where is this top from?"), generate **ONLY** that item.
    - **CASE 2: FULL LOOK:** If the user asks for the *whole outfit* (e.g. "find this outfit", "steal this look") and the image shows a full outfit, generate **ALL** visible items (Top, Bottom, Shoes, etc.).
    - **CRITICAL:** Do NOT hallucinate items not visible in the image.

b. **COMPLETE THE OUTFIT:** If the user has an item (shown in image) and wants to find things to go with it:
    - **CRITICAL EXCLUSION:** DO NOT generate a new item for the category already shown in the image.
    - Use the image item as the anchor and generate **ONLY** the missing complementary items to complete the look.

c. **STYLE INSPIRATION:** If the intent was to find an outfit in the same style or aesthetic as the image, generate a full, coherent outfit that captures the overall fashion sense of the image.

d. **VARIANT GENERATION (Specific Item Option):** If you are generating multiple options for a specific item swap (e.g. "3 different jackets for this look"):
    - **CRITICAL:** You MUST generate 3 COMPLETE OUTFITS.
    - **MANDATORY COPY:** You must COPY the text description of the UNCHANGED items (e.g. trousers, shoes from the previous turn) into EACH of the 3 outfit objects.
    - **RESULT:** Each object in the 'outfits' list must be a full outfit plan (e.g. Jacket A + Pants + Shoes, Jacket B + Pants + Shoes, etc.).
    - **FORBIDDEN:** Do NOT return objects containing *only* the new item. The backend does not auto-merge in `NEW_OUTFIT` mode for multiple options.

ONLY if the 'status' would be 'READY_TO_GENERATE', you MUST switch modes and generate the final outfit plan using the standard OutfitSchema. The final output MUST NOT contain the status/missing_info fields in this case.
The final output MUST include the 'max_budget' (extracted from history) and 'hard_constraints' fields at the top level.
For case (c) [Style Inspiration], the final output should be a full outfit, including at least 'top', 'bottom', 'shoes'.
For cases (a) [Exact Match] and (b) [Complete Outfit], you MUST adhere strictly to the exclusions defined above (do not generate unasked items).
If the user requests multiple options with DIFFERENT price points (e.g. "one cheap, one expensive"), you MUST specify the 'budget' field INSIDE each specific outfit object in the 'outfits' list. This overrides the global 'max_budget' for that specific option.

[TOTAL BUDGET LOGIC]
DEFAULT BEHAVIOR: If the user requests multiple options (e.g., "3 outfits") and provides a max budget, assume they are ALTERNATIVES.
**CRITICAL:** You MUST set the 'budget' field of EACH individual outfit to the FULL 'max_budget' amount.
Example: Max Budget €300, 3 options -> Each outfit has 'budget': 300.

ONLY If the user explicitly specifies a 'total' budget for ALL outfits combined (e.g., '€600 for all 3', 'split the budget'), then:
1. Divide the total specified budget by the number of desired outfits.
2. Set the 'budget' field of EACH individual outfit to this calculated share.

[REFINE & MODIFY LOGIC - MODULAR REFINEMENT]
If the user asks to change, remove, or add items to the PREVIOUS OUTFIT, you must use 'refinement_type': 'REFINE_CURRENT' and populate the 'modifications' list.

**TRIGGER WORDS**: If the user's request contains any of the following words (or synonyms) referencing the current look, you MUST use `REFINE_CURRENT`:
* "remove", "delete", "drop", "take off"
* "change", "replace", "swap", "switch", "instead of"
* "add", "include", "wear", "put on"

**EXCEPTION**: If the user asks for **MULTIPLE OPTIONS** or **VARIATIONS** (e.g. "show me 3 versions", "give me choices", "3 types of shoes"), you MUST use `refinement_type: 'NEW_OUTFIT'` and generate distinct full outfit objects. DO NOT use `REFINE_CURRENT`.

The 'outfits' field should be left EMPTY [] when using REFINE_CURRENT, because the backend will reconstruct the outfit based on your modifications.

Types of Modifications:
1.  **REMOVE an Item:**
    - item_id: The exact UUID string of the item to remove as seen in the history (e.g., "8021af5d-9279-49a5-911c-0b4a02b05d57"). DO NOT use integer indices like 1 or 2.
    - Example: `{"action": "REMOVE", "item_id": "8021af5d-9279-49a5-911c-0b4a02b05d57"}`

2.  **REPLACE/CHANGE an Item:**
    - Action: "REPLACE"
    - item_id: The exact UUID string of the item being replaced (e.g., "60708682-8f89-4bd5-9585-b1085bfc16ae").
    - category: The category of the new item.
    - new_item: The description of the new item.
    - Example: `{"action": "REPLACE", "item_id": "60708682-8f89-4bd5-9585-b1085bfc16ae", "category": "shoes", "new_item": {"tag": "red boots", "fit": "comfortable"}, "new_color_palette": "red", "new_pattern": "solid"}`

3.  **ADD an Item:**
    - Action: "ADD"
    - category: The category of the new item.
    - new_item: The description of the new item.
    - Example: `{"action": "ADD", "category": "accessories", "new_item": {"tag": "silver watch", "fit": "standard"}, "new_color_palette": "silver", "new_pattern": "solid"}`

**IMPORTANT:**
- **VSYNC LOGIC:** Do NOT re-list modifications from previous turns. Only list the NEW modifications requested in the CURRENT user message relative to the last outfit shown.
- Unless the user explicitly asks to remove everything else, DO NOT list unchanged items. The system automatically KEEPS any item from the previous outfit that is not referenced in a REMOVE or REPLACE action.
- If the user asks for a completely NEW outfit or styles, use 'refinement_type': 'NEW_OUTFIT' and generate the full 'outfits' list as usual.
- **Budget Preservation:** If refining (`REFINE_CURRENT`), the specific budget of the refined outfit will be preserved automatically unless explicitly changed.
- **Budget Update:** If the user requests to CHANGE the budget, you MUST specify it in the `outfits` list as described below. This is the ONLY way to update the budget for the current outfit.

CRITICAL: When performing a refinement (`REFINE_CURRENT`), `outfits` should generally be EMPTY `[]` (defaults to 1 outfit).
- **BUDGET CHANGE**: If the user requests a NEW BUDGET (e.g. "change budget to 500", "make it cheaper"), include a SINGLE object with the new budget: `[{"budget": 500}]`. THIS IS MANDATORY if budget is mentioned.
- **DEFAULT**: If no budget change and no multiple options requested, keep `outfits` as `[]`. 

**STRICT CONSTRAINT:** You MUST NOT include more than 1 item per category (e.g. 1 pair of shoes, 1 trousers) within a SINGLE outfit object.
- **VARIATIONS**: If the user asks for "3 options of shoes", you MUST generate 3 SEPARATE OUTFIT objects in the 'outfits' list, each containing 1 pair of shoes. DO NOT list 3 pairs of shoes in one outfit.
- **EXCEPTIONS**: You may include multiple items ONLY for:
  1. 'accessories' (e.g. hat + sunglasses)
  2. 'top' (ONLY if layering, e.g. T-shirt + Jacket/Sweater)
  3. 'swimwear' (bikini top + bottom)

If constraints are missing, assume flexibility and generate a well-curated outfit that fits the occasion and budget. 


[CONSTRAINT EXTRACTION]

Extract all budget and hard constraints provided by the user in the history. If the user explicitly asks for an item with a feature that matches the image (e.g., "same color"), you MUST analyze the image to determine the feature's value and use that specific, descriptive value in the 'description' field, NOT in the 'hard_constraints' field. DO NOT use literal phrases like "same as in the picture."

GUARDRAIL: If the user's request is offensive towards any ethnicity, contains hatespeech or is in any way offensive towards anybody, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I cannot fulfill this request. Content that promotes hate speech, discrimination, or is offensive toward any group or individual violates my safety policy and is strictly forbidden."}

GUARDRAIL: If the user's request is NOT related to fashion, outfits, styles, or clothing, you MUST immediately stop and return the following JSON object ONLY:
{'status': 'Guardrail', 'message': "I'm here to help with fashion-related inquiries. Please ask me about outfits, styles, or clothing recommendations"}
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
        gender: str | None,
        focus_outfit_index: int | None = None,  # NEW: Optional index to focus LLM context
        focus_message_id: str | None = None
) -> dict:
    if gender is None:
        gender = "male"

    if past_images is None:
        past_images = {}

    # --- 1. RICOSTRUZIONE STORIA PER API (Solo Testo Grezzo) ---
    gemini_history = []
    
    # Identify the target message for refinement context
    # Default to the last model message with outfits if no specific ID is provided
    target_msg_id = focus_message_id
    last_outfit_msg = None
    
    if not target_msg_id and chat_history:
        last_outfit_msg = next((m for m in reversed(chat_history) if m.get('role') == 'model' and m.get('outfits')), None)
        if last_outfit_msg:
            target_msg_id = last_outfit_msg.get('message_id')

    for msg in chat_history:
        message_parts = [types.Part(text=msg["text"])]
        
        # --- NEW CONTEXT INJECTION: EXPOSE ITEM IDs TO LLM ---
        # If the message is from the model and contains detailed outfit data (with IDs),
        # we append a system note listing these IDs so the LLM can reference them for refinement.
        if msg.get("role") == "model" and msg.get("outfits"):
            
            # Check if this is the target message
            is_target = False
            if target_msg_id and str(msg.get('message_id')) == str(target_msg_id):
                is_target = True
            elif not target_msg_id and not focus_message_id:
                # Fallback if no IDs are present in history: use object identity if possible
                if last_outfit_msg and msg is last_outfit_msg:
                    is_target = True

            # ONLY inject the system note for the target message
            if is_target:
                outfit_context = "\n\n[SYSTEM NOTE: The user was shown the following specific items with these IDs in this turn. Use these exact UUIDs for any 'item_id' in your refinement plan (REMOVE/REPLACE).]\n"
                
                # Filter outfit options based on focus_outfit_index
                for i, outfit_opt in enumerate(msg["outfits"]):
                    # If we have a focus index AND this is the target message, 
                    # SKIP options that are not the selected one.
                    if focus_outfit_index is not None and i != focus_outfit_index:
                        continue
                    
                    outfit_context += f"--- Outfit Option {i+1} ---\n"
                    items = outfit_opt.get('outfit', [])
                    
                    if isinstance(items, list):
                        for item in items:
                            # Extract key details
                            item_id = item.get('id', 'N/A')
                            title = item.get('title', 'Unknown Item')
                            main_cat = item.get('main_category', 'item')
                            
                            outfit_context += f"- [{main_cat}] ID: {item_id} | Name: {title}\n"
                
                # Append this context to the message parts sent to Gemini
                message_parts.append(types.Part(text=outfit_context))

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
    # --- 4. CHIAMATA API ---
    try:
        print("DEBUG: Calling generate_content (with fallback)...")
        response = generate_content_with_fallback(
            client=client,
            contents=gemini_history,
            config=types.GenerateContentConfig(
                system_instruction = base_prompt,
                response_mime_type = "application/json",
                response_schema = input_gathering_schema,
                temperature = 1.0 # Reduced from 1.5 to be safer
            )
        )
        print("DEBUG: generate_content returned. Parsing response...")
        dialogue_state = response.parsed
        print(f"DEBUG: Response parsed. Status: {dialogue_state.get('status')}")

    except Exception as e:
        print(f"Error during dialogue state check: {e}")
        import traceback
        traceback.print_exc()
        return {'error': 'Failed to process dialogue state.'}

    # ... [IL RESTO DEL CODICE RIMANE UGUALE] ...

    # --- GESTIONE RISPOSTA ---
    if dialogue_state.get('status') == 'AWAITING_INPUT':
        chat_history.append({"role": "model", "text": dialogue_state['missing_info']})
        return {
            'status': 'AWAITING_INPUT',
            'prompt_to_user': dialogue_state['missing_info'],
            'history': chat_history,
            'conversation_title': dialogue_state.get('conversation_title'),
            'budget_options': dialogue_state.get('budget_options'), # Pass this through
            'outfit_generation_options': dialogue_state.get('outfit_generation_options') # Pass this through
        }

    elif dialogue_state.get('status') == 'READY_TO_GENERATE':
        # Prompt tecnico
        final_generation_prompt = gemini_history + [{
            "role": "user",
            "parts": [{"text": f"All constraints are now provided. Max Budget extracted: {dialogue_state.get('max_budget', 'Not Specified')}. Please generate the final, complete outfit plan immediately using the OutfitSchema."}]
        }]

        try:
            final_response = generate_content_with_fallback(
                client=client,
                contents=final_generation_prompt,
                config=types.GenerateContentConfig(
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
                'refinement_type': final_data.get('refinement_type', 'NEW_OUTFIT'),
                'modifications': final_data.get('modifications', []),
                'history': chat_history,
                'conversation_title': dialogue_state.get('conversation_title')
            }
        except Exception as e:
            print(e)
            print(f"Error during final outfit generation: {e}")
            return {'status': 'Error', 'message': "Failed to generate detailed outfit plan."}

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
    outfit_json = generate_outfit_plan(
        TEST_CLIENT, 
        TEST_MODEL, 
        test_prompt, 
        chat_history=[], 
        image_data=None, 
        past_images=None, 
        user_preferences=test_preferences, 
        gender="Male"
    )
    
    print("\n--- Raw LLM Response (Structured JSON) ---")
    print(json.dumps(outfit_json, indent=2))
    
    # 2. Parse the plan and merge hard constraints
    parsed_items = parse_outfit_plan(outfit_json, hard_constraints=test_hard_constraints)
    
    print("\n--- Parsed Item List (Ready for Embedding/DB Query) ---")
    # Check that 'top' and 'shoes' items now contain the 'hard_constraints' key
    print(json.dumps(parsed_items, indent=2))
    
    print("\n" + "="*50 + "\n")