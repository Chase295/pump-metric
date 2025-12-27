-- ============================================================================
-- ATH (All-Time High) TRACKING - DATENBANK-SCHEMA ERWEITERUNG
-- ============================================================================
-- 
-- Fügt ATH-Tracking-Spalten zur coin_streams Tabelle hinzu.
-- Diese Spalten werden verwendet, um den höchsten Preis jedes Coins zu tracken.
-- 
-- Implementierung: Hybrid-System
-- - RAM (ath_cache): Für Millisekunden-Entscheidungen (sofort verfügbar)
-- - DB (coin_streams): Für Persistenz (überlebt Neustarts)
-- ============================================================================

-- Füge ATH-Spalten zur coin_streams Tabelle hinzu
ALTER TABLE coin_streams 
ADD COLUMN IF NOT EXISTS ath_price_sol NUMERIC DEFAULT 0,
ADD COLUMN IF NOT EXISTS ath_timestamp TIMESTAMPTZ;

-- Index für schnelle ATH-Abfragen (optional, aber empfohlen)
-- Hilft bei Queries wie "Top 10 Coins nach ATH"
CREATE INDEX IF NOT EXISTS idx_streams_ath_price 
ON coin_streams(ath_price_sol DESC) 
WHERE is_active = TRUE AND ath_price_sol > 0;

-- Kommentare für Dokumentation
COMMENT ON COLUMN coin_streams.ath_price_sol IS 'All-Time High Preis in SOL (wird live getrackt)';
COMMENT ON COLUMN coin_streams.ath_timestamp IS 'Timestamp des letzten ATH-Updates';

-- ============================================================================
-- VERIFICATION QUERIES (Optional - zum Testen)
-- ============================================================================

-- Prüfe ob Spalten existieren:
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns 
-- WHERE table_name = 'coin_streams' 
-- AND column_name IN ('ath_price_sol', 'ath_timestamp');

-- Prüfe aktive Coins mit ATH:
-- SELECT token_address, ath_price_sol, ath_timestamp 
-- FROM coin_streams 
-- WHERE is_active = TRUE 
-- ORDER BY ath_price_sol DESC 
-- LIMIT 10;

