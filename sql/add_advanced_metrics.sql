-- Erweitere coin_metrics um neue Metriken
-- Migration: Fügt erweiterte Metriken für Whale-Tracking und Volatilität hinzu

ALTER TABLE coin_metrics
    -- Netto-Volumen (Delta): buy_volume - sell_volume
    ADD COLUMN IF NOT EXISTS net_volume_sol NUMERIC(24, 9) DEFAULT 0,
    
    -- Volatilität: ((high - low) / open) * 100
    ADD COLUMN IF NOT EXISTS volatility_pct NUMERIC(10, 4) DEFAULT 0,
    
    -- Durchschnittliche Trade-Größe: volume / (num_buys + num_sells)
    ADD COLUMN IF NOT EXISTS avg_trade_size_sol NUMERIC(24, 9) DEFAULT 0,
    
    -- Whale Tracking (Trades >= 1.0 SOL)
    ADD COLUMN IF NOT EXISTS whale_buy_volume_sol NUMERIC(24, 9) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS whale_sell_volume_sol NUMERIC(24, 9) DEFAULT 0,
    ADD COLUMN IF NOT EXISTS num_whale_buys INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS num_whale_sells INTEGER DEFAULT 0;

-- Kommentare für Dokumentation
COMMENT ON COLUMN coin_metrics.net_volume_sol IS 'Netto-Volumen (Delta): buy_volume_sol - sell_volume_sol. Positiv = Kaufdruck, Negativ = Verkaufsdruck';
COMMENT ON COLUMN coin_metrics.volatility_pct IS 'Volatilität: ((price_high - price_low) / price_open) * 100. Zeigt relative Preis-Schwankung im Intervall';
COMMENT ON COLUMN coin_metrics.avg_trade_size_sol IS 'Durchschnittliche Trade-Größe: volume_sol / (num_buys + num_sells)';
COMMENT ON COLUMN coin_metrics.whale_buy_volume_sol IS 'Volumen von Buy-Trades >= WHALE_THRESHOLD_SOL (Standard: 1.0 SOL)';
COMMENT ON COLUMN coin_metrics.whale_sell_volume_sol IS 'Volumen von Sell-Trades >= WHALE_THRESHOLD_SOL (Standard: 1.0 SOL)';
COMMENT ON COLUMN coin_metrics.num_whale_buys IS 'Anzahl Buy-Trades >= WHALE_THRESHOLD_SOL';
COMMENT ON COLUMN coin_metrics.num_whale_sells IS 'Anzahl Sell-Trades >= WHALE_THRESHOLD_SOL';

