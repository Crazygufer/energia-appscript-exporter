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


# =============================================================================
# PARÁMETROS
# =============================================================================

# Margen solicitado a Clickie para validar antes/después del hueco
MARGEN_API_MIN = 15

# Tolerancia para comparar Clickie contra un borde conocido de Ignition
TOLERANCIA_VALIDACION_MIN = 10

# No insertar un dato Clickie demasiado cerca de un registro real de Ignition.
MARGEN_BORDE_MIN = 2

# Protección SQL:
# si existe un registro del mismo tag a +/- 2 minutos, no inserta.
PROTECCION_SQL_SEG = 120

# Día operativo que estamos corrigiendo
CIERRE_DIA = datetime(
    2026, 8, 21,
    7, 0, 0,
    tzinfo=TZ
)


# =============================================================================
# EQUIPOS
# =============================================================================
#
# IMPORTANTE:
#
# scale = 1.0 PARA TODOS.
#
# El futuro ajuste ×0,1 NO forma parte de este backfill.
#
# =============================================================================

EQUIPOS = [

    # =========================================================================
    # CCM 1
    # =========================================================================

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

        # Primer registro realmente válido después del retorno
        "first_after": datetime(
            2026, 8, 21,
            10, 56, 1, 801000,
            tzinfo=TZ
        ),

        "value_after": 3715775.0,

        # 10:46 = cero de inicialización/publicación inválido
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

        # acumulador del cierre del día anterior
        "previous_accumulated": 3713532.0,

        "max_edge_diff": 500.0
    },


    # =========================================================================
    # CCM 2
    # =========================================================================

    {
        "key": "ccm2",
        "name": "CCM 2",

        "uuid": "2c0fde28-81d3-404f-9983-9db8f2fb2e3d",

        "scale": 1.0,

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


    # =========================================================================
    # CCM 3
    # =========================================================================

    {
        "key": "ccm3",
        "name": "CCM 3",

        "uuid": "bdb14b8e-b06e-4d48-b683-13f0d3dc271d",

        "scale": 1.0,

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


    # =========================================================================
    # HYPET 400-3
    # =========================================================================

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

        # 10:46 fue cero inválido.
        # 10:51 ya vuelve con acumulador real.
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


    # =========================================================================
    # HYPET 500-2
    # =========================================================================

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


    # =========================================================================
    # IPS 400-2
    # =========================================================================

    {
        "key": "ips400_2",
        "name": "IPS 400-2",

        "uuid": "6da7639c-7481-405d-9415-3e599bc8dd02",

        "scale": 1.0,

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


    # =========================================================================
    # SB08
    # =========================================================================

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
    }
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

    if value is None:
        return "NULL"

    return (
        f"{float(value):.10f}"
        .rstrip("0")
        .rstrip(".")
    )


# =============================================================================
# PARSEO CLICKIE
# =============================================================================

def agregar_punto(
    puntos,
    timestamp,
    value
):

    try:

        timestamp = float(timestamp)
        value = float(value)

    except (TypeError, ValueError):
        return


    if not math.isfinite(value):
        return


    # Clickie podría entregar segundos o milisegundos
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
        "ts_seconds": timestamp,
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


    # =========================================================================
    # DICT
    # =========================================================================

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


    # =========================================================================
    # LIST
    # =========================================================================

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
                isinstance(
                    item,
                    (list, tuple)
                )
                and len(item) >= 2
            ):

                agregar_punto(
                    puntos,
                    item[0],
                    item[1]
                )


    # =========================================================================
    # ELIMINAR TIMESTAMPS DUPLICADOS
    # =========================================================================

    unicos = {}


    for punto in puntos:

        ts_ms = epoch_ms(
            punto["dt"]
        )

        unicos[ts_ms] = punto


    puntos = list(
        unicos.values()
    )


    puntos.sort(
        key=lambda p: p["dt"]
    )


    return puntos


# =============================================================================
# CONSULTA CLICKIE
# =============================================================================

def consultar_clickie(equipo):

    if not API_KEY:

        raise RuntimeError(
            "Falta CLICKIE_API_KEY en .env"
        )


    desde = (
        equipo["last_before"]
        - timedelta(
            minutes=MARGEN_API_MIN
        )
    )


    hasta = (
        equipo["first_after"]
        + timedelta(
            minutes=MARGEN_API_MIN
        )
    )


    headers = {
        "Authorization": API_KEY,
        "Account": ACCOUNT_ID,
        "Accept": "application/json"
    }


    params = {
        "metric": equipo["uuid"],
        "from": int(
            desde.timestamp()
        ),
        "to": int(
            hasta.timestamp()
        )
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
        "clickie_raw_v2",
        exist_ok=True
    )


    with open(
        f"clickie_raw_v2/{equipo['key']}.json",
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


    # =========================================================================
    # ESCALA
    #
    # POR AHORA TODOS ×1.
    # =========================================================================

    for punto in puntos:

        punto["value"] = (
            punto["raw_value"]
            * equipo["scale"]
        )


    return puntos


# =============================================================================
# LECTURA MÁS CERCANA
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
# VALIDAR BORDE
# =============================================================================

def validar_borde(
    equipo,
    puntos,
    target_dt,
    ignition_value
):

    lectura = buscar_mas_cercano(
        puntos,
        target_dt,
        TOLERANCIA_VALIDACION_MIN
    )


    if lectura is None:

        return {
            "ok": False,
            "reason": "SIN_LECTURA",
            "clickie": None,
            "diff": None
        }


    diff = (
        lectura["value"]
        - ignition_value
    )


    ok = (
        abs(diff)
        <= equipo["max_edge_diff"]
    )


    return {
        "ok": ok,

        "reason":
            "OK"
            if ok
            else "DIFERENCIA_EXCESIVA",

        "clickie": lectura,

        "diff": diff
    }


# =============================================================================
# EXTRAER DATOS REALES CLICKIE DEL HUECO
# =============================================================================

def extraer_hueco_real(
    equipo,
    puntos
):

    """
    No genera timestamps artificiales.

    Conserva únicamente las lecturas REALES
    de Clickie dentro del intervalo faltante.
    """

    inicio = (
        equipo["last_before"]
        + timedelta(
            minutes=MARGEN_BORDE_MIN
        )
    )


    fin = (
        equipo["first_after"]
        - timedelta(
            minutes=MARGEN_BORDE_MIN
        )
    )


    filas = []


    for punto in puntos:

        if not (
            inicio
            < punto["dt"]
            < fin
        ):
            continue


        filas.append({
            "dt": punto["dt"],

            "t_stamp":
                epoch_ms(
                    punto["dt"]
                ),

            "raw_value":
                punto["raw_value"],

            "value":
                punto["value"]
        })


    # Orden cronológico
    filas.sort(
        key=lambda x: x["dt"]
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

        actual = fila["value"]


        if actual < anterior:

            errores.append({
                "dt": fila["dt"],
                "anterior": anterior,
                "actual": actual
            })


        anterior = actual


    # Comparar contra el primer valor real posterior
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
# VALIDAR DUPLICADOS DE TIMESTAMP CLICKIE
# =============================================================================

def validar_timestamps(filas):

    vistos = set()
    duplicados = []


    for fila in filas:

        ts = fila[
            "t_stamp"
        ]


        if ts in vistos:

            duplicados.append(
                fila
            )

        else:

            vistos.add(
                ts
            )


    return duplicados


# =============================================================================
# CALCULAR CIERRE 07:00
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
            "ok": False,
            "reason": "SIN_LECTURA_07"
        }


    nuevo_accumulated = lectura[
        "value"
    ]


    nuevo_value = (
        nuevo_accumulated
        - equipo[
            "previous_accumulated"
        ]
    )


    if nuevo_value < 0:

        return {
            "ok": False,
            "reason": "CONSUMO_NEGATIVO"
        }


    return {
        "ok": True,
        "reason": "OK",

        "dt":
            lectura["dt"],

        "raw_value":
            lectura["raw_value"],

        "accumulated":
            nuevo_accumulated,

        "consumption":
            nuevo_value,

        "distance_seconds":
            lectura["distance_seconds"]
    }


# =============================================================================
# PROCESAR EQUIPO
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
        f"Lecturas Clickie recibidas: "
        f"{len(puntos)}"
    )


    # =========================================================================
    # BORDES
    # =========================================================================

    inicio = validar_borde(
        equipo,
        puntos,
        equipo["last_before"],
        equipo["value_before"]
    )


    fin = validar_borde(
        equipo,
        puntos,
        equipo["first_after"],
        equipo["value_after"]
    )


    print()
    print("VALIDACIÓN INICIAL")

    print(
        f"Ignition : "
        f"{equipo['value_before']:,.3f}"
    )


    if inicio["clickie"]:

        print(
            f"Clickie  : "
            f"{inicio['clickie']['value']:,.3f}"
        )

        print(
            f"Fecha    : "
            f"{fmt_dt(inicio['clickie']['dt'])}"
        )

        print(
            f"Delta    : "
            f"{inicio['diff']:+,.3f}"
        )

    else:

        print(
            "Clickie  : SIN DATO"
        )


    print()
    print("VALIDACIÓN FINAL")

    print(
        f"Ignition : "
        f"{equipo['value_after']:,.3f}"
    )


    if fin["clickie"]:

        print(
            f"Clickie  : "
            f"{fin['clickie']['value']:,.3f}"
        )

        print(
            f"Fecha    : "
            f"{fmt_dt(fin['clickie']['dt'])}"
        )

        print(
            f"Delta    : "
            f"{fin['diff']:+,.3f}"
        )

    else:

        print(
            "Clickie  : SIN DATO"
        )


    # =========================================================================
    # HUECO
    # =========================================================================

    filas = extraer_hueco_real(
        equipo,
        puntos
    )


    errores_monotonia = validar_monotonia(
        equipo,
        filas
    )


    duplicados = validar_timestamps(
        filas
    )


    cierre = calcular_cierre(
        equipo,
        puntos
    )


    valido = (
        inicio["ok"]
        and
        fin["ok"]
        and
        len(filas) > 0
        and
        len(errores_monotonia) == 0
        and
        len(duplicados) == 0
        and
        cierre["ok"]
    )


    print()
    print("HISTÓRICO A RECUPERAR")

    print(
        f"Lecturas reales Clickie : "
        f"{len(filas)}"
    )


    if filas:

        print(
            f"Primera                : "
            f"{fmt_dt(filas[0]['dt'])}"
            f" -> {filas[0]['value']:,.3f}"
        )

        print(
            f"Última                 : "
            f"{fmt_dt(filas[-1]['dt'])}"
            f" -> {filas[-1]['value']:,.3f}"
        )


    print(
        f"Retrocesos EA          : "
        f"{len(errores_monotonia)}"
    )

    print(
        f"Timestamps duplicados  : "
        f"{len(duplicados)}"
    )


    print()
    print("CIERRE OPERACIONAL")


    if cierre["ok"]:

        print(
            f"Lectura Clickie : "
            f"{fmt_dt(cierre['dt'])}"
        )

        print(
            f"EA cierre       : "
            f"{cierre['accumulated']:,.3f}"
        )

        print(
            f"Consumo anterior: "
            f"{equipo['old_value']:,.3f}"
        )

        print(
            f"Consumo corregido: "
            f"{cierre['consumption']:,.3f}"
        )

    else:

        print(
            f"ERROR: "
            f"{cierre['reason']}"
        )


    print()
    print(
        "RESULTADO: "
        + (
            "APROBADO"
            if valido
            else "BLOQUEADO"
        )
    )


    return {
        "equipo": equipo,

        "puntos": puntos,

        "inicio": inicio,
        "fin": fin,

        "filas": filas,

        "errores_monotonia":
            errores_monotonia,

        "duplicados":
            duplicados,

        "cierre":
            cierre,

        "valid":
            valido
    }


# =============================================================================
# CSV RESUMEN
# =============================================================================

def exportar_resumen(
    resultados
):

    archivo = (
        "Backfill_Raspberry_V2_Resumen.csv"
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

            "borde_inicio",
            "delta_inicio",

            "borde_fin",
            "delta_fin",

            "lecturas_backfill",

            "retrocesos",
            "duplicados",

            "lectura_cierre",

            "ea_cierre",

            "consumo_actual",

            "consumo_corregido",

            "accumulated_actual",

            "accumulated_corregido",

            "resultado"
        ])


        for r in resultados:

            e = r["equipo"]
            cierre = r["cierre"]


            writer.writerow([
                e["name"],
                e["tagid"],
                e["uuid"],
                e["scale"],

                r["inicio"]["reason"],
                r["inicio"]["diff"],

                r["fin"]["reason"],
                r["fin"]["diff"],

                len(
                    r["filas"]
                ),

                len(
                    r["errores_monotonia"]
                ),

                len(
                    r["duplicados"]
                ),

                (
                    fmt_dt(
                        cierre.get("dt")
                    )
                    if cierre["ok"]
                    else ""
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
                    if r["valid"]
                    else "BLOQUEADO"
                )
            ])


    return archivo


