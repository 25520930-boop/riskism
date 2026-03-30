-- ============================================
-- RISKISM Database Initialization
-- ============================================

-- Users & Risk Profile
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    password_hash TEXT,
    firebase_uid VARCHAR(255) UNIQUE,
    email VARCHAR(255) UNIQUE,
    avatar_url TEXT,
    risk_appetite VARCHAR(20) DEFAULT 'moderate' CHECK (risk_appetite IN ('conservative', 'moderate', 'aggressive')),
    capital_amount DECIMAL(15,2) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;

-- Portfolio Holdings
CREATE TABLE IF NOT EXISTS portfolios (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    avg_price DECIMAL(12,2) NOT NULL DEFAULT 0,
    sector VARCHAR(50),
    added_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, symbol)
);

-- Market Data Cache
CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    open_price DECIMAL(12,2),
    high_price DECIMAL(12,2),
    low_price DECIMAL(12,2),
    close_price DECIMAL(12,2),
    volume BIGINT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(symbol, trade_date)
);

-- News Articles
CREATE TABLE IF NOT EXISTS news (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    source VARCHAR(50),
    url TEXT UNIQUE,
    content_summary TEXT,
    published_at TIMESTAMP WITH TIME ZONE,
    sentiment_score DECIMAL(4,3) DEFAULT 0 CHECK (sentiment_score >= -1 AND sentiment_score <= 1),
    impact_level VARCHAR(10) DEFAULT 'low' CHECK (impact_level IN ('low', 'medium', 'high', 'critical')),
    related_symbols TEXT[] DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- AI Insights
CREATE TABLE IF NOT EXISTS insights (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    insight_type VARCHAR(30) NOT NULL CHECK (insight_type IN ('risk_alert', 'daily_report', 'anomaly', 'morning_brief', 'afternoon_review')),
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    risk_level VARCHAR(10) CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    confidence_score DECIMAL(4,3) DEFAULT 0,
    related_symbols TEXT[] DEFAULT '{}',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Predictions (Self-reflection loop)
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    prediction_type VARCHAR(20) NOT NULL CHECK (prediction_type IN ('morning', 'afternoon_review')),
    content TEXT NOT NULL,
    predicted_symbols TEXT[] DEFAULT '{}',
    predicted_direction JSONB DEFAULT '{}',
    actual_result JSONB,
    accuracy_score DECIMAL(4,3),
    reflection_notes TEXT,
    predicted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE
);

-- Risk Snapshots (cached risk calculations)
CREATE TABLE IF NOT EXISTS risk_snapshots (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(10),
    snapshot_type VARCHAR(20) CHECK (snapshot_type IN ('individual', 'portfolio')),
    metrics JSONB NOT NULL DEFAULT '{}',
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Morning Predictions (persisted pre-market forecast)
CREATE TABLE IF NOT EXISTS morning_predictions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    prediction_type VARCHAR(20) NOT NULL DEFAULT 'morning',
    content JSONB NOT NULL DEFAULT '{}',
    predicted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Reflections (self-evaluation results)
CREATE TABLE IF NOT EXISTS reflections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    morning_prediction_id INTEGER REFERENCES morning_predictions(id) ON DELETE SET NULL,
    content JSONB NOT NULL DEFAULT '{}',
    evaluated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================
-- Indexes for performance
-- ============================================
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON portfolios(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_firebase_uid ON users(firebase_uid) WHERE firebase_uid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_date ON market_data(symbol, trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_news_published ON news(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_symbols ON news USING GIN(related_symbols);
CREATE INDEX IF NOT EXISTS idx_insights_user_type ON insights(user_id, insight_type);
CREATE INDEX IF NOT EXISTS idx_insights_created ON insights(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_predictions_user ON predictions(user_id, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_snapshots_user ON risk_snapshots(user_id, calculated_at DESC);
CREATE INDEX IF NOT EXISTS idx_morning_predictions_user ON morning_predictions(user_id, predicted_at DESC);
CREATE INDEX IF NOT EXISTS idx_reflections_user ON reflections(user_id, evaluated_at DESC);

-- ============================================
-- Seed default user
-- ============================================
INSERT INTO users (id, username, password_hash, risk_appetite, capital_amount)
VALUES (
    1,
    'demo_user',
    'pbkdf2_sha256$310000$9c3f4ec51f8ae5ff27b1e978df3f98b0$e623f55994dab0705f4080292443eb20a0dbc2292fd62a675aafb4cdffe0bb0a',
    'moderate',
    20000000
)
ON CONFLICT (id) DO NOTHING;

UPDATE users
SET password_hash = 'pbkdf2_sha256$310000$9c3f4ec51f8ae5ff27b1e978df3f98b0$e623f55994dab0705f4080292443eb20a0dbc2292fd62a675aafb4cdffe0bb0a'
WHERE username = 'demo_user' AND password_hash IS NULL AND firebase_uid IS NULL;

-- Seed default portfolio
INSERT INTO portfolios (user_id, symbol, quantity, avg_price, sector)
VALUES 
    (1, 'VCB', 100, 85000, 'Banking'),
    (1, 'FPT', 50, 120000, 'Technology'),
    (1, 'HPG', 200, 26000, 'Industrial')
ON CONFLICT (user_id, symbol) DO NOTHING;
