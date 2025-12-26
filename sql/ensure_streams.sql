-- ============================================================================
-- AUTOMATISCHE STREAM-ERSTELLUNG
-- ============================================================================
-- 
-- Diese Funktionen und Trigger stellen sicher, dass für jeden Coin in
-- discovered_coins automatisch ein Stream in coin_streams erstellt wird.
-- ============================================================================

-- Funktion: Erstellt automatisch einen Stream für einen neuen Coin
CREATE OR REPLACE FUNCTION ensure_coin_stream()
RETURNS TRIGGER AS $$
BEGIN
    -- Prüfe ob bereits ein Stream existiert
    IF NOT EXISTS (
        SELECT 1 FROM coin_streams 
        WHERE token_address = NEW.token_address
    ) THEN
        -- Erstelle neuen Stream
        INSERT INTO coin_streams (
            token_address,
            current_phase_id,
            is_active,
            is_graduated,
            started_at
        ) VALUES (
            NEW.token_address,
            COALESCE(NEW.phase_id, 1),  -- Verwende phase_id aus discovered_coins oder Default 1
            COALESCE(NEW.is_active, TRUE),  -- Verwende is_active aus discovered_coins oder Default TRUE
            COALESCE(NEW.is_graduated, FALSE),  -- Verwende is_graduated aus discovered_coins oder Default FALSE
            COALESCE(NEW.discovered_at, NOW())  -- Verwende discovered_at oder jetzt
        )
        ON CONFLICT (token_address) DO NOTHING;  -- Verhindert Fehler bei Duplikaten
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger: Wird bei jedem INSERT in discovered_coins ausgelöst
DROP TRIGGER IF EXISTS trigger_ensure_coin_stream ON discovered_coins;
CREATE TRIGGER trigger_ensure_coin_stream
    AFTER INSERT ON discovered_coins
    FOR EACH ROW
    EXECUTE FUNCTION ensure_coin_stream();

-- Funktion: Repariert fehlende Streams (für nachträgliche Korrektur)
CREATE OR REPLACE FUNCTION repair_missing_streams()
RETURNS TABLE(
    token_address VARCHAR(64),
    created BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    WITH missing_streams AS (
        SELECT dc.token_address
        FROM discovered_coins dc
        WHERE NOT EXISTS (
            SELECT 1 FROM coin_streams cs
            WHERE cs.token_address = dc.token_address
        )
        AND dc.is_active = TRUE  -- Nur aktive Coins
    )
    INSERT INTO coin_streams (
        token_address,
        current_phase_id,
        is_active,
        is_graduated,
        started_at
    )
    SELECT 
        ms.token_address,
        COALESCE(dc.phase_id, 1),
        COALESCE(dc.is_active, TRUE),
        COALESCE(dc.is_graduated, FALSE),
        COALESCE(dc.discovered_at, NOW())
    FROM missing_streams ms
    JOIN discovered_coins dc ON ms.token_address = dc.token_address
    ON CONFLICT (token_address) DO NOTHING
    RETURNING coin_streams.token_address, TRUE;
END;
$$ LANGUAGE plpgsql;

-- Funktion: Prüft auf Lücken und gibt Report zurück
CREATE OR REPLACE FUNCTION check_stream_gaps()
RETURNS TABLE(
    missing_streams_count BIGINT,
    coins_without_streams TEXT[],
    oldest_missing_coin TIMESTAMP WITH TIME ZONE,
    newest_missing_coin TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as missing_streams_count,
        ARRAY_AGG(dc.token_address ORDER BY dc.discovered_at) FILTER (WHERE COUNT(*) <= 20) as coins_without_streams,
        MIN(dc.discovered_at) as oldest_missing_coin,
        MAX(dc.discovered_at) as newest_missing_coin
    FROM discovered_coins dc
    WHERE NOT EXISTS (
        SELECT 1 FROM coin_streams cs
        WHERE cs.token_address = dc.token_address
    )
    AND dc.is_active = TRUE;
END;
$$ LANGUAGE plpgsql;

-- Kommentare
COMMENT ON FUNCTION ensure_coin_stream() IS 'Erstellt automatisch einen Stream-Eintrag für jeden neuen Coin in discovered_coins';
COMMENT ON FUNCTION repair_missing_streams() IS 'Repariert fehlende Streams für Coins die bereits in discovered_coins existieren';
COMMENT ON FUNCTION check_stream_gaps() IS 'Prüft auf Lücken zwischen discovered_coins und coin_streams';



