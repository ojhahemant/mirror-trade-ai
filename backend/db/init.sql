-- ═══════════════════════════════════════════════════════════
-- Mirror Trade AI — Database Schema
-- Uses TimescaleDB for time-series optimization
-- ═══════════════════════════════════════════════════════════

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ── Users ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    username        VARCHAR(100) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    is_active       BOOLEAN DEFAULT TRUE,
    risk_mode       VARCHAR(20) DEFAULT 'balanced',  -- conservative/balanced/aggressive
    alert_telegram  BOOLEAN DEFAULT FALSE,
    alert_email     BOOLEAN DEFAULT FALSE,
    alert_inapp     BOOLEAN DEFAULT TRUE,
    telegram_chat_id VARCHAR(100),
    email_address   VARCHAR(255),
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── OHLCV Candles (Time-series table) ────────────────────
CREATE TABLE IF NOT EXISTS candles (
    time        TIMESTAMPTZ NOT NULL,
    symbol      VARCHAR(50) NOT NULL DEFAULT 'BANKNIFTY',
    timeframe   VARCHAR(10) NOT NULL,  -- 1min, 5min, 15min, 1hr, 1day
    open        NUMERIC(12,2) NOT NULL,
    high        NUMERIC(12,2) NOT NULL,
    low         NUMERIC(12,2) NOT NULL,
    close       NUMERIC(12,2) NOT NULL,
    volume      BIGINT NOT NULL DEFAULT 0,
    oi          BIGINT,  -- Open Interest
    PRIMARY KEY (time, symbol, timeframe)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('candles', 'time', if_not_exists => TRUE);

-- ── Options Chain Snapshots ───────────────────────────────
CREATE TABLE IF NOT EXISTS options_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    time            TIMESTAMPTZ NOT NULL,
    expiry_date     DATE NOT NULL,
    strike          NUMERIC(12,2) NOT NULL,
    option_type     CHAR(2) NOT NULL,  -- CE or PE
    ltp             NUMERIC(10,2),
    iv              NUMERIC(8,4),
    oi              BIGINT,
    change_in_oi    BIGINT,
    volume          BIGINT,
    pcr             NUMERIC(8,4),
    max_pain        NUMERIC(12,2),
    iv_rank         NUMERIC(6,2)
);

SELECT create_hypertable('options_snapshots', 'time', if_not_exists => TRUE);

-- ── Trading Signals ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS signals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    direction       VARCHAR(10) NOT NULL,  -- BUY, SELL, NEUTRAL
    confidence      NUMERIC(5,2) NOT NULL,
    entry_price     NUMERIC(12,2) NOT NULL,
    entry_low       NUMERIC(12,2),
    entry_high      NUMERIC(12,2),
    stop_loss       NUMERIC(12,2) NOT NULL,
    target_1        NUMERIC(12,2) NOT NULL,
    target_2        NUMERIC(12,2) NOT NULL,
    risk_reward     NUMERIC(5,2) NOT NULL,
    pattern_detected VARCHAR(100),
    timeframe       VARCHAR(10) DEFAULT '15min',
    atr_value       NUMERIC(10,2),
    status          VARCHAR(20) DEFAULT 'ACTIVE',
    -- ACTIVE | TARGET_1_HIT | TARGET_2_HIT | SL_HIT | EXPIRED | CANCELLED
    closed_at       TIMESTAMPTZ,
    close_price     NUMERIC(12,2),
    pnl_points      NUMERIC(10,2) DEFAULT 0,
    model_version   VARCHAR(50),
    features_snapshot JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Signal Lifecycle Events ───────────────────────────────
CREATE TABLE IF NOT EXISTS signal_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    signal_id   UUID REFERENCES signals(id) ON DELETE CASCADE,
    event_type  VARCHAR(50) NOT NULL,  -- CREATED, T1_HIT, T2_HIT, SL_HIT, EXPIRED
    price       NUMERIC(12,2),
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    notes       TEXT
);

-- ── Model Versions ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_versions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version         VARCHAR(50) UNIQUE NOT NULL,
    filename        VARCHAR(255) NOT NULL,
    is_champion     BOOLEAN DEFAULT FALSE,
    train_accuracy  NUMERIC(6,4),
    val_accuracy    NUMERIC(6,4),
    train_from      DATE,
    train_to        DATE,
    feature_count   INTEGER,
    hyperparams     JSONB,
    metrics         JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Backtest Results ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS backtest_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_date       DATE NOT NULL,
    to_date         DATE NOT NULL,
    total_signals   INTEGER,
    winning_signals INTEGER,
    losing_signals  INTEGER,
    neutral_signals INTEGER,
    win_rate        NUMERIC(6,2),
    avg_rr          NUMERIC(6,2),
    max_drawdown    NUMERIC(10,2),
    sharpe_ratio    NUMERIC(6,3),
    total_pnl_points NUMERIC(12,2),
    best_trade      NUMERIC(10,2),
    worst_trade     NUMERIC(10,2),
    monthly_pnl     JSONB,
    detailed_trades JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_candles_symbol_timeframe ON candles(symbol, timeframe, time DESC);
CREATE INDEX IF NOT EXISTS idx_signals_status ON signals(status, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_direction ON signals(direction, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_options_time ON options_snapshots(time DESC);

-- ── Continuous Aggregate for 1-day summary ────────────────
CREATE MATERIALIZED VIEW IF NOT EXISTS candles_daily_summary
WITH (timescaledb.continuous) AS
    SELECT
        time_bucket('1 day', time) AS bucket,
        symbol,
        first(open, time) AS open,
        max(high) AS high,
        min(low) AS low,
        last(close, time) AS close,
        sum(volume) AS volume
    FROM candles
    WHERE timeframe = '15min'
    GROUP BY bucket, symbol
WITH NO DATA;

-- ── Functions ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_signals_updated_at
    BEFORE UPDATE ON signals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Default admin user (change password immediately!)
INSERT INTO users (email, username, hashed_password, risk_mode)
VALUES ('admin@mirrortrade.ai', 'admin', '$2b$12$placeholder_change_me', 'balanced')
ON CONFLICT DO NOTHING;
