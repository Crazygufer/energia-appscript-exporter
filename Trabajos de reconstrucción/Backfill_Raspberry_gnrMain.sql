-- ================================================================
-- ACTUALIZACIÓN process."gnrMain"
-- EJECUTAR SOLO DESPUÉS DEL HISTORIAN
-- ================================================================

BEGIN;

-- BLOQUEADO: CCM 1

-- BLOQUEADO: CCM 2

-- BLOQUEADO: CCM 3

-- BLOQUEADO: Hypet 400-3

-- BLOQUEADO: Hypet 500-2

-- BLOQUEADO: IPS 400-2

-- SB08
UPDATE process."gnrMain"
SET
    "value" = 15,
    "accumulated" = 968557
WHERE "id" = 8616
  AND "value" = 2
  AND "accumulated" = 968544
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- VALIDAR TODOS LOS RETURNING.
-- Después:
-- COMMIT;
-- Ante cualquier diferencia:
-- ROLLBACK;
