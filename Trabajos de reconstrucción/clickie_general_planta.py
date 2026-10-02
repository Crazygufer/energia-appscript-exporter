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


# =============================================================================
# CLICKIE - GENERAL PLANTA
# =============================================================================

CLICKIE_UUID = "57e397e6-391b-4d02-a49a-26bb399cfa53"


# =============================================================================
# IGNITION
# =============================================================================

TAG_ID = 1478

TAG_PATH = "ssee/energy/grlplant/ea"

TABLE_NAME = "timescaledb_history.sqlth_1_data"


# =============================================================================
# BORDES REALES CONFIRMADOS EN POSTGRESQL
# =============================================================================
#
# Último registro correcto ANTES de la pérdida de comunicación:
#
# 2026-08-20 11:11:01.780
# EA = 2.583.322 kWh
#
# Primer registro correcto DESPUÉS de recuperar comunicación:
#
# 2026-08-21 10:46:01.801
# EA = 2.666.835 kWh
#
# Estos dos registros NO deben insertarse.
# =============================================================================

ULTIMO_ANTES_FALLA = datetime(
    2026, 8, 20,
    11, 11, 1, 780000,
    tzinfo=TZ
)

VALOR_ULTIMO_ANTES_FALLA = 2583322.0


PRIMERO_DESPUES_FALLA = datetime(
    2026, 8, 21,
    10, 46, 1, 801000,
    tzinfo=TZ
)

VALOR_PRIMERO_DESPUES_FALLA = 2666835.0


# =============================================================================
# DÍA OPERACIONAL QUE QUEREMOS RECONSTRUIR
# =============================================================================
#
# Ignition tenía:
#
# 2026-08-20 06:59:12.611
# EA = 2.568.261
#
# La aplicación mostraba:
#
# 2.583.322 - 2.568.261 = 15.061 kWh
#
# Por lo tanto, ya validamos que estamos trabajando sobre el tag correcto.
# =============================================================================

INICIO_DIA_OPERACIONAL = datetime(
    2026, 8, 20,
    6, 59, 12, 611000,
    tzinfo=TZ
)

EA_INICIO_DIA = 2568261.0


CIERRE_DIA_OBJETIVO = datetime(
    2026, 8, 21,
    7, 0, 0,
    tzinfo=TZ
)


# =============================================================================
# PARÁMETROS DE RECONSTRUCCIÓN
# =============================================================================

# Cadencia observada en Ignition
INTERVALO_MINUTOS = 5


# Clickie no necesariamente registra justo en HH:MM:01.
# Buscamos la lectura más cercana.
TOLERANCIA_MINUTOS = 4


# Para validar los bordes podemos aceptar una ventana algo mayor.
TOLERANCIA_VALIDACION_MINUTOS = 10


# Margen adicional solicitado a la API.
MARGEN_API_MINUTOS = 15


# Diferencia máxima permitida entre Clickie e Ignition
# durante la validación de bordes.
#
# 1500 kWh es deliberadamente amplio.
# Si supera esto, el script detiene la generación del SQL.
MAX_DIFERENCIA_VALIDACION_KWH = 1500


# -----------------------------------------------------------------------------
# Evitar acercarnos demasiado al primer dato recuperado.
#
# Primer dato real:
# 10:46:01.801
#
# Último objetivo de backfill esperado:
# 10:41:01.780
#
# Con un margen de 2 minutos, nunca generaremos el punto 10:46.
# -----------------------------------------------------------------------------

MARGEN_FIN_HUECO_MINUTOS = 2


# -----------------------------------------------------------------------------
# Protección adicional en SQL.
#
# Si ya existe un punto de tagid 1478 dentro de +/- 2 minutos
# del timestamp que queremos insertar, NO se inserta.
# -----------------------------------------------------------------------------

PROTECCION_SQL_SEGUNDOS = 120


# =============================================================================
# UTILIDADES
# =============================================================================

def epoch_ms(dt):
    """
    Convierte datetime timezone-aware a epoch en milisegundos.
    """

    return int(round(dt.timestamp() * 1000))


def formato_dt(dt):
    """
    Formatea datetime para mostrarlo con milisegundos.
    """

    if dt is None:
        return ""

    return dt.strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


# =============================================================================
# PARSEO CLICKIE
# =============================================================================

