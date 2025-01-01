-- Create materialized view for combined data
CREATE MATERIALIZED VIEW crypto_combined_data AS
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
),
myinvestor_latest AS (
    SELECT 
        symbol,
        closing_price as price,
        volume,
        date as timestamp,
        'myinvestor' as source
    FROM myinvestor_data
    WHERE date = CURRENT_DATE
)
SELECT 
    COALESCE(b.symbol, c.symbol, m.symbol) as symbol,
    b.price as binance_price,
    c.price as coingecko_price,
    m.price as myinvestor_price,
    GREATEST(b.timestamp, c.timestamp, m.timestamp) as last_updated,
    b.volume as binance_volume,
    c.volume as coingecko_volume,
    m.volume as myinvestor_volume
FROM binance_latest b
FULL OUTER JOIN coingecko_latest c USING (symbol)
FULL OUTER JOIN myinvestor_latest m USING (symbol)
WHERE b.symbol IS NOT NULL 
   OR c.symbol IS NOT NULL 
   OR m.symbol IS NOT NULL;

-- Create unique index on the materialized view
CREATE UNIQUE INDEX idx_crypto_combined_symbol ON crypto_combined_data (symbol);

-- Create function to refresh materialized view
CREATE OR REPLACE FUNCTION refresh_crypto_combined_data()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY crypto_combined_data;
END;
$$ LANGUAGE plpgsql;

-- Schedule refresh every 15 minutes using pg_cron
SELECT cron.schedule('*/15 * * * *', 'SELECT refresh_crypto_combined_data();');