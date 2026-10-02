-- =============================================================================
-- AUDITORÍA gnrMain VS CLICKIE
-- =============================================================================
--
-- BASE: gnrProDb01
-- TABLA: process."gnrMain"
--
-- CONSULTA EXCLUSIVAMENTE DE LECTURA.
--
-- Exportar resultado como:
--     gnrMain_Auditoria.csv
--
-- y dejarlo dentro de:
--     auditoria_clickie_raspberry/reportes/
-- =============================================================================

SELECT
    id,
    "nameMtr" AS equipo,
    "nameTag" AS codigo,
    value,
    accumulated,
    "date",
    "dateIn",
    path,
    category
FROM process."gnrMain"
WHERE "nameTag" IN (
        'hyp400_3',
        'hyp500_2',
        'ips400_2',
        'ccm2',
        'ccm3',
        'blm10',
        'khs8',
        'ccm1',
        'sb08'
)
AND "dateIn" >= TIMESTAMP '2026-01-02 00:00:00'
AND "dateIn" <  TIMESTAMP '2026-08-24 00:00:00'
ORDER BY
    "dateIn",
    "nameTag",
    id;
