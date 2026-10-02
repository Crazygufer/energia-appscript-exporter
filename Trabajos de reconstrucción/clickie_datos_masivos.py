import os
import csv
import json
import math
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv


# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

load_dotenv()

TZ = ZoneInfo("America/Santiago")

API_URL = "https://api.clickie.io/v4/data/metric"


API_KEY = "0580c356-8b91-4298-bd20-385c2f46226a"
ACCOUNT_ID = "63"

HIST_TABLE = "timescaledb_history.sqlth_1_data"
GNR_TABLE = 'process."gnrMain"'

INTERVALO_MINUTOS = 5

# Para reconstrucción
TOLERANCIA_BACKFILL_MIN = 4

# Para validar Clickie contra los bordes conocidos de Ignition
TOLERANCIA_VALIDACION_MIN = 10

# Margen adicional API
MARGEN_API_MIN = 15

# Evitar generar un punto prácticamente encima
# del primer dato válido después de la caída.
MARGEN_FIN_MIN = 2

# Protección SQL contra registros cercanos existentes
PROTECCION_SQL_SEG = 120

# Cierre operacional
CIERRE_DIA = datetime(
    2026, 8, 21,
    7, 0, 0,
    tzinfo=TZ
)


# =============================================================================
# CONFIGURACIÓN DE LOS EQUIPOS
# =============================================================================
#
# old_value / old_accumulated:
# Son los valores actualmente congelados en process."gnrMain".
#
# previous_accumulated:
# Es el acumulado correspondiente al cierre del día anterior.
#
# last_before / first_after:
# Bordes válidos encontrados en historian.
#
# invalid_rows:
# Registros espurios que sabemos que deben eliminarse antes del backfill.
# =============================================================================

EQUIPOS = [

    {
        "key": "ccm1",
        "name": "CCM 1",

        "uuid": "ff0263d8-07a0-4d37-8840-88d4414ada88",

        "scale": 1.0,

        "tagid": 1862,
        "tagpath": "lids/energy/ccm1/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 3713814.0,

        # 10:46 fue cero inválido.
        # No hubo registro útil a las 10:51.
        # El primer borde realmente válido fue 10:56.
        "first_after": datetime(
            2026, 8, 21,
            10, 56, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 3715775.0,

        "invalid_rows": [
            {
                "datetime": datetime(
                    2026, 8, 21,
                    10, 46, 1, 801000,
                    tzinfo=TZ
                ),
                "value": 0.0
            }
        ],

        "gnr_id": 8647,
        "old_value": 282.0,
        "old_accumulated": 3713814.0,
        "previous_accumulated": 3713532.0,

        "max_edge_diff": 500.0
    },


    {
        "key": "ccm2",
        "name": "CCM 2",

        "uuid": "2c0fde28-81d3-404f-9983-9db8f2fb2e3d",

        # Clickie raw -> Ignition kWh
        "scale": 0.1,

        "tagid": 1868,
        "tagpath": "lids/energy/ccm2/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 36907356.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 36933644.0,

        "invalid_rows": [],

        "gnr_id": 8650,
        "old_value": 4624.0,
        "old_accumulated": 36907356.0,
        "previous_accumulated": 36902732.0,

        "max_edge_diff": 1500.0
    },


    {
        "key": "ccm3",
        "name": "CCM 3",

        "uuid": "bdb14b8e-b06e-4d48-b683-13f0d3dc271d",

        "scale": 0.1,

        "tagid": 1445,
        "tagpath": "lids/energy/ccm3/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 18629826.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 18644876.0,

        "invalid_rows": [],

        "gnr_id": 8649,
        "old_value": 2628.0,
        "old_accumulated": 18629826.0,
        "previous_accumulated": 18627198.0,

        "max_edge_diff": 1500.0
    },


    {
        "key": "hyp400_3",
        "name": "Hypet 400-3",

        "uuid": "38e371c4-f2e7-46ed-a0a7-7ba6a5dab360",

        "scale": 1.0,

        "tagid": 1493,
        "tagpath": "injection/energy/hyp400_3/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 1386164.5,

        # 10:46 = 0 inválido.
        # 10:51 es el primer acumulado real.
        "first_after": datetime(
            2026, 8, 21,
            10, 51, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 1394626.75,

        "invalid_rows": [
            {
                "datetime": datetime(
                    2026, 8, 21,
                    10, 46, 1, 801000,
                    tzinfo=TZ
                ),
                "value": 0.0
            }
        ],

        "gnr_id": 8643,
        "old_value": 1509.5,
        "old_accumulated": 1386164.5,
        "previous_accumulated": 1384655.0,

        "max_edge_diff": 500.0
    },


    {
        "key": "hyp500_2",
        "name": "Hypet 500-2",

        "uuid": "9faeb035-e10e-4fd9-87f4-70632f2753d2",

        "scale": 1.0,

        "tagid": 1434,
        "tagpath": "injection/energy/hyp500_2/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 1955807.25,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 1965932.25,

        "invalid_rows": [],

        "gnr_id": 8645,
        "old_value": 1272.75,
        "old_accumulated": 1955807.25,
        "previous_accumulated": 1954534.5,

        "max_edge_diff": 500.0
    },


    {
        "key": "ips400_2",
        "name": "IPS 400-2",

        "uuid": "6da7639c-7481-405d-9415-3e599bc8dd02",

        "scale": 0.1,

        "tagid": 1469,
        "tagpath": "injection/energy/ips400_2/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 68913488.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 68964560.0,

        "invalid_rows": [],

        "gnr_id": 8634,
        "old_value": 8848.0,
        "old_accumulated": 68913488.0,
        "previous_accumulated": 68904640.0,

        "max_edge_diff": 3000.0
    },


    {
        "key": "sb08",
        "name": "SB08",

        "uuid": "cf8918f9-50c6-42be-84e3-46905b288fa8",

        "scale": 1.0,

        "tagid": 1466,
        "tagpath": "blown/energy/sb08/ea",

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),
        "value_before": 968544.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),
        "value_after": 968558.0,

        "invalid_rows": [],

        "gnr_id": 8616,
        "old_value": 2.0,
        "old_accumulated": 968544.0,
        "previous_accumulated": 968542.0,

        "max_edge_diff": 100.0
    },
]


