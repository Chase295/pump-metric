-- Erweitere coin_metrics um Ratio-Metriken
-- Migration: Fügt buy_pressure_ratio und unique_signer_ratio hinzu

ALTER TABLE coin_metrics
    -- Buy Pressure Ratio: Verhältnis von Buy- zu Gesamt-Volumen
    ADD COLUMN IF NOT EXISTS buy_pressure_ratio NUMERIC(5, 4) DEFAULT 0,
    
    -- Unique Signer Ratio: Verhältnis von unique_wallets zu total_trades
    ADD COLUMN IF NOT EXISTS unique_signer_ratio NUMERIC(5, 4) DEFAULT 0;

-- Kommentare für Dokumentation
COMMENT ON COLUMN coin_metrics.buy_pressure_ratio IS 'Buy-Volumen-Verhältnis: buy_volume / (buy_volume + sell_volume). 0.0 = nur Sells, 1.0 = nur Buys, 0.5 = ausgeglichen';
COMMENT ON COLUMN coin_metrics.unique_signer_ratio IS 'Unique-Wallet-Verhältnis: unique_wallets / (num_buys + num_sells). Niedrig = Wash-Trading, Hoch = organisches Wachstum';

