-- ================================================================
-- ACTUALIZACION process."gnrMain"
-- LOTE 3
-- ================================================================

BEGIN;

-- Blomacs 10
UPDATE process."gnrMain"
SET
    "value" = 61,
    "accumulated" = 3328016
WHERE "id" = 8617
  AND "value" = 11
  AND "accumulated" = 3327966
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- KHS 8
UPDATE process."gnrMain"
SET
    "value" = 132,
    "accumulated" = 8053345
WHERE "id" = 8619
  AND "value" = 32
  AND "accumulated" = 8053245
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- Compresor de Alta
UPDATE process."gnrMain"
SET
    "value" = 6,
    "accumulated" = 6737218
WHERE "id" = 8665
  AND "value" = 6
  AND "accumulated" = 6737218
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- ================================================================
-- VALIDAR RETURNING ANTES DE COMMIT
-- ================================================================
-- COMMIT;
-- ROLLBACK;