# =============================================================================
# UTILIDADES
# =============================================================================

def epoch_ms(dt):
    return int(round(dt.timestamp() * 1000))


def fmt_dt(dt):
    if dt is None:
        return ""

    return dt.strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


def sql_number(value):
    """
    Número SQL sin notación científica.
    """

    if value is None:
        return "NULL"

    return (
        f"{float(value):.10f}"
        .rstrip("0")
        .rstrip(".")
    )


# =============================================================================
# CLICKIE
# =============================================================================

def agregar_punto(puntos, timestamp, value):

    try:
        timestamp = float(timestamp)
        value = float(value)
    except (TypeError, ValueError):
        return

    if not math.isfinite(value):
        return

    if timestamp > 10_000_000_000:
        timestamp = timestamp / 1000.0

    try:
        dt = datetime.fromtimestamp(
            timestamp,
            TZ
        )
    except Exception:
        return

    puntos.append({
        "ts": int(timestamp),
        "dt": dt,
        "raw_value": value
    })


def parse_clickie_response(payload):

    puntos = []

    if (
        isinstance(payload, dict)
        and "data" in payload
    ):
        data = payload["data"]
    else:
        data = payload


    if isinstance(data, dict):

        for key, value in data.items():

            if isinstance(
                value,
                (int, float, str)
            ):
                agregar_punto(
                    puntos,
                    key,
                    value
                )

            elif isinstance(value, dict):

                ts = (
                    value.get("timestamp")
                    or value.get("ts")
                    or value.get("time")
                    or key
                )

                val = (
                    value.get("value")
                    if value.get("value") is not None
                    else value.get("val")
                )

                if val is not None:
                    agregar_punto(
                        puntos,
                        ts,
                        val
                    )


    elif isinstance(data, list):

        for item in data:

            if isinstance(item, dict):

                ts = (
                    item.get("timestamp")
                    or item.get("ts")
                    or item.get("time")
                    or item.get("date")
                )

                val = (
                    item.get("value")
                    if item.get("value") is not None
                    else item.get("val")
                )

                if (
                    ts is not None
                    and val is not None
                ):
                    agregar_punto(
                        puntos,
                        ts,
                        val
                    )

            elif (
                isinstance(item, (list, tuple))
                and len(item) >= 2
            ):

                agregar_punto(
                    puntos,
                    item[0],
                    item[1]
                )


    # Eliminar timestamps duplicados

    unicos = {}

    for punto in puntos:
        unicos[punto["ts"]] = punto

    puntos = list(
        unicos.values()
    )

    puntos.sort(
        key=lambda p: p["dt"]
    )

    return puntos