def agregar_punto(puntos, ts, value):
    """
    Convierte timestamp y valor a un formato interno común.
    """

    try:
        ts = float(ts)
        value = float(value)

    except (TypeError, ValueError):
        return

    if not math.isfinite(value):
        return

    # -------------------------------------------------------------------------
    # Detectar timestamp en milisegundos
    # -------------------------------------------------------------------------

    if ts > 10_000_000_000:
        ts = ts / 1000.0

    try:

        dt = datetime.fromtimestamp(
            ts,
            TZ
        )

    except (
        ValueError,
        OSError,
        OverflowError
    ):
        return

    puntos.append({
        "timestamp": int(ts),
        "datetime": dt,
        "value": value
    })


def parse_clickie_response(payload):
    """
    Intenta interpretar distintos formatos posibles
    de respuesta de Clickie.
    """

    puntos = []

    # -------------------------------------------------------------------------
    # Extraer campo data si viene encapsulado
    # -------------------------------------------------------------------------

    if (
        isinstance(payload, dict)
        and "data" in payload
    ):
        data = payload["data"]

    else:
        data = payload


    # =========================================================================
    # FORMATO DICT
    # =========================================================================

    if isinstance(data, dict):

        for key, value in data.items():

            # -----------------------------------------------------------------
            # Ejemplo:
            #
            # {
            #   "1787280000": 2583000
            # }
            # -----------------------------------------------------------------

            if isinstance(
                value,
                (int, float, str)
            ):

                agregar_punto(
                    puntos,
                    key,
                    value
                )

            # -----------------------------------------------------------------
            # Ejemplo:
            #
            # {
            #   "x": {
            #       "timestamp": 1787280000,
            #       "value": 2583000
            #   }
            # }
            # -----------------------------------------------------------------

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
    # FORMATO LIST
    # =========================================================================

    elif isinstance(data, list):

        for item in data:

            # -----------------------------------------------------------------
            # Ejemplo:
            #
            # {
            #   "timestamp": 1787280000,
            #   "value": 2583000
            # }
            # -----------------------------------------------------------------

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

            # -----------------------------------------------------------------
            # Ejemplo:
            #
            # [1787280000, 2583000]
            # -----------------------------------------------------------------

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
    # ELIMINAR DUPLICADOS
    # =========================================================================

    unicos = {}

    for punto in puntos:

        unicos[
            punto["timestamp"]
        ] = punto


    puntos = list(
        unicos.values()
    )


    puntos.sort(
        key=lambda p: p["datetime"]
    )

    return puntos


# =============================================================================
# CONSULTA CLICKIE
# =============================================================================

def consultar_clickie(
    desde,
    hasta
):

    if not API_KEY:

        raise RuntimeError(
            "No existe CLICKIE_API_KEY "
            "en el archivo .env"
        )


    desde_api = (
        desde
        - timedelta(
            minutes=MARGEN_API_MINUTOS
        )
    )


    hasta_api = (
        hasta
        + timedelta(
            minutes=MARGEN_API_MINUTOS
        )
    )


    headers = {
        "Authorization": API_KEY,
        "Account": ACCOUNT_ID,
        "Accept": "application/json"
    }


    params = {
        "metric": CLICKIE_UUID,
        "from": int(
            desde_api.timestamp()
        ),
        "to": int(
            hasta_api.timestamp()
        )
    }


    print()
    print("=" * 80)
    print("CONSULTANDO CLICKIE")
    print("=" * 80)

    print(
        f"UUID  : {CLICKIE_UUID}"
    )

    print(
        f"Desde : {formato_dt(desde_api)}"
    )

    print(
        f"Hasta : {formato_dt(hasta_api)}"
    )


    response = requests.get(
        API_URL,
        params=params,
        headers=headers,
        timeout=60
    )


    print(
        f"HTTP  : {response.status_code}"
    )


    response.raise_for_status()


    try:

        payload = response.json()

    except Exception:

        with open(
            "clickie_respuesta_error.txt",
            "w",
            encoding="utf-8"
        ) as f:

            f.write(
                response.text
            )

        raise RuntimeError(
            "Clickie no devolvió JSON. "
            "Se guardó clickie_respuesta_error.txt"
        )


    # -------------------------------------------------------------------------
    # Guardar respuesta original para auditoría
    # -------------------------------------------------------------------------

    with open(
        "clickie_raw_response.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2
        )


    puntos = parse_clickie_response(
        payload
    )


    if not puntos:

        raise RuntimeError(
            "La API respondió pero no se pudo "
            "interpretar ninguna lectura. "
            "Revisa clickie_raw_response.json"
        )


    print()
    print(
        f"Lecturas interpretadas : "
        f"{len(puntos)}"
    )

    print(
        f"Primera lectura         : "
        f"{formato_dt(puntos[0]['datetime'])} "
        f"-> {puntos[0]['value']:,.3f}"
    )

    print(
        f"Última lectura          : "
        f"{formato_dt(puntos[-1]['datetime'])} "
        f"-> {puntos[-1]['value']:,.3f}"
    )


    return puntos


