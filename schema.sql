-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Conversations table
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Prompts table (User messages)
CREATE TABLE IF NOT EXISTS prompts (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    prompt TEXT NOT NULL,
    image_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- AI Responses table
CREATE TABLE IF NOT EXISTS ai_responses (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    short_message TEXT,
    explanation TEXT,
    status VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Product Data table (Catalog)
CREATE TABLE IF NOT EXISTS product_data (
    id SERIAL PRIMARY KEY, -- Assuming integer ID, change to VARCHAR if needed
    title VARCHAR(255),
    url TEXT,
    price DECIMAL(10, 2),
    image_link TEXT,
    brand VARCHAR(255),
    material VARCHAR(255),
    description TEXT, -- Inferred from usage in embeddings
    embedding VECTOR(512) -- Assuming 512 dim for CLIP/Text embedding, adjust as needed
);

-- Outfit Suggestions (Link between AI response and Products)
CREATE TABLE IF NOT EXISTS outfit_suggestion (
    id SERIAL PRIMARY KEY,
    ai_response_id INTEGER REFERENCES ai_responses(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES product_data(id) ON DELETE CASCADE,
    outfit_index INTEGER DEFAULT 0,
    budget DECIMAL(10, 2), -- Storing per-outfit budget
    UNIQUE(ai_response_id, product_id, outfit_index)
);

-- Preferences table (Master list of preferences)
CREATE TABLE IF NOT EXISTS preferences (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL
);

-- User Preferences table
CREATE TABLE IF NOT EXISTS user_preference (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    preference_id INTEGER REFERENCES preferences(id) ON DELETE CASCADE,
    value VARCHAR(255),
    PRIMARY KEY (user_id, preference_id)
);

-- Initial Data for Preferences (Example)
INSERT INTO preferences (name) VALUES 
('favorite_color'),
('style'),
('budget_range')
ON CONFLICT DO NOTHING;