def consultar_clickie(equipo):

    if not API_KEY:
        raise RuntimeError(
            "Falta CLICKIE_API_KEY en .env"
        )

    desde = (
        equipo["last_before"]
        - timedelta(minutes=MARGEN_API_MIN)
    )

    hasta = (
        equipo["first_after"]
        + timedelta(minutes=MARGEN_API_MIN)
    )


    headers = {
        "Authorization": API_KEY,
        "Account": ACCOUNT_ID,
        "Accept": "application/json"
    }


    params = {
        "metric": equipo["uuid"],
        "from": int(desde.timestamp()),
        "to": int(hasta.timestamp())
    }


    response = requests.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=60
    )

    response.raise_for_status()

    payload = response.json()


    os.makedirs(
        "clickie_raw",
        exist_ok=True
    )

    with open(
        f"clickie_raw/{equipo['key']}.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False
        )


    puntos = parse_clickie_response(
        payload
    )


    # -------------------------------------------------------------------------
    # Aplicar escala al TOTALIZADOR completo.
    # -------------------------------------------------------------------------

    for punto in puntos:

        punto["value"] = (
            punto["raw_value"]
            * equipo["scale"]
        )


    return puntos


# =============================================================================
# BÚSQUEDA MÁS CERCANA
# =============================================================================

def buscar_mas_cercano(
    puntos,
    objetivo,
    tolerancia_min
):

    mejor = None
    mejor_distancia = None

    for punto in puntos:

        distancia = abs(
            (
                punto["dt"]
                - objetivo
            ).total_seconds()
        )

        if (
            mejor_distancia is None
            or distancia < mejor_distancia
        ):

            mejor = punto
            mejor_distancia = distancia


    if mejor is None:
        return None


    if (
        mejor_distancia
        > tolerancia_min * 60
    ):
        return None


    resultado = dict(mejor)

    resultado[
        "distance_seconds"
    ] = mejor_distancia

    return resultado


# =============================================================================
# VALIDACIÓN DE BORDES
# =============================================================================

def validar_borde(
    puntos,
    target_dt,
    ignition_value,
    max_diff
):

    lectura = buscar_mas_cercano(
        puntos,
        target_dt,
        TOLERANCIA_VALIDACION_MIN
    )

    if lectura is None:

        return {
            "ok": False,
            "reason": "SIN_LECTURA_CLICKIE",
            "clickie": None,
            "diff": None
        }


    diff = (
        lectura["value"]
        - ignition_value
    )


    return {
        "ok": abs(diff) <= max_diff,
        "reason":
            "OK"
            if abs(diff) <= max_diff
            else "DIFERENCIA_EXCESIVA",

        "clickie": lectura,
        "diff": diff
    }


# =============================================================================
# RECONSTRUCCIÓN
# =============================================================================