# =============================================================================
# BÚSQUEDA DE LECTURA MÁS CERCANA
# =============================================================================

def buscar_mas_cercano(
    puntos,
    objetivo,
    tolerancia_minutos
):

    mejor = None
    mejor_distancia = None


    for punto in puntos:

        distancia = abs(
            (
                punto["datetime"]
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
        > tolerancia_minutos * 60
    ):
        return None


    resultado = mejor.copy()

    resultado[
        "distancia_segundos"
    ] = mejor_distancia


    return resultado


# =============================================================================
# VALIDACIÓN CLICKIE VS IGNITION
# =============================================================================

def validar_borde(
    nombre,
    puntos,
    fecha_ignition,
    valor_ignition
):

    clickie = buscar_mas_cercano(
        puntos,
        fecha_ignition,
        TOLERANCIA_VALIDACION_MINUTOS
    )


    print()
    print(nombre)

    print(
        f"  Ignition : "
        f"{formato_dt(fecha_ignition)} "
        f"-> {valor_ignition:,.3f}"
    )


    if clickie is None:

        print(
            "  Clickie  : "
            "NO SE ENCONTRÓ LECTURA CERCANA"
        )

        return False


    diferencia = (
        clickie["value"]
        - valor_ignition
    )


    print(
        f"  Clickie  : "
        f"{formato_dt(clickie['datetime'])} "
        f"-> {clickie['value']:,.3f}"
    )


    print(
        f"  Distancia: "
        f"{clickie['distancia_segundos'] / 60:.2f} min"
    )


    print(
        f"  Delta    : "
        f"{diferencia:+,.3f} kWh"
    )


    if (
        abs(diferencia)
        > MAX_DIFERENCIA_VALIDACION_KWH
    ):

        print(
            "  RESULTADO: ERROR"
        )

        print(
            "  La diferencia entre Clickie "
            "e Ignition es demasiado grande."
        )

        return False


    print(
        "  RESULTADO: VALIDACIÓN ACEPTABLE"
    )

    return True


# =============================================================================
# RECONSTRUCCIÓN DEL HUECO
# =============================================================================

def reconstruir_hueco(puntos):

    filas = []


    # -------------------------------------------------------------------------
    # Primer punto:
    #
    # último existente = 11:11:01
    #
    # primer backfill   = 11:16:01
    # -------------------------------------------------------------------------

    objetivo = (
        ULTIMO_ANTES_FALLA
        + timedelta(
            minutes=INTERVALO_MINUTOS
        )
    )


    # -------------------------------------------------------------------------
    # Límite efectivo
    #
    # El primer dato REAL recuperado es:
    #
    # 10:46:01.801
    #
    # Restamos dos minutos.
    #
    # Por lo tanto:
    #
    # 10:41 entra.
    # 10:46 NO entra.
    # -------------------------------------------------------------------------

    limite_fin = (
        PRIMERO_DESPUES_FALLA
        - timedelta(
            minutes=MARGEN_FIN_HUECO_MINUTOS
        )
    )


    while objetivo < limite_fin:

        lectura = buscar_mas_cercano(
            puntos,
            objetivo,
            TOLERANCIA_MINUTOS
        )


        if lectura is None:

            filas.append({
                "target_dt": objetivo,
                "target_epoch_ms":
                    epoch_ms(objetivo),

                "value": None,

                "clickie_dt": None,

                "distance_seconds":
                    None
            })


        else:

            filas.append({
                "target_dt": objetivo,

                "target_epoch_ms":
                    epoch_ms(objetivo),

                "value":
                    lectura["value"],

                "clickie_dt":
                    lectura["datetime"],

                "distance_seconds":
                    lectura[
                        "distancia_segundos"
                    ]
            })


        objetivo += timedelta(
            minutes=INTERVALO_MINUTOS
        )


    return filas


# =============================================================================
# VALIDAR MONOTONÍA
# =============================================================================

def validar_monotonia(filas):

    """
    El EA es un acumulador.

    No debería disminuir.
    """

    validas = [
        fila
        for fila in filas
        if fila["value"] is not None
    ]


    errores = []


    valor_anterior = (
        VALOR_ULTIMO_ANTES_FALLA
    )


    for fila in validas:

        if (
            fila["value"]
            < valor_anterior
        ):

            errores.append({
                "timestamp":
                    fila["target_dt"],

                "anterior":
                    valor_anterior,

                "actual":
                    fila["value"]
            })


        valor_anterior = fila["value"]


    # -------------------------------------------------------------------------
    # Comparar último backfill contra primer dato recuperado
    # -------------------------------------------------------------------------

    if validas:

        ultimo = validas[-1]["value"]

        if (
            VALOR_PRIMERO_DESPUES_FALLA
            < ultimo
        ):

            errores.append({
                "timestamp":
                    PRIMERO_DESPUES_FALLA,

                "anterior":
                    ultimo,

                "actual":
                    VALOR_PRIMERO_DESPUES_FALLA
            })


    return errores


# =============================================================================
# CSV PARA BD
# =============================================================================

def exportar_csv_db(filas):

    archivo = (
        "General_Planta_Backfill_"
        "2026-08-20_2026-08-21.csv"
    )


    validas = [
        fila
        for fila in filas
        if fila["value"] is not None
    ]


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)


        writer.writerow([
            "tagid",
            "intvalue",
            "floatvalue",
            "stringvalue",
            "datevalue",
            "t_stamp"
        ])


        for row in validas:

            writer.writerow([
                TAG_ID,
                "",
                row["value"],
                "",
                "",
                row["target_epoch_ms"]
            ])


    return archivo


