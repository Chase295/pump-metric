-- ============================================================================
-- FIX: phase_id Fehler beheben
-- ============================================================================
-- 
-- Diese Query aktualisiert die Funktionen, die noch auf phase_id zugreifen
-- ============================================================================

-- Aktualisiere ensure_coin_stream() Funktion
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
            1,  -- Default Phase 1 (phase_id wurde aus discovered_coins entfernt)
            COALESCE(NEW.is_active, TRUE),
            COALESCE(NEW.is_graduated, FALSE),
            COALESCE(NEW.discovered_at, NOW())
        )
        ON CONFLICT (token_address) DO NOTHING;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Aktualisiere repair_missing_streams() Funktion
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
        AND dc.is_active = TRUE
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
        1,  -- Default Phase 1 (phase_id wurde aus discovered_coins entfernt)
        COALESCE(dc.is_active, TRUE),
        COALESCE(dc.is_graduated, FALSE),
        COALESCE(dc.discovered_at, NOW())
    FROM missing_streams ms
    JOIN discovered_coins dc ON ms.token_address = dc.token_address
    ON CONFLICT (token_address) DO NOTHING
    RETURNING coin_streams.token_address, TRUE;
END;
$$ LANGUAGE plpgsql;