def reconstruir_hueco(
    equipo,
    puntos
):

    filas = []

    objetivo = (
        equipo["last_before"]
        + timedelta(
            minutes=INTERVALO_MINUTOS
        )
    )


    limite = (
        equipo["first_after"]
        - timedelta(
            minutes=MARGEN_FIN_MIN
        )
    )


    source_ts_usados = set()


    while objetivo < limite:

        lectura = buscar_mas_cercano(
            puntos,
            objetivo,
            TOLERANCIA_BACKFILL_MIN
        )


        if lectura is None:

            filas.append({
                "target_dt": objetivo,
                "target_ms": epoch_ms(objetivo),

                "clickie_dt": None,
                "clickie_ts": None,

                "raw_value": None,
                "value": None,

                "distance_seconds": None,

                "status": "SIN_DATO"
            })


        elif lectura["ts"] in source_ts_usados:

            filas.append({
                "target_dt": objetivo,
                "target_ms": epoch_ms(objetivo),

                "clickie_dt": lectura["dt"],
                "clickie_ts": lectura["ts"],

                "raw_value":
                    lectura["raw_value"],

                "value":
                    lectura["value"],

                "distance_seconds":
                    lectura["distance_seconds"],

                "status":
                    "LECTURA_CLICKIE_REUTILIZADA"
            })


        else:

            source_ts_usados.add(
                lectura["ts"]
            )

            filas.append({
                "target_dt": objetivo,
                "target_ms": epoch_ms(objetivo),

                "clickie_dt": lectura["dt"],
                "clickie_ts": lectura["ts"],

                "raw_value":
                    lectura["raw_value"],

                "value":
                    lectura["value"],

                "distance_seconds":
                    lectura["distance_seconds"],

                "status": "OK"
            })


        objetivo += timedelta(
            minutes=INTERVALO_MINUTOS
        )


    return filas


# =============================================================================
# VALIDAR MONOTONÍA
# =============================================================================

def validar_monotonia(
    equipo,
    filas
):

    errores = []

    anterior = equipo[
        "value_before"
    ]


    for fila in filas:

        if fila["status"] != "OK":
            continue

        actual = fila["value"]

        if actual < anterior:

            errores.append({
                "dt": fila["target_dt"],
                "anterior": anterior,
                "actual": actual
            })

        anterior = actual


    if (
        equipo["value_after"]
        < anterior
    ):

        errores.append({
            "dt":
                equipo["first_after"],

            "anterior":
                anterior,

            "actual":
                equipo["value_after"]
        })


    return errores


# =============================================================================
# CONSUMO DEL DÍA
# =============================================================================

def calcular_cierre(
    equipo,
    puntos
):

    lectura = buscar_mas_cercano(
        puntos,
        CIERRE_DIA,
        TOLERANCIA_VALIDACION_MIN
    )

    if lectura is None:

        return {
            "ok": False
        }


    accumulated = lectura[
        "value"
    ]


    consumo = (
        accumulated
        - equipo[
            "previous_accumulated"
        ]
    )


    return {
        "ok": consumo >= 0,

        "dt":
            lectura["dt"],

        "raw_value":
            lectura["raw_value"],

        "accumulated":
            accumulated,

        "consumption":
            consumo
    }


# =============================================================================
# PROCESAR UN EQUIPO
# =============================================================================

