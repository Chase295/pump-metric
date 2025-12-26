-- ============================================================================
-- ENTFERNE phase_id SPALTE AUS discovered_coins
-- ============================================================================
-- 
-- Diese Query entfernt die Spalte 'phase_id' aus der Tabelle 'discovered_coins'
-- ============================================================================

-- Prüfe zuerst ob die Spalte existiert
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'discovered_coins' 
        AND column_name = 'phase_id'
    ) THEN
        -- Entferne die Spalte
        ALTER TABLE discovered_coins DROP COLUMN phase_id;
        RAISE NOTICE 'Spalte phase_id wurde aus discovered_coins entfernt';
    ELSE
        RAISE NOTICE 'Spalte phase_id existiert nicht in discovered_coins';
    END IF;
END $$;

