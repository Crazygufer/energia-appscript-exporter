import os
import csv
import json
import math
import requests

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

load_dotenv()

TZ = ZoneInfo("America/Santiago")

API_URL = "https://api.clickie.io/v4/data/metric"

API_KEY = "0580c356-8b91-4298-bd20-385c2f46226a"
ACCOUNT_ID = "63"

HIST_TABLE = "timescaledb_history.sqlth_1_data"
GNR_TABLE = 'process."gnrMain"'


# =============================================================================
# PARÁMETROS DE SEGURIDAD
# =============================================================================

# Margen adicional solicitado a Clickie
MARGEN_API_MIN = 15

# Para validar Clickie contra los bordes conocidos de Ignition
TOLERANCIA_VALIDACION_MIN = 10

# No usar lecturas demasiado pegadas al borde real existente
MARGEN_BORDE_MIN = 2

# Si ya existe una lectura del mismo tag dentro de ±2 minutos,
# el SQL no inserta esa lectura Clickie.
PROTECCION_SQL_SEG = 120

# Día operacional que estamos reparando:
# 20-08 07:00 → 21-08 07:00
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
# Todos se recuperan a escala ×1.
# El proyecto futuro de normalización ×0.1 NO se aplica aquí.
#
# =============================================================================

EQUIPOS = [

    # =========================================================================
    # BLOMACS 10
    # =========================================================================

    {
        "key": "blm10",
        "name": "Blomacs 10",

        "uuid": "263f108c-b499-4706-8ffd-24a4e71096ab",

        "tagid": 1472,
        "tagpath": "blown/energy/blm10/ea",

        "scale": 1.0,

        # Último dato antes de caer Raspberry
        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),

        "value_before": 3327966.0,

        # Primer dato después de volver
        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),

        "value_after": 3328025.0,

        # gnrMain
        "gnr_id": 8617,

        "old_value": 11.0,
        "old_accumulated": 3327966.0,

        # Acumulado utilizado como inicio del día
        "previous_accumulated": 3327955.0,

        # Tolerancia Clickie vs Ignition
        "max_edge_diff": 100.0
    },


    # =========================================================================
    # KHS 8
    # =========================================================================

    {
        "key": "khs8",
        "name": "KHS 8",

        "uuid": "4a6fbb73-d1ff-4ae5-b6a1-236df6fdeb57",

        "tagid": 1432,
        "tagpath": "blown/energy/khs8/ea",

        "scale": 1.0,

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),

        "value_before": 8053245.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),

        "value_after": 8053364.0,

        "gnr_id": 8619,

        "old_value": 32.0,
        "old_accumulated": 8053245.0,

        "previous_accumulated": 8053213.0,

        "max_edge_diff": 150.0
    },


    # =========================================================================
    # COMPRESOR DE ALTA
    # =========================================================================
    #
    # UUID CANDIDATO:
    # "Compresor ABC (ex Horizont)"
    #
    # El script NO lo dará por válido a menos que Clickie cuadre
    # contra 6.737.218 en los bordes.
    # =========================================================================

    {
        "key": "cmp_high",
        "name": "Compresor de Alta",

        "uuid": "0bb125fe-69c6-48fb-84ef-070bf49ed246",

        "tagid": 1521,
        "tagpath": "supply/energy/cmphigh/ea",

        "scale": 1.0,

        "last_before": datetime(
            2026, 8, 20,
            11, 11, 1, 780000,
            tzinfo=TZ
        ),

        "value_before": 6737218.0,

        "first_after": datetime(
            2026, 8, 21,
            10, 46, 1, 801000,
            tzinfo=TZ
        ),

        "value_after": 6737218.0,

        "gnr_id": 8665,

        "old_value": 6.0,
        "old_accumulated": 6737218.0,

        "previous_accumulated": 6737212.0,

        # Lo mantenemos bastante estricto precisamente
        # porque el UUID aún es candidato.
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


    # Detectar milisegundos
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


    # -------------------------------------------------------------------------
    # DICT
    # -------------------------------------------------------------------------

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


    # -------------------------------------------------------------------------
    # LIST
    # -------------------------------------------------------------------------

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


    # -------------------------------------------------------------------------
    # Eliminar timestamps duplicados
    # -------------------------------------------------------------------------

    unicos = {}


    for punto in puntos:

        ts = epoch_ms(
            punto["dt"]
        )

        unicos[ts] = punto


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


    print()
    print(
        f"Consultando {equipo['name']}..."
    )


    response = requests.get(
        API_URL,
        headers=headers,
        params=params,
        timeout=60
    )


    print(
        f"HTTP: {response.status_code}"
    )


    response.raise_for_status()


    payload = response.json()


    # -------------------------------------------------------------------------
    # Guardar raw para auditoría
    # -------------------------------------------------------------------------

    os.makedirs(
        "clickie_raw_lote3",
        exist_ok=True
    )


    with open(
        f"clickie_raw_lote3/{equipo['key']}.json",
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


    for punto in puntos:

        punto["value"] = (
            punto["raw_value"]
            * equipo["scale"]
        )


        punto["t_stamp"] = epoch_ms(
            punto["dt"]
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
    distancia_mejor = None


    for punto in puntos:

        distancia = abs(
            (
                punto["dt"]
                - objetivo
            ).total_seconds()
        )


        if (
            distancia_mejor is None
            or distancia < distancia_mejor
        ):

            mejor = punto
            distancia_mejor = distancia


    if mejor is None:
        return None


    if (
        distancia_mejor
        > tolerancia_min * 60
    ):

        return None


    resultado = dict(mejor)

    resultado[
        "distance_seconds"
    ] = distancia_mejor


    return resultado


# =============================================================================
# VALIDACIÓN DE BORDES
# =============================================================================

def validar_borde(
    equipo,
    puntos,
    objetivo,
    valor_ignition
):

    lectura = buscar_mas_cercano(
        puntos,
        objetivo,
        TOLERANCIA_VALIDACION_MIN
    )


    if lectura is None:

        return {
            "ok": False,
            "reason": "SIN_LECTURA",
            "clickie": None,
            "diff": None
        }


    diferencia = (
        lectura["value"]
        - valor_ignition
    )


    ok = (
        abs(diferencia)
        <= equipo["max_edge_diff"]
    )


    return {
        "ok": ok,

        "reason":
            "OK"
            if ok
            else "DIFERENCIA_EXCESIVA",

        "clickie":
            lectura,

        "diff":
            diferencia
    }


# =============================================================================
# EXTRAER LECTURAS REALES DEL HUECO
# =============================================================================

def extraer_hueco(
    equipo,
    puntos
):

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

        if (
            inicio
            < punto["dt"]
            < fin
        ):

            filas.append({
                "dt":
                    punto["dt"],

                "t_stamp":
                    punto["t_stamp"],

                "raw_value":
                    punto["raw_value"],

                "value":
                    punto["value"]
            })


    filas.sort(
        key=lambda x: x["dt"]
    )


    return filas


# =============================================================================
# MONOTONÍA
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

        actual = fila[
            "value"
        ]


        if actual < anterior:

            errores.append({
                "dt":
                    fila["dt"],

                "anterior":
                    anterior,

                "actual":
                    actual
            })


        anterior = actual


    # Comparar último Clickie del hueco
    # contra primer valor real posterior de Ignition.

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
# DUPLICADOS
# =============================================================================

def validar_duplicados(filas):

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
# CIERRE OPERACIONAL 07:00
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


    accumulated = lectura[
        "value"
    ]


    consumo = (
        accumulated
        - equipo[
            "previous_accumulated"
        ]
    )


    if consumo < 0:

        return {
            "ok": False,
            "reason": "CONSUMO_NEGATIVO"
        }


    return {
        "ok": True,
        "reason": "OK",

        "dt":
            lectura["dt"],

        "distance_seconds":
            lectura[
                "distance_seconds"
            ],

        "accumulated":
            accumulated,

        "consumption":
            consumo
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
        f"Lecturas Clickie: "
        f"{len(puntos)}"
    )


    # -------------------------------------------------------------------------
    # Validar inicio
    # -------------------------------------------------------------------------

    inicio = validar_borde(
        equipo,
        puntos,
        equipo["last_before"],
        equipo["value_before"]
    )


    # -------------------------------------------------------------------------
    # Validar final
    # -------------------------------------------------------------------------

    fin = validar_borde(
        equipo,
        puntos,
        equipo["first_after"],
        equipo["value_after"]
    )


    print()
    print("BORDE INICIAL")

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
    print("BORDE FINAL")

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


    # -------------------------------------------------------------------------
    # Backfill real
    # -------------------------------------------------------------------------

    filas = extraer_hueco(
        equipo,
        puntos
    )


    errores_monotonia = validar_monotonia(
        equipo,
        filas
    )


    duplicados = validar_duplicados(
        filas
    )


    cierre = calcular_cierre(
        equipo,
        puntos
    )


    # -------------------------------------------------------------------------
    # Validación general
    # -------------------------------------------------------------------------

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
    print("BACKFILL")

    print(
        f"Lecturas reales: "
        f"{len(filas)}"
    )


    if filas:

        print(
            f"Primera: "
            f"{fmt_dt(filas[0]['dt'])} "
            f"-> {filas[0]['value']:,.3f}"
        )

        print(
            f"Última : "
            f"{fmt_dt(filas[-1]['dt'])} "
            f"-> {filas[-1]['value']:,.3f}"
        )


    print(
        f"Retrocesos: "
        f"{len(errores_monotonia)}"
    )


    print(
        f"Duplicados : "
        f"{len(duplicados)}"
    )


    print()
    print("CIERRE 07:00")


    if cierre["ok"]:

        print(
            f"Lectura      : "
            f"{fmt_dt(cierre['dt'])}"
        )

        print(
            f"EA cierre    : "
            f"{cierre['accumulated']:,.3f}"
        )

        print(
            f"Consumo viejo: "
            f"{equipo['old_value']:,.3f}"
        )

        print(
            f"Consumo nuevo: "
            f"{cierre['consumption']:,.3f}"
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

        "inicio": inicio,
        "fin": fin,

        "puntos": puntos,
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

def exportar_resumen(resultados):

    archivo = (
        "Backfill_Raspberry_Lote3_Resumen.csv"
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

def exportar_auditoria(resultados):

    archivo = (
        "Backfill_Raspberry_Lote3_Auditoria.csv"
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
            "t_stamp",

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

def generar_sql_historian(resultados):

    archivo = (
        "Backfill_Raspberry_Lote3_Historian.sql"
    )


    margen_ms = (
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
            "-- BACKFILL RASPBERRY LOTE 3\n"
        )

        f.write(
            "-- BLOMACS 10 / KHS 8 / COMPRESOR DE ALTA\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


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


            valores = []


            for fila in filas:

                valores.append(
                    "        "
                    f"({e['tagid']}, "
                    f"{sql_number(fila['value'])}"
                    "::double precision, "
                    f"{fila['t_stamp']}::bigint)"
                )


            f.write(
                ",\n".join(
                    valores
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
                f"          v.t_stamp - {margen_ms}\n"
                "          AND\n"
                f"          v.t_stamp + {margen_ms}\n"
                ");\n\n"
            )


        f.write(
            "-- ================================================================\n"
        )

        f.write(
            "-- VALIDAR ANTES DE COMMIT\n"
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
# SQL GNRMAIN
# =============================================================================

def generar_sql_gnr(resultados):

    archivo = (
        "Backfill_Raspberry_Lote3_gnrMain.sql"
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
            '-- ACTUALIZACION process."gnrMain"\n'
        )

        f.write(
            "-- LOTE 3\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


        for r in resultados:

            e = r[
                "equipo"
            ]


            cierre = r[
                "cierre"
            ]


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


            nuevo_acc = cierre[
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
                f'{sql_number(nuevo_acc)}\n'
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
            "-- VALIDAR RETURNING ANTES DE COMMIT\n"
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
        "BACKFILL RASPBERRY - LOTE 3"
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
                f"ERROR EN {equipo['name']}: "
                f"{error}"
            )


            resultado = {

                "equipo":
                    equipo,

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

                "puntos":
                    [],

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


    print()
    print("=" * 80)
    print("RESULTADO GENERAL")
    print("=" * 80)


    aprobados = 0


    for r in resultados:

        estado = (
            "APROBADO"
            if r["valid"]
            else "BLOQUEADO"
        )


        print(
            f"{r['equipo']['name']:<25}"
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
    print("Archivos generados:")

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
        "  clickie_raw_lote3/*.json"
    )


    print()
    print(
        "Ningún cambio fue realizado "
        "directamente sobre PostgreSQL."
    )


if __name__ == "__main__":
    main()