def procesar_equipo(equipo):

    print()
    print("=" * 80)
    print(equipo["name"])
    print("=" * 80)


    puntos = consultar_clickie(
        equipo
    )


    print(
        f"Lecturas Clickie: {len(puntos)}"
    )


    validacion_inicio = validar_borde(
        puntos,
        equipo["last_before"],
        equipo["value_before"],
        equipo["max_edge_diff"]
    )


    validacion_fin = validar_borde(
        puntos,
        equipo["first_after"],
        equipo["value_after"],
        equipo["max_edge_diff"]
    )


    print()
    print("Borde inicial:")

    if validacion_inicio["clickie"]:

        print(
            f"  Ignition : "
            f"{equipo['value_before']:,.3f}"
        )

        print(
            f"  Clickie  : "
            f"{validacion_inicio['clickie']['value']:,.3f}"
        )

        print(
            f"  Delta    : "
            f"{validacion_inicio['diff']:+,.3f}"
        )

    else:

        print(
            "  Sin lectura Clickie."
        )


    print()
    print("Borde final:")

    if validacion_fin["clickie"]:

        print(
            f"  Ignition : "
            f"{equipo['value_after']:,.3f}"
        )

        print(
            f"  Clickie  : "
            f"{validacion_fin['clickie']['value']:,.3f}"
        )

        print(
            f"  Delta    : "
            f"{validacion_fin['diff']:+,.3f}"
        )

    else:

        print(
            "  Sin lectura Clickie."
        )


    filas = reconstruir_hueco(
        equipo,
        puntos
    )


    errores_monotonia = validar_monotonia(
        equipo,
        filas
    )


    cierre = calcular_cierre(
        equipo,
        puntos
    )


    estados_no_ok = [
        x
        for x in filas
        if x["status"] != "OK"
    ]


    valido = (
        validacion_inicio["ok"]
        and
        validacion_fin["ok"]
        and
        len(estados_no_ok) == 0
        and
        len(errores_monotonia) == 0
        and
        cierre["ok"]
    )


    print()
    print(
        f"Puntos esperados   : "
        f"{len(filas)}"
    )

    print(
        f"Puntos OK          : "
        f"{len(filas) - len(estados_no_ok)}"
    )

    print(
        f"Puntos con problema: "
        f"{len(estados_no_ok)}"
    )

    print(
        f"Retrocesos EA      : "
        f"{len(errores_monotonia)}"
    )


    if cierre["ok"]:

        print()
        print(
            f"EA cierre 07:00    : "
            f"{cierre['accumulated']:,.3f}"
        )

        print(
            f"Consumo corregido  : "
            f"{cierre['consumption']:,.3f} kWh"
        )


    print()
    print(
        "RESULTADO: "
        + (
            "APROBADO PARA SQL"
            if valido
            else "BLOQUEADO"
        )
    )


    return {
        "equipo": equipo,
        "puntos": puntos,
        "filas": filas,

        "inicio":
            validacion_inicio,

        "fin":
            validacion_fin,

        "errores_monotonia":
            errores_monotonia,

        "cierre":
            cierre,

        "valid": valido
    }


# =============================================================================
# CSV AUDITORÍA
# =============================================================================

def exportar_auditoria(resultados):

    archivo = (
        "Backfill_Raspberry_Auditoria.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "equipo",
            "tagid",
            "tagpath",
            "scale",
            "timestamp_objetivo",
            "timestamp_clickie",
            "raw_clickie",
            "valor_ignition",
            "distancia_segundos",
            "estado"
        ])


        for resultado in resultados:

            equipo = resultado[
                "equipo"
            ]


            for fila in resultado[
                "filas"
            ]:

                writer.writerow([
                    equipo["name"],
                    equipo["tagid"],
                    equipo["tagpath"],
                    equipo["scale"],

                    fmt_dt(
                        fila["target_dt"]
                    ),

                    fmt_dt(
                        fila["clickie_dt"]
                    ),

                    fila["raw_value"],

                    fila["value"],

                    fila[
                        "distance_seconds"
                    ],

                    fila["status"]
                ])


    return archivo


# =============================================================================
# CSV RESUMEN
# =============================================================================

