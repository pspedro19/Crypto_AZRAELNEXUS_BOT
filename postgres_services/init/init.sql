-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Create crypto database if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'crypto_data') THEN
        CREATE DATABASE crypto_data;
    END IF;
END
$$;

\c crypto_data;

-- Create tables for different data sources with TimescaleDB hypertables
CREATE TABLE IF NOT EXISTS binance_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    open NUMERIC(24,8) NOT NULL,
    high NUMERIC(24,8) NOT NULL,
    low NUMERIC(24,8) NOT NULL,
    close NUMERIC(24,8) NOT NULL,
    volume NUMERIC(24,8) NOT NULL,
    trades INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_binance_data UNIQUE (symbol, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable('binance_data', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE TABLE IF NOT EXISTS coingecko_data (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    price_usd NUMERIC(24,8) NOT NULL,
    market_cap NUMERIC(24,8) NOT NULL,
    volume_24h NUMERIC(24,8) NOT NULL,
    price_change_24h NUMERIC(24,8) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_coingecko_data UNIQUE (symbol, timestamp)
);

-- Convert to hypertable
SELECT create_hypertable('coingecko_data', 'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Create optimized indexes
CREATE INDEX IF NOT EXISTS idx_binance_symbol_timestamp ON binance_data(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_binance_timestamp ON binance_data(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_coingecko_symbol_timestamp ON coingecko_data(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_coingecko_timestamp ON coingecko_data(timestamp DESC);

-- Create materialized view for combined data
CREATE MATERIALIZED VIEW IF NOT EXISTS crypto_combined_data 
WITH (timescaledb.continuous) AS
WITH binance_latest AS (
    SELECT 
        symbol,
        close as price,
        volume,
        timestamp,
        'binance' as source
    FROM binance_data
    WHERE timestamp >= NOW() - INTERVAL '24 hours'
),
coingecko_latest AS (
    SELECT 
        symbol,
        price_usd as price,
        volume_24h as volume,
        timestamp,
        'coingecko' as source
    FROM coingecko_data
    WHERE timestamp >= NOW() - INTERVAL '24 hours'
)
SELECT 
    COALESCE(b.symbol, c.symbol) as symbol,
    b.price as binance_price,
    c.price as coingecko_price,
    GREATEST(b.timestamp, c.timestamp) as last_updated,
    b.volume as binance_volume,
    c.volume as coingecko_volume
FROM binance_latest b
FULL OUTER JOIN coingecko_latest c USING (symbol)
WHERE b.symbol IS NOT NULL 
   OR c.symbol IS NOT NULL;

-- Create unique index on the materialized view
CREATE UNIQUE INDEX IF NOT EXISTS idx_crypto_combined_symbol 
ON crypto_combined_data (symbol, last_updated);

-- Create functions for maintenance and refresh
CREATE OR REPLACE FUNCTION refresh_crypto_combined_data()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY crypto_combined_data;
END;
$$ LANGUAGE plpgsql;

-- Create function to clean old data
CREATE OR REPLACE FUNCTION cleanup_old_data()
RETURNS void AS $$
BEGIN
    -- Delete data older than 3 months
    DELETE FROM binance_data 
    WHERE timestamp < NOW() - INTERVAL '3 months';
    
    DELETE FROM coingecko_data 
    WHERE timestamp < NOW() - INTERVAL '3 months';
    
    -- Vacuum tables after deletion
    VACUUM ANALYZE binance_data;
    VACUUM ANALYZE coingecko_data;
END;
$$ LANGUAGE plpgsql;

-- Schedule automated tasks using pg_cron
SELECT cron.schedule('refresh-mv', '*/15 * * * *', 'SELECT refresh_crypto_combined_data()');
SELECT cron.schedule('cleanup-old-data', '0 0 * * *', 'SELECT cleanup_old_data()');

-- Create monitoring views
CREATE OR REPLACE VIEW crypto_data_stats AS
SELECT
    (SELECT count(*) FROM binance_data) as binance_records,
    (SELECT count(*) FROM coingecko_data) as coingecko_records,
    (SELECT count(*) FROM crypto_combined_data) as combined_records,
    (SELECT max(timestamp) FROM binance_data) as latest_binance_update,
    (SELECT max(timestamp) FROM coingecko_data) as latest_coingecko_update;

-- Set up partitioning retention policy
SELECT add_retention_policy('binance_data', INTERVAL '3 months');
SELECT add_retention_policy('coingecko_data', INTERVAL '3 months');

-- Create user and grant permissions
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_user WHERE usename = 'crypto_user') THEN
        CREATE USER crypto_user WITH PASSWORD 'Cr1pt0_2024';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE crypto_data TO crypto_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO crypto_user;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO crypto_user;

-- Configure basic PostgreSQL optimizations
ALTER SYSTEM SET max_connections = '100';
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET effective_cache_size = '3GB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET work_mem = '32MB';
ALTER SYSTEM SET random_page_cost = '1.1';
ALTER SYSTEM SET effective_io_concurrency = '200';

-- Add table comments for documentation
COMMENT ON TABLE binance_data IS 'Real-time cryptocurrency data from Binance';
COMMENT ON TABLE coingecko_data IS 'Cryptocurrency market data from CoinGecko';
COMMENT ON MATERIALIZED VIEW crypto_combined_data IS 'Combined view of Binance and CoinGecko data';