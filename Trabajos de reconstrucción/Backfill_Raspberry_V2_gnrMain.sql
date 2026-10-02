-- ================================================================
-- ACTUALIZACIÓN process."gnrMain"
-- EJECUTAR DESPUÉS DE VALIDAR HISTORIAN
-- ================================================================

BEGIN;

-- CCM 1
UPDATE process."gnrMain"
SET
    "value" = 1931,
    "accumulated" = 3715463
WHERE "id" = 8647
  AND "value" = 282
  AND "accumulated" = 3713814
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- CCM 2
UPDATE process."gnrMain"
SET
    "value" = 26743,
    "accumulated" = 36929475
WHERE "id" = 8650
  AND "value" = 4624
  AND "accumulated" = 36907356
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- CCM 3
UPDATE process."gnrMain"
SET
    "value" = 15391,
    "accumulated" = 18642589
WHERE "id" = 8649
  AND "value" = 2628
  AND "accumulated" = 18629826
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- Hypet 400-3
UPDATE process."gnrMain"
SET
    "value" = 8628.6310000001,
    "accumulated" = 1393283.6310000001
WHERE "id" = 8643
  AND "value" = 1509.5
  AND "accumulated" = 1386164.5
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- Hypet 500-2
UPDATE process."gnrMain"
SET
    "value" = 9709.6270000001,
    "accumulated" = 1964244.1270000001
WHERE "id" = 8645
  AND "value" = 1272.75
  AND "accumulated" = 1955807.25
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

-- IPS 400-2
UPDATE process."gnrMain"
SET
    "value" = 51830,
    "accumulated" = 68956470
WHERE "id" = 8634
  AND "value" = 8848
  AND "accumulated" = 68913488
RETURNING
    "id",
    "nameMtr",
    "nameTag",
    "value",
    "accumulated",
    "date",
    "dateIn";

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

-- ================================================================
-- VALIDAR RETURNING ANTES DEL COMMIT
-- ================================================================
-- COMMIT;
-- ROLLBACK;
