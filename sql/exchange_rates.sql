-- ============================================================================
-- PUMP METRIC - Exchange Rates Tabelle (Marktstimmung)
-- ============================================================================
-- Diese Tabelle wird vom n8n Workflow gefüllt und dient als Referenz für
-- die KI-Analyse, um echte Token-Pumps von allgemeinen Marktbewegungen zu unterscheiden.
-- ============================================================================

CREATE TABLE IF NOT EXISTS exchange_rates (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),       -- Zeitstempel des Snapshots
    sol_price_usd NUMERIC(24, 9),              -- WICHTIG: Der "Wasserstand" (z.B. 145.50)
    usd_to_eur_rate NUMERIC(10, 6),            -- Währungsumrechnung (USD zu EUR)
    native_currency_price_usd NUMERIC(24, 9),  -- Redundant zu sol_price (für Mapping)
    blockchain_id INTEGER DEFAULT 1,           -- ID der Chain (1 = Solana)
    source VARCHAR(50)                          -- Herkunft (z.B. "Scout Workflow" oder "n8n")
);

-- Index für schnelle Abfragen nach Zeitpunkt
CREATE INDEX IF NOT EXISTS idx_exchange_rates_created_at ON exchange_rates(created_at DESC);

-- Index für Blockchain-ID (falls mehrere Chains unterstützt werden)
CREATE INDEX IF NOT EXISTS idx_exchange_rates_blockchain ON exchange_rates(blockchain_id);

-- Kommentare
COMMENT ON TABLE exchange_rates IS 'Marktstimmung ("Wasserstand"): SOL-Preis und Wechselkurse für KI-Analysen';
COMMENT ON COLUMN exchange_rates.sol_price_usd IS 'Aktueller SOL-Preis in USD - Der "Wasserstand" für relative Performance-Analysen';
COMMENT ON COLUMN exchange_rates.usd_to_eur_rate IS 'USD zu EUR Wechselkurs (für EUR-Umrechnungen)';
COMMENT ON COLUMN exchange_rates.created_at IS 'Zeitstempel des Snapshots (wird alle 60 Sekunden aktualisiert)';
COMMENT ON COLUMN exchange_rates.source IS 'Herkunft der Daten (z.B. "n8n Workflow", "Jupiter API")';

-- ============================================================================
-- BEISPIEL-ABFRAGEN
-- ============================================================================

-- Neueste Exchange Rate
/*
SELECT 
    sol_price_usd,
    usd_to_eur_rate,
    created_at
FROM exchange_rates
ORDER BY created_at DESC
LIMIT 1;
*/

-- Exchange Rates der letzten Stunde
/*
SELECT 
    created_at,
    sol_price_usd,
    usd_to_eur_rate
FROM exchange_rates
WHERE created_at >= NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
*/

-- SOL-Preis-Änderung (letzte Stunde)
/*
SELECT 
    (SELECT sol_price_usd FROM exchange_rates ORDER BY created_at DESC LIMIT 1) as aktuell,
    (SELECT sol_price_usd FROM exchange_rates WHERE created_at >= NOW() - INTERVAL '1 hour' ORDER BY created_at ASC LIMIT 1) as vor_1h,
    ((SELECT sol_price_usd FROM exchange_rates ORDER BY created_at DESC LIMIT 1) / 
     (SELECT sol_price_usd FROM exchange_rates WHERE created_at >= NOW() - INTERVAL '1 hour' ORDER BY created_at ASC LIMIT 1) - 1) * 100 as aenderung_pct;
*/

-- ============================================================================
-- ENDE DES SCHEMAS
-- ============================================================================