def exportar_resumen(resultados):

    archivo = (
        "Backfill_Raspberry_Resumen.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)


        writer.writerow([
            "equipo",
            "tagid",
            "uuid",
            "scale",
            "validacion_inicio",
            "delta_inicio",
            "validacion_fin",
            "delta_fin",
            "puntos",
            "puntos_ok",
            "retrocesos",
            "ea_cierre_07",
            "consumo_actual_gnr",
            "consumo_corregido",
            "acumulado_actual_gnr",
            "acumulado_corregido",
            "resultado"
        ])


        for resultado in resultados:

            e = resultado["equipo"]

            filas = resultado["filas"]

            puntos_ok = sum(
                1
                for x in filas
                if x["status"] == "OK"
            )


            cierre = resultado[
                "cierre"
            ]


            writer.writerow([
                e["name"],
                e["tagid"],
                e["uuid"],
                e["scale"],

                resultado["inicio"]["reason"],
                resultado["inicio"]["diff"],

                resultado["fin"]["reason"],
                resultado["fin"]["diff"],

                len(filas),
                puntos_ok,

                len(
                    resultado[
                        "errores_monotonia"
                    ]
                ),

                (
                    cierre.get(
                        "accumulated"
                    )
                    if cierre["ok"]
                    else ""
                ),

                e["old_value"],

                (
                    cierre.get(
                        "consumption"
                    )
                    if cierre["ok"]
                    else ""
                ),

                e["old_accumulated"],

                (
                    cierre.get(
                        "accumulated"
                    )
                    if cierre["ok"]
                    else ""
                ),

                (
                    "APROBADO"
                    if resultado["valid"]
                    else "BLOQUEADO"
                )
            ])


    return archivo


# =============================================================================
# SQL HISTORIAN
# =============================================================================

def generar_sql_historian(resultados):

    archivo = (
        "Backfill_Raspberry_Historian.sql"
    )


    proteccion_ms = (
        PROTECCION_SQL_SEG * 1000
    )


    with open(
        archivo,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "-- ================================================================\n"
        )
        f.write(
            "-- BACKFILL RASPBERRY -> IGNITION HISTORIAN\n"
        )
        f.write(
            "-- NO EJECUTAR COMMIT SIN VALIDAR\n"
        )
        f.write(
            "-- ================================================================\n\n"
        )

        f.write(
            "BEGIN;\n\n"
        )


        # =====================================================================
        # BORRAR CEROS ESPURIOS
        # =====================================================================

        f.write(
            "-- ================================================================\n"
        )
        f.write(
            "-- ELIMINACIÓN DE REGISTROS INVÁLIDOS CONFIRMADOS\n"
        )
        f.write(
            "-- ================================================================\n\n"
        )


        for resultado in resultados:

            if not resultado["valid"]:
                continue


            equipo = resultado[
                "equipo"
            ]


            for invalid in equipo[
                "invalid_rows"
            ]:

                ts_ms = epoch_ms(
                    invalid["datetime"]
                )


                f.write(
                    f"-- {equipo['name']}\n"
                )

                f.write(
                    f"DELETE FROM {HIST_TABLE}\n"
                    f"WHERE tagid = {equipo['tagid']}\n"
                    f"  AND t_stamp = {ts_ms}\n"
                    f"  AND floatvalue = "
                    f"{sql_number(invalid['value'])};\n\n"
                )


        # =====================================================================
        # INSERT POR EQUIPO
        # =====================================================================

        for resultado in resultados:

            equipo = resultado[
                "equipo"
            ]


            if not resultado["valid"]:

                f.write(
                    f"-- BLOQUEADO: {equipo['name']}\n\n"
                )

                continue


            filas = [
                fila
                for fila in resultado["filas"]
                if fila["status"] == "OK"
            ]


            if not filas:
                continue


            f.write(
                "-- ================================================================\n"
            )

            f.write(
                f"-- {equipo['name']} | "
                f"tagid={equipo['tagid']}\n"
            )

            f.write(
                "-- ================================================================\n"
            )


            f.write(
                f"INSERT INTO {HIST_TABLE}\n"
                "(\n"
                "    tagid,\n"
                "    floatvalue,\n"
                "    t_stamp\n"
                ")\n"
                "SELECT\n"
                "    v.tagid,\n"
                "    v.floatvalue,\n"
                "    v.t_stamp\n"
                "FROM\n"
                "(\n"
                "    VALUES\n"
            )


            values_sql = []


            for fila in filas:

                values_sql.append(
                    "        "
                    f"({equipo['tagid']}, "
                    f"{sql_number(fila['value'])}"
                    "::double precision, "
                    f"{fila['target_ms']}::bigint)"
                )


            f.write(
                ",\n".join(
                    values_sql
                )
            )


            f.write(
                "\n"
                ") AS v(tagid, floatvalue, t_stamp)\n"
                "WHERE NOT EXISTS\n"
                "(\n"
                "    SELECT 1\n"
                f"    FROM {HIST_TABLE} existente\n"
                "    WHERE existente.tagid = v.tagid\n"
                "      AND existente.t_stamp BETWEEN\n"
                f"          v.t_stamp - {proteccion_ms}\n"
                "          AND\n"
                f"          v.t_stamp + {proteccion_ms}\n"
                ");\n\n"
            )


        f.write(
            "-- ================================================================\n"
        )

        f.write(
            "-- VALIDAR ANTES DE EJECUTAR:\n"
        )

        f.write(
            "-- COMMIT;\n"
        )

        f.write(
            "-- Si algo no cuadra:\n"
        )

        f.write(
            "-- ROLLBACK;\n"
        )


    return archivo


# =============================================================================
# SQL GNRMAIN
# =============================================================================

def generar_sql_gnr(resultados):

    archivo = (
        "Backfill_Raspberry_gnrMain.sql"
    )


    with open(
        archivo,
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            "-- ================================================================\n"
        )

        f.write(
            '-- ACTUALIZACIÓN process."gnrMain"\n'
        )

        f.write(
            "-- EJECUTAR SOLO DESPUÉS DEL HISTORIAN\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )

        f.write(
            "BEGIN;\n\n"
        )


        for resultado in resultados:

            equipo = resultado[
                "equipo"
            ]

            cierre = resultado[
                "cierre"
            ]


            if (
                not resultado["valid"]
                or
                not cierre["ok"]
            ):

                f.write(
                    f"-- BLOQUEADO: {equipo['name']}\n\n"
                )

                continue


            nuevo_value = cierre[
                "consumption"
            ]

            nuevo_accumulated = cierre[
                "accumulated"
            ]


            f.write(
                f"-- {equipo['name']}\n"
            )


            f.write(
                f'UPDATE {GNR_TABLE}\n'
                "SET\n"
                f'    "value" = '
                f'{sql_number(nuevo_value)},\n'
                f'    "accumulated" = '
                f'{sql_number(nuevo_accumulated)}\n'
                f'WHERE "id" = '
                f'{equipo["gnr_id"]}\n'
                f'  AND "value" = '
                f'{sql_number(equipo["old_value"])}\n'
                f'  AND "accumulated" = '
                f'{sql_number(equipo["old_accumulated"])}\n'
                "RETURNING\n"
                '    "id",\n'
                '    "nameMtr",\n'
                '    "nameTag",\n'
                '    "value",\n'
                '    "accumulated",\n'
                '    "date",\n'
                '    "dateIn";\n\n'
            )


        f.write(
            "-- VALIDAR TODOS LOS RETURNING.\n"
        )

        f.write(
            "-- Después:\n"
        )

        f.write(
            "-- COMMIT;\n"
        )

        f.write(
            "-- Ante cualquier diferencia:\n"
        )

        f.write(
            "-- ROLLBACK;\n"
        )


    return archivo


# =============================================================================
# MAIN
# =============================================================================

def main():

    print(
        "=" * 80
    )

    print(
        "BACKFILL MASIVO RASPBERRY"
    )

    print(
        "=" * 80
    )


    resultados = []


    for equipo in EQUIPOS:

        try:

            resultado = procesar_equipo(
                equipo
            )

        except Exception as error:

            print()
            print(
                f"ERROR {equipo['name']}: "
                f"{error}"
            )


            resultado = {
                "equipo": equipo,
                "puntos": [],
                "filas": [],

                "inicio": {
                    "ok": False,
                    "reason": "ERROR",
                    "diff": None
                },

                "fin": {
                    "ok": False,
                    "reason": "ERROR",
                    "diff": None
                },

                "errores_monotonia": [],

                "cierre": {
                    "ok": False
                },

                "valid": False
            }


        resultados.append(
            resultado
        )


    # =========================================================================
    # ARCHIVOS
    # =========================================================================

    auditoria = exportar_auditoria(
        resultados
    )

    resumen = exportar_resumen(
        resultados
    )

    sql_hist = generar_sql_historian(
        resultados
    )

    sql_gnr = generar_sql_gnr(
        resultados
    )


    print()
    print(
        "=" * 80
    )

    print(
        "RESULTADO GENERAL"
    )

    print(
        "=" * 80
    )


    for resultado in resultados:

        print(
            f"{resultado['equipo']['name']:<20} "
            f"{'APROBADO' if resultado['valid'] else 'BLOQUEADO'}"
        )


    print()
    print(
        "Archivos:"
    )

    print(
        f"  {auditoria}"
    )

    print(
        f"  {resumen}"
    )

    print(
        f"  {sql_hist}"
    )

    print(
        f"  {sql_gnr}"
    )

    print(
        "  clickie_raw/*.json"
    )


    print()
    print(
        "IMPORTANTE: ningún SQL fue ejecutado."
    )


if __name__ == "__main__":
    main()