# =============================================================================
# CSV AUDITORÍA
# =============================================================================

def exportar_auditoria(
    resultados
):

    archivo = (
        "Backfill_Raspberry_V2_Auditoria.csv"
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

            "timestamp_clickie",

            "t_stamp_ms",

            "raw_clickie",

            "valor_insertar"
        ])


        for r in resultados:

            e = r[
                "equipo"
            ]


            for fila in r[
                "filas"
            ]:

                writer.writerow([
                    e["name"],
                    e["tagid"],
                    e["tagpath"],

                    fmt_dt(
                        fila["dt"]
                    ),

                    fila["t_stamp"],

                    fila["raw_value"],

                    fila["value"]
                ])


    return archivo


# =============================================================================
# SQL HISTORIAN
# =============================================================================

def generar_sql_historian(
    resultados
):

    archivo = (
        "Backfill_Raspberry_V2_Historian.sql"
    )


    proteccion_ms = (
        PROTECCION_SQL_SEG
        * 1000
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
            "-- BACKFILL RASPBERRY V2\n"
        )

        f.write(
            "-- HISTORIAN IGNITION\n"
        )

        f.write(
            "-- Usa timestamps REALES de Clickie\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


        # =====================================================================
        # ELIMINAR CEROS INVÁLIDOS
        # =====================================================================

        f.write(
            "-- ================================================================\n"
        )

        f.write(
            "-- REGISTROS INVÁLIDOS CONFIRMADOS\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        for r in resultados:

            if not r["valid"]:
                continue


            e = r["equipo"]


            for invalido in e[
                "invalid_rows"
            ]:

                ts = epoch_ms(
                    invalido["datetime"]
                )


                f.write(
                    f"-- {e['name']}\n"
                )


                f.write(
                    f"DELETE FROM {HIST_TABLE}\n"
                    f"WHERE tagid = {e['tagid']}\n"
                    f"  AND t_stamp = {ts}\n"
                    f"  AND floatvalue = "
                    f"{sql_number(invalido['value'])};\n\n"
                )


        # =====================================================================
        # INSERTS
        # =====================================================================

        for r in resultados:

            e = r[
                "equipo"
            ]


            if not r["valid"]:

                f.write(
                    f"-- BLOQUEADO: "
                    f"{e['name']}\n\n"
                )

                continue


            filas = r[
                "filas"
            ]


            if not filas:
                continue


            f.write(
                "-- ================================================================\n"
            )

            f.write(
                f"-- {e['name']}\n"
            )

            f.write(
                f"-- tagid = {e['tagid']}\n"
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
                    f"({e['tagid']}, "
                    f"{sql_number(fila['value'])}"
                    "::double precision, "
                    f"{fila['t_stamp']}::bigint)"
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
            "-- NO HACER COMMIT HASTA VALIDAR\n"
        )

        f.write(
            "-- ================================================================\n"
        )

        f.write(
            "-- COMMIT;\n"
        )

        f.write(
            "-- ROLLBACK;\n"
        )


    return archivo


# =============================================================================
# SQL gnrMain
# =============================================================================

def generar_sql_gnr(
    resultados
):

    archivo = (
        "Backfill_Raspberry_V2_gnrMain.sql"
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
            "-- EJECUTAR DESPUÉS DE VALIDAR HISTORIAN\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


        for r in resultados:

            e = r["equipo"]
            cierre = r["cierre"]


            if (
                not r["valid"]
                or
                not cierre["ok"]
            ):

                f.write(
                    f"-- BLOQUEADO: "
                    f"{e['name']}\n\n"
                )

                continue


            nuevo_value = cierre[
                "consumption"
            ]


            nuevo_accumulated = cierre[
                "accumulated"
            ]


            f.write(
                f"-- {e['name']}\n"
            )


            f.write(
                f'UPDATE {GNR_TABLE}\n'
                "SET\n"
                f'    "value" = '
                f'{sql_number(nuevo_value)},\n'
                f'    "accumulated" = '
                f'{sql_number(nuevo_accumulated)}\n'
                f'WHERE "id" = '
                f'{e["gnr_id"]}\n'
                f'  AND "value" = '
                f'{sql_number(e["old_value"])}\n'
                f'  AND "accumulated" = '
                f'{sql_number(e["old_accumulated"])}\n'
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
            "-- ================================================================\n"
        )

        f.write(
            "-- VALIDAR RETURNING ANTES DEL COMMIT\n"
        )

        f.write(
            "-- ================================================================\n"
        )

        f.write(
            "-- COMMIT;\n"
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
        "BACKFILL MASIVO RASPBERRY V2"
    )

    print(
        "=" * 80
    )

    print(
        "Escala aplicada a /ea: ×1"
    )

    print(
        "Timestamps: REALES de Clickie"
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
                f"ERROR EN {equipo['name']}: "
                f"{error}"
            )


            resultado = {

                "equipo":
                    equipo,

                "puntos":
                    [],

                "inicio": {
                    "ok": False,
                    "reason": "ERROR",
                    "diff": None,
                    "clickie": None
                },

                "fin": {
                    "ok": False,
                    "reason": "ERROR",
                    "diff": None,
                    "clickie": None
                },

                "filas":
                    [],

                "errores_monotonia":
                    [],

                "duplicados":
                    [],

                "cierre": {
                    "ok": False,
                    "reason": "ERROR"
                },

                "valid":
                    False
            }


        resultados.append(
            resultado
        )


    # =========================================================================
    # EXPORTACIONES
    # =========================================================================

    resumen = exportar_resumen(
        resultados
    )


    auditoria = exportar_auditoria(
        resultados
    )


    sql_hist = generar_sql_historian(
        resultados
    )


    sql_gnr = generar_sql_gnr(
        resultados
    )


    # =========================================================================
    # RESULTADO FINAL
    # =========================================================================

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


    aprobados = 0


    for r in resultados:

        estado = (
            "APROBADO"
            if r["valid"]
            else "BLOQUEADO"
        )


        print(
            f"{r['equipo']['name']:<20} "
            f"{estado}"
        )


        if r["valid"]:
            aprobados += 1


    print()
    print(
        f"Aprobados: "
        f"{aprobados}/{len(resultados)}"
    )


    print()
    print(
        "ARCHIVOS GENERADOS"
    )

    print(
        f"  {resumen}"
    )

    print(
        f"  {auditoria}"
    )

    print(
        f"  {sql_hist}"
    )

    print(
        f"  {sql_gnr}"
    )

    print(
        "  clickie_raw_v2/*.json"
    )


    print()
    print(
        "Ninguna modificación fue realizada "
        "directamente en PostgreSQL."
    )


if __name__ == "__main__":
    main()