# =============================================================================
# CSV DE AUDITORÍA
# =============================================================================

def exportar_auditoria(filas):

    archivo = (
        "General_Planta_Backfill_Auditoria.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(f)


        writer.writerow([
            "timestamp_ignition_objetivo",
            "timestamp_clickie_utilizado",
            "distancia_segundos",
            "ea_kwh",
            "estado"
        ])


        for row in filas:

            if row["value"] is None:

                writer.writerow([
                    formato_dt(
                        row["target_dt"]
                    ),
                    "",
                    "",
                    "",
                    "SIN_DATO_CLICKIE"
                ])

            else:

                writer.writerow([
                    formato_dt(
                        row["target_dt"]
                    ),

                    formato_dt(
                        row["clickie_dt"]
                    ),

                    round(
                        row[
                            "distance_seconds"
                        ],
                        3
                    ),

                    row["value"],

                    "OK"
                ])


    return archivo


# =============================================================================
# GENERAR SQL SEGURO
# =============================================================================

def generar_sql(filas):

    """
    Genera SQL sin tocar PostgreSQL.

    Además de limitar correctamente el hueco,
    cada registro verifica que no exista ya
    otro punto del mismo tag dentro de +/- 2 minutos.
    """

    validas = [
        fila
        for fila in filas
        if fila["value"] is not None
    ]


    archivo = (
        "General_Planta_Backfill_Ignition.sql"
    )


    margen_ms = (
        PROTECCION_SQL_SEGUNDOS
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
            "-- BACKFILL GENERAL PLANTA / ENERGIA ACTIVA ACUMULADA\n"
        )

        f.write(
            "-- Fuente: Clickie\n"
        )

        f.write(
            f"-- Tag Ignition: {TAG_PATH}\n"
        )

        f.write(
            f"-- tagid: {TAG_ID}\n"
        )

        f.write(
            "-- ================================================================\n\n"
        )


        f.write(
            "-- Último punto real antes de la falla:\n"
        )

        f.write(
            f"-- {formato_dt(ULTIMO_ANTES_FALLA)} "
            f"= {VALOR_ULTIMO_ANTES_FALLA}\n"
        )


        f.write(
            "-- Primer punto real después de recuperar comunicación:\n"
        )

        f.write(
            f"-- {formato_dt(PRIMERO_DESPUES_FALLA)} "
            f"= {VALOR_PRIMERO_DESPUES_FALLA}\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


        if not validas:

            f.write(
                "-- No existen filas válidas para insertar.\n"
            )

        else:

            # =================================================================
            # Una sola sentencia INSERT.
            # =================================================================

            f.write(
                f"INSERT INTO {TABLE_NAME}\n"
            )

            f.write(
                "(\n"
                "    tagid,\n"
                "    floatvalue,\n"
                "    t_stamp\n"
                ")\n"
            )

            f.write(
                "SELECT\n"
                "    v.tagid,\n"
                "    v.floatvalue,\n"
                "    v.t_stamp\n"
                "FROM\n"
                "(\n"
                "    VALUES\n"
            )


            valores = []


            for row in validas:

                valor = (
                    f"        "
                    f"({TAG_ID}, "
                    f"{row['value']:.10f}::double precision, "
                    f"{row['target_epoch_ms']}::bigint)"
                )

                valores.append(
                    valor
                )


            f.write(
                ",\n".join(valores)
            )


            f.write(
                "\n"
                ") AS v(tagid, floatvalue, t_stamp)\n"
            )


            f.write(
                "WHERE NOT EXISTS\n"
                "(\n"
                "    SELECT 1\n"
                f"    FROM {TABLE_NAME} existente\n"
                "    WHERE existente.tagid = v.tagid\n"
                "      AND existente.t_stamp BETWEEN\n"
                f"          v.t_stamp - {margen_ms}\n"
                "          AND\n"
                f"          v.t_stamp + {margen_ms}\n"
                ");\n"
            )


        f.write(
            "\nCOMMIT;\n"
        )


    return archivo


# =============================================================================
# CONSUMO DÍA OPERACIONAL
# =============================================================================

def calcular_consumo_dia(puntos):

    cierre = buscar_mas_cercano(
        puntos,
        CIERRE_DIA_OBJETIVO,
        TOLERANCIA_VALIDACION_MINUTOS
    )


    if cierre is None:
        return None


    consumo = (
        cierre["value"]
        - EA_INICIO_DIA
    )


    return {
        "cierre_clickie":
            cierre,

        "consumo":
            consumo
    }


# =============================================================================
# MAIN
# =============================================================================

def main():

    print(
        "=" * 80
    )

    print(
        "RECUPERACIÓN HISTÓRICA - GENERAL PLANTA"
    )

    print(
        "=" * 80
    )


    print()
    print("TAG IGNITION")

    print(
        f"  tagid   : {TAG_ID}"
    )

    print(
        f"  tagpath : {TAG_PATH}"
    )


    print()
    print("HUECO CONFIRMADO")


    print(
        f"  Último antes de falla : "
        f"{formato_dt(ULTIMO_ANTES_FALLA)} "
        f"-> {VALOR_ULTIMO_ANTES_FALLA:,.3f}"
    )


    print(
        f"  Primero recuperado    : "
        f"{formato_dt(PRIMERO_DESPUES_FALLA)} "
        f"-> {VALOR_PRIMERO_DESPUES_FALLA:,.3f}"
    )


    print(
        f"  Duración               : "
        f"{PRIMERO_DESPUES_FALLA - ULTIMO_ANTES_FALLA}"
    )


    # =========================================================================
    # CONSULTAR CLICKIE
    # =========================================================================

    puntos = consultar_clickie(
        ULTIMO_ANTES_FALLA,
        PRIMERO_DESPUES_FALLA
    )


    # =========================================================================
    # VALIDACIÓN DE BORDES
    # =========================================================================

    print()
    print(
        "=" * 80
    )

    print(
        "VALIDACIÓN CRUZADA CLICKIE / IGNITION"
    )

    print(
        "=" * 80
    )


    validacion_inicio = validar_borde(
        "BORDE ANTES DE LA FALLA",
        puntos,
        ULTIMO_ANTES_FALLA,
        VALOR_ULTIMO_ANTES_FALLA
    )


    validacion_fin = validar_borde(
        "BORDE DESPUÉS DE LA FALLA",
        puntos,
        PRIMERO_DESPUES_FALLA,
        VALOR_PRIMERO_DESPUES_FALLA
    )


    if (
        not validacion_inicio
        or not validacion_fin
    ):

        print()
        print(
            "=" * 80
        )

        print(
            "PROCESO DETENIDO"
        )

        print(
            "=" * 80
        )

        print(
            "Clickie no pasó la validación "
            "contra los valores conocidos "
            "de Ignition."
        )

        print(
            "NO se generó el SQL."
        )

        return


    # =========================================================================
    # RECONSTRUIR HUECO
    # =========================================================================

    filas = reconstruir_hueco(
        puntos
    )


    validas = [
        fila
        for fila in filas
        if fila["value"] is not None
    ]


    faltantes = [
        fila
        for fila in filas
        if fila["value"] is None
    ]


    print()
    print(
        "=" * 80
    )

    print(
        "RECONSTRUCCIÓN DEL HUECO"
    )

    print(
        "=" * 80
    )


    print(
        f"Puntos esperados    : "
        f"{len(filas)}"
    )


    print(
        f"Puntos recuperados  : "
        f"{len(validas)}"
    )


    print(
        f"Sin dato Clickie    : "
        f"{len(faltantes)}"
    )


    if validas:

        print()

        print(
            "Primer punto a insertar:"
        )

        print(
            f"  Objetivo : "
            f"{formato_dt(validas[0]['target_dt'])}"
        )

        print(
            f"  Clickie  : "
            f"{formato_dt(validas[0]['clickie_dt'])}"
        )

        print(
            f"  EA       : "
            f"{validas[0]['value']:,.3f}"
        )


        print()

        print(
            "Último punto a insertar:"
        )

        print(
            f"  Objetivo : "
            f"{formato_dt(validas[-1]['target_dt'])}"
        )

        print(
            f"  Clickie  : "
            f"{formato_dt(validas[-1]['clickie_dt'])}"
        )

        print(
            f"  EA       : "
            f"{validas[-1]['value']:,.3f}"
        )


    # =========================================================================
    # VALIDAR MONOTONÍA
    # =========================================================================

    errores_monotonia = validar_monotonia(
        filas
    )


    print()
    print(
        "=" * 80
    )

    print(
        "VALIDACIÓN DEL ACUMULADOR"
    )

    print(
        "=" * 80
    )


    if errores_monotonia:

        print(
            "ERROR: se detectaron retrocesos "
            "en el acumulador."
        )


        for error in errores_monotonia:

            print(
                f"{formato_dt(error['timestamp'])} | "
                f"{error['anterior']:,.3f} -> "
                f"{error['actual']:,.3f}"
            )


        print()
        print(
            "NO se generará el SQL."
        )

        return


    print(
        "Acumulador monotónico: OK"
    )


    # =========================================================================
    # CONSUMO DEL DÍA
    # =========================================================================

    resultado_dia = calcular_consumo_dia(
        puntos
    )


    print()
    print(
        "=" * 80
    )

    print(
        "CONSUMO DÍA OPERACIONAL 20-08-2026"
    )

    print(
        "=" * 80
    )


    print(
        f"Inicio Ignition : "
        f"{formato_dt(INICIO_DIA_OPERACIONAL)}"
    )


    print(
        f"EA inicial      : "
        f"{EA_INICIO_DIA:,.3f} kWh"
    )


    if resultado_dia is None:

        print(
            "No fue posible encontrar "
            "una lectura Clickie cercana "
            "a 2026-08-21 07:00."
        )

    else:

        cierre = resultado_dia[
            "cierre_clickie"
        ]


        print(
            f"Cierre Clickie  : "
            f"{formato_dt(cierre['datetime'])}"
        )


        print(
            f"EA cierre       : "
            f"{cierre['value']:,.3f} kWh"
        )


        print()

        print(
            f"CONSUMO REAL    : "
            f"{resultado_dia['consumo']:,.3f} kWh"
        )


    # =========================================================================
    # GENERAR ARCHIVOS
    # =========================================================================

    csv_db = exportar_csv_db(
        filas
    )


    csv_auditoria = exportar_auditoria(
        filas
    )


    sql_file = generar_sql(
        filas
    )


    print()
    print(
        "=" * 80
    )

    print(
        "ARCHIVOS GENERADOS"
    )

    print(
        "=" * 80
    )


    print(
        f"CSV BD      : {csv_db}"
    )


    print(
        f"Auditoría   : {csv_auditoria}"
    )


    print(
        f"SQL         : {sql_file}"
    )


    print(
        "Raw Clickie : clickie_raw_response.json"
    )


    # =========================================================================
    # ADVERTENCIAS
    # =========================================================================

    if faltantes:

        print()
        print(
            "ADVERTENCIA"
        )

        print(
            "Existen timestamps para los cuales "
            "Clickie no encontró una lectura "
            "dentro de la tolerancia."
        )

        print(
            "Esos registros NO fueron incluidos "
            "en el SQL."
        )


    print()
    print(
        "=" * 80
    )

    print(
        "POSTGRESQL NO FUE MODIFICADO"
    )

    print(
        "=" * 80
    )

    print(
        "Revisa los archivos generados "
        "antes de ejecutar el SQL."
    )


if __name__ == "__main__":
    main()