# =============================================================================
# AUDITORÍA CLICKIE MULTI-MEDIDOR / RASPBERRY -> IGNITION
# =============================================================================
#
# OBJETIVO GENERAL
# -----------------------------------------------------------------------------
# Este script consulta Clickie para un conjunto controlado de medidores que hoy
# forman parte de la cadena Raspberry -> Ignition y sobre los cuales existen
# dudas de escalamiento, discontinuidades, resets o cambios de régimen.
#
# El foco NO es modificar PostgreSQL.
#
# El foco es construir una referencia independiente y auditable de:
#
#     consumo diario operacional = 07:00 del día D -> 07:00 del día D+1
#
# utilizando la misma idea de negocio que hemos venido usando con Clickie:
#
#     consumo = última lectura válida del período
#             - primera lectura válida del período
#
# Para los medidores donde ya existe una escala de negocio validada/provisional,
# la escala se aplica al totalizador y al delta antes de expresarlo como kWh.
#
# IMPORTANTE
# -----------------------------------------------------------------------------
# ESTE SCRIPT:
#
#     - NO se conecta a PostgreSQL.
#     - NO ejecuta INSERT.
#     - NO ejecuta UPDATE.
#     - NO ejecuta DELETE.
#     - NO modifica Ignition.
#
# Genera archivos CSV de auditoría y, opcionalmente, compara contra un CSV
# exportado manualmente desde gnrProDb01.process."gnrMain".
#
# =============================================================================


# =============================================================================
# IMPORTACIONES
# =============================================================================

import csv
import json
import math
import os
import time as time_module

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv


# =============================================================================
# RUTAS DEL PROYECTO
# =============================================================================
#
# Estructura esperada:
#
# TELEMETRIA_MODULAR/
# │
# ├── .env
# │
# └── auditoria_clickie_raspberry/
#     │
#     ├── auditoria_clickie_multi.py
#     │
#     ├── raw/
#     │
#     ├── reportes/
#     │
#     └── sql/
#
# Si ejecutas este archivo desde otra ubicación, las carpetas se crean respecto
# del directorio donde se encuentre este script.
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent

RAW_DIR = BASE_DIR / "raw"
REPORT_DIR = BASE_DIR / "reportes"
SQL_DIR = BASE_DIR / "sql"

RAW_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
SQL_DIR.mkdir(parents=True, exist_ok=True)


# =============================================================================
# VARIABLES DE ENTORNO
# =============================================================================
#
# En TELEMETRIA_MODULAR/.env deberían existir, idealmente:
#
# CLICKIE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
# CLICKIE_ACCOUNT_ID=63
#
# No se recomienda volver a dejar la API KEY escrita dentro del código.
# =============================================================================



CLICKIE_API_KEY = "0580c356-8b91-4298-bd20-385c2f46226a"
CLICKIE_ACCOUNT_ID = "63"


# =============================================================================
# CONFIGURACIÓN CLICKIE
# =============================================================================

TZ = ZoneInfo("America/Santiago")

API_URL = "https://api.clickie.io/v4/data/metric"

HTTP_TIMEOUT_SECONDS = 90
HTTP_MAX_RETRIES = 4
HTTP_RETRY_BASE_SECONDS = 2

# ----------------------------------------------------------------------------
# Se consulta por bloques temporales pequeños para no pedir de una sola vez
# cientos de miles de puntos.
#
# 7 días suele ser razonable para series con cadencia de pocos minutos.
# Si Clickie devuelve 413, el script subdivide automáticamente el bloque.
# ----------------------------------------------------------------------------

API_CHUNK_DAYS = 7

# ----------------------------------------------------------------------------
# Margen agregado a cada chunk para no perder puntos justo en un borde.
# Los puntos repetidos se deduplican posteriormente por timestamp.
# ----------------------------------------------------------------------------

API_MARGIN_MINUTES = 15

# ----------------------------------------------------------------------------
# Guardar cada JSON de respuesta puede generar cientos de archivos.
# Por defecto queda desactivado.
#
# La serie interpretada completa SIEMPRE se guarda en CSV por medidor.
# ----------------------------------------------------------------------------

SAVE_CHUNK_JSON = False


# =============================================================================
# REGLA DEL DÍA OPERACIONAL
# =============================================================================
#
# Día D:
#
#     inicio = D     07:00:00
#     fin    = D + 1 07:00:00
#
# El punto de las 07:00 del día siguiente queda fuera del intervalo, de forma
# equivalente a:
#
#     [inicio, fin)
#
# Usamos la primera y última lectura REAL existentes dentro del período.
# =============================================================================

OPERATIONAL_HOUR = 7
OPERATIONAL_MINUTE = 0

# ----------------------------------------------------------------------------
# Si la primera/última muestra queda demasiado lejos del borde, no descartamos
# automáticamente el día, pero lo dejamos marcado para revisión.
# ----------------------------------------------------------------------------

MAX_RECOMMENDED_EDGE_GAP_MINUTES = 15


# =============================================================================
# PERÍODO DE AUDITORÍA
# =============================================================================
#
# gnrMain comenzó a mostrarnos datos desde comienzos de enero de 2026.
# Partimos desde el 02-01-2026.
#
# El 04-08-2026 se usa como frontera de referencia porque en los ensayos de
# H400-3/H500-2 ya vimos que desde ese régimen los resultados vuelven a quedar
# cercanos a Clickie.
#
# OJO:
# Esta frontera NO significa que todos los otros medidores estén buenos desde
# esa fecha. Solamente sirve para separar los reportes:
#
#     HISTORICO_AUDITAR
#     VALIDACION_POST_CAMBIO
# =============================================================================

FIRST_OPERATIONAL_DAY = date(2026, 1, 2)
POST_CHANGE_START_DAY = date(2026, 8, 4)

CRITICAL_PERIOD_START = date(2026, 7, 30)
CRITICAL_PERIOD_END = date(2026, 8, 10)


# =============================================================================
# MEDIDORES AUDITADOS
# =============================================================================
#
# PRINCIPIO IMPORTANTE SOBRE ESCALA:
#
#     Clickie entrega un valor RAW.
#
# Para algunos UUID ya se había definido una escala de negocio de 0.1.
# Ese factor NO se usa para "forzar" una coincidencia.
# Se usa porque ya es parte de la interpretación energética conocida del equipo.
#
# Por eso el reporte conserva SIEMPRE:
#
#     raw_first
#     raw_last
#     raw_delta
#
# y adicionalmente calcula:
#
#     ea_inicio_kwh = raw_first * scale
#     ea_fin_kwh    = raw_last  * scale
#     consumo_kwh   = raw_delta * scale
#
# De esa manera podemos auditar tanto el dato original como el dato de negocio.
#
# -----------------------------------------------------------------------------
# EQUIPOS PRINCIPALES CON DUDA DE ESCALA / DISCONTINUIDAD
# -----------------------------------------------------------------------------
#
# H400-3 / H500-2:
#     escala Clickie = 1
#     se incluyen por el evento de cambio de régimen que acabamos de estudiar.
#
# IPS400-2:
#     escala 0.1 VALIDATED.
#
# CCM2 / CCM3:
#     escala 0.1 VALIDATED.
#
# Blomacs 10:
#     escala 0.1 VALIDATED.
#
# KHS8:
#     escala 0.1 PROVISIONAL por discontinuidades/reset.
#
# -----------------------------------------------------------------------------
# CONTROLES
# -----------------------------------------------------------------------------
#
# CCM1:
#     Se incluye como control porque pertenece al mismo grupo funcional que
#     CCM2/CCM3 y permite comparar comportamiento sin asumir que toda la familia
#     debe usar la misma escala.
#
# SB08:
#     Se incluye como control de Soplado/Raspberry.
# =============================================================================

EQUIPMENTS = [
    {
        "name": "Hypet 400-3",
        "code": "hyp400_3",
        "uuid": "38e371c4-f2e7-46ed-a0a7-7ba6a5dab360",
        "scale": 1.0,
        "scale_status": "DEFAULT",
        "reason": "Caso crítico estudiado: transición de escala/discontinuidades en Ignition.",
    },
    {
        "name": "Hypet 500-2",
        "code": "hyp500_2",
        "uuid": "9faeb035-e10e-4fd9-87f4-70632f2753d2",
        "scale": 1.0,
        "scale_status": "DEFAULT",
        "reason": "Caso crítico estudiado: transición de escala/discontinuidades en Ignition.",
    },
    {
        "name": "IPS 400-2",
        "code": "ips400_2",
        "uuid": "6da7639c-7481-405d-9415-3e599bc8dd02",
        "scale": 0.1,
        "scale_status": "VALIDATED",
        "reason": "Escala 0.1 previamente conciliada contra referencia Clickie.",
    },
    {
        "name": "CCM 2",
        "code": "ccm2",
        "uuid": "2c0fde28-81d3-404f-9983-9db8f2fb2e3d",
        "scale": 0.1,
        "scale_status": "VALIDATED",
        "reason": "Escala 0.1 previamente conciliada contra referencia Clickie.",
    },
    {
        "name": "CCM 3",
        "code": "ccm3",
        "uuid": "bdb14b8e-b06e-4d48-b683-13f0d3dc271d",
        "scale": 0.1,
        "scale_status": "VALIDATED",
        "reason": "Escala 0.1 previamente conciliada contra referencia Clickie.",
    },
    {
        "name": "Blomacs 10",
        "code": "blm10",
        "uuid": "263f108c-b499-4706-8ffd-24a4e71096ab",
        "scale": 0.1,
        "scale_status": "VALIDATED",
        "reason": "Escala 0.1 previamente validada; se audita además por discontinuidades observadas.",
    },
    {
        "name": "KHS 8",
        "code": "khs8",
        "uuid": "4a6fbb73-d1ff-4ae5-b6a1-236df6fdeb57",
        "scale": 0.1,
        "scale_status": "PROVISIONAL",
        "reason": "Escala 0.1 provisional; acumulador ha mostrado discontinuidades/reset.",
    },
    {
        "name": "CCM 1",
        "code": "ccm1",
        "uuid": "ff0263d8-07a0-4d37-8840-88d4414ada88",
        "scale": 1.0,
        "scale_status": "CONTROL",
        "reason": "Control de comparación frente a CCM2/CCM3; no aplicar escala por familia sin validar.",
    },
    {
        "name": "SB08",
        "code": "sb08",
        "uuid": "cf8918f9-50c6-42be-84e3-46905b288fa8",
        "scale": 1.0,
        "scale_status": "CONTROL",
        "reason": "Control adicional de Soplado/Raspberry.",
    },
]


# =============================================================================
# TOLERANCIAS PARA COMPARAR CLICKIE VS gnrMain
# =============================================================================
#
# Estas tolerancias SOLO se usan si existe:
#
#     reportes/gnrMain_Auditoria.csv
#
# No modifican la captura Clickie.
# =============================================================================

COMPARE_ABS_TOLERANCE_KWH = 5.0
COMPARE_REL_TOLERANCE = 0.02  # 2 %

# Factores típicos que queremos detectar automáticamente cuando el valor de
# gnrMain parece estar en otra escala.
SCALE_FACTORS_TO_TEST = [
    0.001,
    0.01,
    0.1,
    10.0,
    100.0,
    1000.0,
]


# =============================================================================
# ARCHIVOS DE SALIDA
# =============================================================================

MASTER_REPORT_FILE = REPORT_DIR / "Clickie_Auditoria_Multi_07a07.csv"
POST_CHANGE_FILE = REPORT_DIR / "Clickie_Validacion_PostCambio.csv"
CRITICAL_PERIOD_FILE = REPORT_DIR / "Clickie_Periodo_Critico.csv"
SUMMARY_FILE = REPORT_DIR / "Clickie_Resumen_Equipos.csv"
CONFIG_FILE = REPORT_DIR / "Clickie_Configuracion_Auditoria.csv"

GNRMAIN_EXPORT_EXPECTED_FILE = REPORT_DIR / "gnrMain_Auditoria.csv"
GNRMAIN_QUERY_FILE = SQL_DIR / "gnrMain_Auditoria_Query.sql"

COMPARISON_FILE = REPORT_DIR / "Comparacion_Clickie_gnrMain.csv"
CORRECTIONS_FILE = REPORT_DIR / "Correcciones_Candidatas.csv"


# =============================================================================
# FUNCIONES DE FECHA / FORMATO
# =============================================================================

def format_datetime(dt):
    """Devuelve datetime legible con milisegundos."""

    if dt is None:
        return ""

    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def operational_start(day):
    """Construye el inicio 07:00 del día operacional indicado."""

    return datetime.combine(
        day,
        time(OPERATIONAL_HOUR, OPERATIONAL_MINUTE),
        tzinfo=TZ,
    )


def last_closed_operational_day():
    """
    Determina automáticamente cuál es el último día operacional completamente
    cerrado.

    Ejemplo:

        ahora = 24-08 12:00
        último día cerrado = 23-08

    porque:

        23-08 07:00 -> 24-08 07:00

    ya terminó.
    """

    now = datetime.now(TZ)
    today_cut = operational_start(now.date())

    if now >= today_cut:
        return now.date() - timedelta(days=1)

    return now.date() - timedelta(days=2)


def daterange_inclusive(start_day, end_day):
    """Itera fechas incluyendo ambos extremos."""

    current = start_day

    while current <= end_day:
        yield current
        current += timedelta(days=1)


# =============================================================================
# PARSEO DE LA RESPUESTA CLICKIE
# =============================================================================

def add_point(points, ts, value):
    """
    Normaliza timestamp y valor recibidos desde Clickie.

    Acepta epoch en segundos o milisegundos.
    """

    try:
        ts = float(ts)
        value = float(value)
    except (TypeError, ValueError):
        return

    if not math.isfinite(ts) or not math.isfinite(value):
        return

    # Epoch muy grande -> probablemente milisegundos.
    if ts > 10_000_000_000:
        ts = ts / 1000.0

    try:
        dt = datetime.fromtimestamp(ts, TZ)
    except (ValueError, OSError, OverflowError):
        return

    points.append(
        {
            "timestamp": int(ts),
            "datetime": dt,
            "value": value,
        }
    )


def parse_clickie_response(payload):
    """
    Interpreta distintos formatos posibles de respuesta Clickie.

    Formatos soportados, entre otros:

        {"1780000000": 123456.7}

        {
            "data": {
                "1780000000": 123456.7
            }
        }

        [
            [1780000000, 123456.7],
            ...
        ]

        [
            {"timestamp": 1780000000, "value": 123456.7},
            ...
        ]
    """

    points = []

    if isinstance(payload, dict) and "data" in payload:
        data = payload["data"]
    else:
        data = payload

    if isinstance(data, dict):
        for key, item in data.items():
            if isinstance(item, (int, float, str)):
                add_point(points, key, item)

            elif isinstance(item, dict):
                ts = (
                    item.get("timestamp")
                    or item.get("ts")
                    or item.get("time")
                    or item.get("date")
                    or key
                )

                value = (
                    item.get("value")
                    if item.get("value") is not None
                    else item.get("val")
                )

                if value is not None:
                    add_point(points, ts, value)

    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                ts = (
                    item.get("timestamp")
                    or item.get("ts")
                    or item.get("time")
                    or item.get("date")
                )

                value = (
                    item.get("value")
                    if item.get("value") is not None
                    else item.get("val")
                )

                if ts is not None and value is not None:
                    add_point(points, ts, value)

            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                add_point(points, item[0], item[1])

    # -------------------------------------------------------------------------
    # Deduplicación por segundo epoch.
    # -------------------------------------------------------------------------
    # Si el backend devolviera dos puntos del mismo segundo, conservamos el
    # último interpretado.
    # -------------------------------------------------------------------------

    unique = {}

    for point in points:
        unique[point["timestamp"]] = point

    result = list(unique.values())
    result.sort(key=lambda p: p["datetime"])

    return result


# =============================================================================
# CLIENTE HTTP CLICKIE
# =============================================================================

def build_headers():
    """Construye headers de Clickie y valida credenciales."""

    if not CLICKIE_API_KEY:
        raise RuntimeError(
            "No existe CLICKIE_API_KEY en el archivo .env.\n"
            f"Ruta esperada: {PROJECT_ROOT / '.env'}"
        )

    return {
        "Authorization": CLICKIE_API_KEY,
        "Account": CLICKIE_ACCOUNT_ID,
        "Accept": "application/json",
    }


def request_clickie_once(session, equipment, start_dt, end_dt):
    """
    Ejecuta una consulta Clickie para un rango temporal.

    end_dt se manda como timestamp final incluido por la API.
    """

    params = {
        "metric": equipment["uuid"],
        "from": int(start_dt.timestamp()),
        "to": int(end_dt.timestamp()),
    }

    response = session.get(
        API_URL,
        params=params,
        headers=build_headers(),
        timeout=HTTP_TIMEOUT_SECONDS,
    )

    return response


def request_clickie_with_retries(session, equipment, start_dt, end_dt):
    """
    Consulta Clickie con reintentos para errores transitorios.

    413 se trata aparte porque significa que el rango debe subdividirse.
    """

    last_error = None

    for attempt in range(1, HTTP_MAX_RETRIES + 1):
        try:
            response = request_clickie_once(
                session,
                equipment,
                start_dt,
                end_dt,
            )

            # 413 se devuelve al llamador para subdividir rango.
            if response.status_code == 413:
                return response

            # 408 / 429 / 5xx pueden ser transitorios.
            if (
                response.status_code == 408
                or response.status_code == 429
                or response.status_code >= 500
            ):
                last_error = RuntimeError(
                    f"HTTP transitorio {response.status_code}: {response.text[:500]}"
                )

                if attempt < HTTP_MAX_RETRIES:
                    wait_seconds = HTTP_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                    time_module.sleep(wait_seconds)
                    continue

            response.raise_for_status()
            return response

        except requests.RequestException as exc:
            last_error = exc

            if attempt < HTTP_MAX_RETRIES:
                wait_seconds = HTTP_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                time_module.sleep(wait_seconds)
                continue

            raise

    raise RuntimeError(
        f"Clickie no respondió correctamente. Último error: {last_error}"
    )


def fetch_range_recursive(session, equipment, start_dt, end_dt, depth=0):
    """
    Descarga un rango.

    Si Clickie responde 413, divide el rango en dos y vuelve a consultar.
    """

    response = request_clickie_with_retries(
        session,
        equipment,
        start_dt,
        end_dt,
    )

    if response.status_code != 413:
        try:
            payload = response.json()
        except Exception:
            error_file = RAW_DIR / f"error_{equipment['code']}.txt"
            error_file.write_text(response.text, encoding="utf-8")
            raise RuntimeError(
                f"Clickie no devolvió JSON para {equipment['name']}. "
                f"Respuesta guardada en {error_file}"
            )

        if SAVE_CHUNK_JSON:
            equipment_dir = RAW_DIR / equipment["code"]
            equipment_dir.mkdir(parents=True, exist_ok=True)

            chunk_file = equipment_dir / (
                f"{start_dt.strftime('%Y%m%d_%H%M%S')}__"
                f"{end_dt.strftime('%Y%m%d_%H%M%S')}.json"
            )

            with chunk_file.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)

        return parse_clickie_response(payload)

    # -------------------------------------------------------------------------
    # 413: subdividir.
    # -------------------------------------------------------------------------

    total_seconds = (end_dt - start_dt).total_seconds()

    if total_seconds <= 3600:
        raise RuntimeError(
            f"Clickie devolvió 413 incluso con un rango <= 1 hora para "
            f"{equipment['name']}."
        )

    middle = start_dt + (end_dt - start_dt) / 2

    left = fetch_range_recursive(
        session,
        equipment,
        start_dt,
        middle,
        depth + 1,
    )

    right = fetch_range_recursive(
        session,
        equipment,
        middle,
        end_dt,
        depth + 1,
    )

    return left + right


def fetch_equipment_series(equipment, global_start, global_end):
    """
    Descarga toda la serie de un equipo por chunks semanales.

    Devuelve la serie deduplicada y ordenada.
    """

    print()
    print("=" * 100)
    print(f"CLICKIE | {equipment['name']} | {equipment['code']}")
    print("=" * 100)
    print(f"UUID           : {equipment['uuid']}")
    print(f"Escala negocio : {equipment['scale']}")
    print(f"Estado escala  : {equipment['scale_status']}")
    print(f"Desde          : {format_datetime(global_start)}")
    print(f"Hasta          : {format_datetime(global_end)}")

    all_points = []

    session = requests.Session()

    chunk_start = global_start
    chunk_number = 0

    while chunk_start < global_end:
        chunk_number += 1

        chunk_end = min(
            chunk_start + timedelta(days=API_CHUNK_DAYS),
            global_end,
        )

        query_start = chunk_start - timedelta(minutes=API_MARGIN_MINUTES)
        query_end = chunk_end + timedelta(minutes=API_MARGIN_MINUTES)

        print(
            f"  Chunk {chunk_number:03d}: "
            f"{format_datetime(query_start)} -> {format_datetime(query_end)}"
        )

        points = fetch_range_recursive(
            session,
            equipment,
            query_start,
            query_end,
        )

        all_points.extend(points)

        chunk_start = chunk_end

    # -------------------------------------------------------------------------
    # Deduplicar nuevamente porque usamos márgenes entre chunks.
    # -------------------------------------------------------------------------

    unique = {}

    for point in all_points:
        unique[point["timestamp"]] = point

    merged = list(unique.values())
    merged.sort(key=lambda p: p["datetime"])

    print(f"Lecturas finales: {len(merged):,}")

    if merged:
        print(
            f"Primera lectura: {format_datetime(merged[0]['datetime'])} "
            f"-> {merged[0]['value']:,.6f}"
        )
        print(
            f"Última lectura : {format_datetime(merged[-1]['datetime'])} "
            f"-> {merged[-1]['value']:,.6f}"
        )

    return merged


# =============================================================================
# EXPORTACIÓN RAW POR MEDIDOR
# =============================================================================

def export_raw_equipment_csv(equipment, points):
    """
    Guarda la serie Clickie interpretada completa de un equipo.

    Este archivo es útil para auditoría puntual de resets, ceros o saltos.
    """

    file_path = RAW_DIR / f"clickie_raw_{equipment['code']}.csv"

    with file_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)

        writer.writerow(
            [
                "equipo",
                "codigo",
                "uuid",
                "escala_negocio",
                "fecha_hora",
                "epoch",
                "valor_raw",
                "valor_kwh_escalado",
            ]
        )

        for point in points:
            writer.writerow(
                [
                    equipment["name"],
                    equipment["code"],
                    equipment["uuid"],
                    equipment["scale"],
                    format_datetime(point["datetime"]),
                    point["timestamp"],
                    point["value"],
                    point["value"] * equipment["scale"],
                ]
            )

    return file_path


# =============================================================================
# ANÁLISIS INTERNO DE UN DÍA OPERACIONAL
# =============================================================================

def points_inside_day(points, start_dt, end_dt):
    """
    Devuelve puntos en el intervalo [start_dt, end_dt).

    Se mantiene simple a propósito.
    """

    return [
        point
        for point in points
        if start_dt <= point["datetime"] < end_dt
    ]


def count_internal_negative_steps(day_points):
    """
    Cuenta cuántas veces el acumulador disminuye entre muestras consecutivas.

    NO corrige nada.
    Solo sirve para detectar resets/discontinuidades internas.
    """

    count = 0

    for previous, current in zip(day_points, day_points[1:]):
        if current["value"] < previous["value"]:
            count += 1

    return count


def build_daily_row(equipment, day, points):
    """
    Construye una fila de auditoría para un día operacional.

    Método principal:

        raw_delta = raw_last - raw_first

        consumo_kwh = raw_delta * scale

    Se conserva toda la información de borde para poder revisar diferencias.
    """

    start_dt = operational_start(day)
    end_dt = start_dt + timedelta(days=1)

    day_points = points_inside_day(points, start_dt, end_dt)

    tramo = (
        "HISTORICO_AUDITAR"
        if day < POST_CHANGE_START_DAY
        else "VALIDACION_POST_CAMBIO"
    )

    base = {
        "equipo": equipment["name"],
        "codigo": equipment["code"],
        "uuid": equipment["uuid"],
        "escala": equipment["scale"],
        "estado_escala": equipment["scale_status"],
        "tramo": tramo,
        "dia_operacional": day.isoformat(),
        "inicio_objetivo": start_dt,
        "fin_objetivo": end_dt,
        "muestras": len(day_points),
        "ceros": sum(1 for p in day_points if p["value"] == 0),
        "retrocesos_internos": count_internal_negative_steps(day_points),
        "primer_ts": None,
        "ultimo_ts": None,
        "gap_inicio_seg": None,
        "gap_fin_seg": None,
        "raw_first": None,
        "raw_last": None,
        "raw_delta": None,
        "ea_inicio_kwh": None,
        "ea_fin_kwh": None,
        "consumo_kwh": None,
        "estado": None,
        "observacion": None,
    }

    if not day_points:
        base["estado"] = "NO_DATA"
        base["observacion"] = "Clickie no devolvió lecturas dentro del día operacional."
        return base

    first = day_points[0]
    last = day_points[-1]

    base["primer_ts"] = first["datetime"]
    base["ultimo_ts"] = last["datetime"]

    base["gap_inicio_seg"] = max(
        0.0,
        (first["datetime"] - start_dt).total_seconds(),
    )

    base["gap_fin_seg"] = max(
        0.0,
        (end_dt - last["datetime"]).total_seconds(),
    )

    base["raw_first"] = first["value"]
    base["raw_last"] = last["value"]

    base["ea_inicio_kwh"] = first["value"] * equipment["scale"]
    base["ea_fin_kwh"] = last["value"] * equipment["scale"]

    if len(day_points) == 1:
        base["raw_delta"] = 0.0
        base["estado"] = "ONE_EDGE"
        base["observacion"] = "Solo existe una muestra; no es defendible calcular consumo."
        return base

    raw_delta = last["value"] - first["value"]
    scaled_delta = raw_delta * equipment["scale"]

    base["raw_delta"] = raw_delta
    base["consumo_kwh"] = scaled_delta

    # -------------------------------------------------------------------------
    # Clasificación del día.
    # -------------------------------------------------------------------------

    if raw_delta < 0:
        base["estado"] = "NEGATIVE_DELTA"
        base["observacion"] = (
            "Última lectura < primera lectura. Posible reset/discontinuidad del acumulador."
        )
        return base

    if base["retrocesos_internos"] > 0:
        base["estado"] = "INTERNAL_DISCONTINUITY"
        base["observacion"] = (
            "El delta de bordes es positivo, pero existen retrocesos dentro del día."
        )
        return base

    if base["ceros"] > 0:
        base["estado"] = "ZERO_INSIDE_DAY"
        base["observacion"] = (
            "Existen muestras en cero dentro del día. Revisar antes de considerar el acumulador sano."
        )
        return base

    recommended_gap_seconds = MAX_RECOMMENDED_EDGE_GAP_MINUTES * 60

    if (
        base["gap_inicio_seg"] > recommended_gap_seconds
        or base["gap_fin_seg"] > recommended_gap_seconds
    ):
        base["estado"] = "EDGE_GAP_WARNING"
        base["observacion"] = (
            "El consumo se pudo calcular, pero una lectura de borde queda lejos de las 07:00."
        )
        return base

    base["estado"] = "OK"
    base["observacion"] = "Consumo calculado por primera y última lectura válida del día operacional."

    return base


# =============================================================================
# CONSTRUCCIÓN DEL HISTÓRICO DIARIO
# =============================================================================

def build_all_daily_rows(all_series, first_day, last_day):
    """Construye filas diarias para todos los equipos."""

    rows = []

    for equipment in EQUIPMENTS:
        points = all_series.get(equipment["code"], [])

        for day in daterange_inclusive(first_day, last_day):
            rows.append(build_daily_row(equipment, day, points))

    rows.sort(key=lambda r: (r["dia_operacional"], r["codigo"]))

    return rows


# =============================================================================
# EXPORTADORES DE REPORTES
# =============================================================================

DAILY_HEADERS = [
    "equipo",
    "codigo",
    "uuid",
    "escala",
    "estado_escala",
    "tramo",
    "dia_operacional",
    "inicio_objetivo",
    "fin_objetivo",
    "muestras",
    "ceros",
    "retrocesos_internos",
    "primer_ts",
    "ultimo_ts",
    "gap_inicio_min",
    "gap_fin_min",
    "raw_first",
    "raw_last",
    "raw_delta",
    "ea_inicio_kwh",
    "ea_fin_kwh",
    "consumo_kwh",
    "estado",
    "observacion",
]


def daily_row_to_csv(row):
    """Convierte diccionario interno a arreglo CSV."""

    gap_start_min = (
        row["gap_inicio_seg"] / 60.0
        if row["gap_inicio_seg"] is not None
        else ""
    )

    gap_end_min = (
        row["gap_fin_seg"] / 60.0
        if row["gap_fin_seg"] is not None
        else ""
    )

    return [
        row["equipo"],
        row["codigo"],
        row["uuid"],
        row["escala"],
        row["estado_escala"],
        row["tramo"],
        row["dia_operacional"],
        format_datetime(row["inicio_objetivo"]),
        format_datetime(row["fin_objetivo"]),
        row["muestras"],
        row["ceros"],
        row["retrocesos_internos"],
        format_datetime(row["primer_ts"]),
        format_datetime(row["ultimo_ts"]),
        gap_start_min,
        gap_end_min,
        "" if row["raw_first"] is None else row["raw_first"],
        "" if row["raw_last"] is None else row["raw_last"],
        "" if row["raw_delta"] is None else row["raw_delta"],
        "" if row["ea_inicio_kwh"] is None else row["ea_inicio_kwh"],
        "" if row["ea_fin_kwh"] is None else row["ea_fin_kwh"],
        "" if row["consumo_kwh"] is None else row["consumo_kwh"],
        row["estado"],
        row["observacion"],
    ]


def export_daily_rows(file_path, rows):
    """Exporta filas diarias con formato estándar."""

    with file_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(DAILY_HEADERS)

        for row in rows:
            writer.writerow(daily_row_to_csv(row))

    return file_path


def export_configuration():
    """Guarda una fotografía de la configuración utilizada."""

    with CONFIG_FILE.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)

        writer.writerow(
            [
                "equipo",
                "codigo",
                "uuid",
                "escala",
                "estado_escala",
                "motivo",
            ]
        )

        for equipment in EQUIPMENTS:
            writer.writerow(
                [
                    equipment["name"],
                    equipment["code"],
                    equipment["uuid"],
                    equipment["scale"],
                    equipment["scale_status"],
                    equipment["reason"],
                ]
            )

    return CONFIG_FILE


def export_summary(all_series, daily_rows):
    """
    Genera un resumen por equipo para saber rápidamente:

        - cuántas lecturas Clickie se descargaron;
        - cuántos días OK;
        - cuántos días tienen resets/ceros/gaps;
        - rango RAW de totalizador.
    """

    rows_by_code = defaultdict(list)

    for row in daily_rows:
        rows_by_code[row["codigo"]].append(row)

    with SUMMARY_FILE.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)

        writer.writerow(
            [
                "equipo",
                "codigo",
                "uuid",
                "escala",
                "estado_escala",
                "lecturas_raw",
                "primera_lectura",
                "ultima_lectura",
                "raw_min",
                "raw_max",
                "dias_total",
                "dias_ok",
                "dias_no_data",
                "dias_negative_delta",
                "dias_internal_discontinuity",
                "dias_zero_inside",
                "dias_edge_gap",
            ]
        )

        for equipment in EQUIPMENTS:
            points = all_series.get(equipment["code"], [])
            rows = rows_by_code[equipment["code"]]

            status_count = defaultdict(int)

            for row in rows:
                status_count[row["estado"]] += 1

            raw_values = [point["value"] for point in points]

            writer.writerow(
                [
                    equipment["name"],
                    equipment["code"],
                    equipment["uuid"],
                    equipment["scale"],
                    equipment["scale_status"],
                    len(points),
                    format_datetime(points[0]["datetime"]) if points else "",
                    format_datetime(points[-1]["datetime"]) if points else "",
                    min(raw_values) if raw_values else "",
                    max(raw_values) if raw_values else "",
                    len(rows),
                    status_count["OK"],
                    status_count["NO_DATA"],
                    status_count["NEGATIVE_DELTA"],
                    status_count["INTERNAL_DISCONTINUITY"],
                    status_count["ZERO_INSIDE_DAY"],
                    status_count["EDGE_GAP_WARNING"],
                ]
            )

    return SUMMARY_FILE


# =============================================================================
# QUERY DE EXPORTACIÓN gnrMain
# =============================================================================

def generate_gnrmain_query(first_day, last_day):
    """
    Genera un SELECT listo para ejecutar en gnrProDb01.

    El usuario puede exportar el resultado como:

        reportes/gnrMain_Auditoria.csv

    Luego, al volver a ejecutar este script, se generará automáticamente la
    comparación Clickie vs gnrMain.
    """

    codes_sql = ",\n        ".join(
        f"'{equipment['code']}'"
        for equipment in EQUIPMENTS
    )

    end_exclusive = last_day + timedelta(days=1)

    sql = f'''-- =============================================================================
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
        {codes_sql}
)
AND "dateIn" >= TIMESTAMP '{first_day.isoformat()} 00:00:00'
AND "dateIn" <  TIMESTAMP '{end_exclusive.isoformat()} 00:00:00'
ORDER BY
    "dateIn",
    "nameTag",
    id;
'''

    GNRMAIN_QUERY_FILE.write_text(sql, encoding="utf-8")

    return GNRMAIN_QUERY_FILE


# =============================================================================
# LECTURA DEL CSV gnrMain (OPCIONAL)
# =============================================================================

def open_csv_dicts(file_path):
    """
    Abre un CSV detectando delimitador de forma defensiva.

    Devuelve lista de diccionarios.
    """

    text = file_path.read_text(encoding="utf-8-sig")

    sample = text[:4096]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    reader = csv.DictReader(text.splitlines(), delimiter=delimiter)

    return list(reader)


def find_field(row, *candidates):
    """Busca un campo ignorando mayúsculas/minúsculas."""

    normalized = {
        str(key).strip().lower(): value
        for key, value in row.items()
        if key is not None
    }

    for candidate in candidates:
        key = candidate.lower()

        if key in normalized:
            return normalized[key]

    return None


def parse_float(value):
    """Convierte texto numérico a float o None."""

    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    # PostgreSQL/pgAdmin normalmente exporta decimal con punto.
    # Si aparece una coma decimal simple y no hay punto, intentamos adaptarla.
    if "," in text and "." not in text:
        text = text.replace(",", ".")

    try:
        number = float(text)
    except ValueError:
        return None

    if not math.isfinite(number):
        return None

    return number


def parse_date_any(value):
    """Extrae YYYY-MM-DD desde dateIn exportado por pgAdmin."""

    if value is None:
        return None

    text = str(value).strip()

    if len(text) < 10:
        return None

    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def read_gnrmain_export(file_path):
    """
    Indexa gnrMain por:

        (codigo, dateIn::date)

    porque esa combinación es la que ya venimos usando como identidad del día
    operacional procesado.
    """

    rows = open_csv_dicts(file_path)

    index = defaultdict(list)

    for row in rows:
        code = find_field(row, "codigo", "nameTag")
        date_in = find_field(row, "dateIn", "datein")

        day = parse_date_any(date_in)

        if not code or day is None:
            continue

        index[(str(code).strip(), day)].append(
            {
                "id": find_field(row, "id"),
                "equipo": find_field(row, "equipo", "nameMtr"),
                "codigo": str(code).strip(),
                "value": parse_float(find_field(row, "value")),
                "accumulated": parse_float(find_field(row, "accumulated")),
                "date": find_field(row, "date"),
                "dateIn": date_in,
                "path": find_field(row, "path"),
                "category": find_field(row, "category"),
            }
        )

    return index


# =============================================================================
# COMPARACIÓN CLICKIE VS gnrMain
# =============================================================================

def value_is_close(reference, candidate):
    """
    Determina si dos consumos son suficientemente cercanos.

    tolerancia = máximo entre:

        5 kWh
        2 % de Clickie
    """

    if reference is None or candidate is None:
        return False

    tolerance = max(
        COMPARE_ABS_TOLERANCE_KWH,
        abs(reference) * COMPARE_REL_TOLERANCE,
    )

    return abs(candidate - reference) <= tolerance


def detect_scale_factor(reference, gnr_value):
    """
    Busca si gnrMain parece estar correcto salvo por una escala típica.

    Ejemplo:

        Clickie = 8400 kWh
        gnrMain  = 8.4

        factor = 1000

    Devuelve el factor que habría que multiplicar a gnrMain para aproximarse a
    Clickie, o None si no encuentra un candidato claro.
    """

    if reference is None or gnr_value is None:
        return None

    for factor in SCALE_FACTORS_TO_TEST:
        adjusted = gnr_value * factor

        if value_is_close(reference, adjusted):
            return factor

    return None


def compare_with_gnrmain(daily_rows, gnr_index):
    """Cruza resultados diarios Clickie contra export de gnrMain."""

    comparison_rows = []
    correction_rows = []

    valid_clickie_statuses = {
        "OK",
        "EDGE_GAP_WARNING",
    }

    for clickie in daily_rows:
        day = date.fromisoformat(clickie["dia_operacional"])
        key = (clickie["codigo"], day)

        gnr_rows = gnr_index.get(key, [])

        clickie_value = clickie["consumo_kwh"]
        clickie_valid = (
            clickie_value is not None
            and clickie["estado"] in valid_clickie_statuses
        )

        if not gnr_rows:
            status = "SIN_GNRMAIN"
            gnr = None

        elif len(gnr_rows) > 1:
            status = "DUPLICADO_GNRMAIN"
            gnr = gnr_rows[0]

        else:
            gnr = gnr_rows[0]

            if not clickie_valid:
                status = "CLICKIE_NO_VALIDO"

            elif gnr["value"] is None:
                status = "GNRMAIN_VALUE_NULO"

            elif value_is_close(clickie_value, gnr["value"]):
                status = "OK"

            else:
                factor = detect_scale_factor(clickie_value, gnr["value"])

                if factor is not None:
                    status = f"ESCALA_GNR_X{factor:g}"
                else:
                    status = "DIFERENCIA_REAL"

        gnr_value = gnr["value"] if gnr else None
        gnr_accumulated = gnr["accumulated"] if gnr else None

        difference = (
            gnr_value - clickie_value
            if gnr_value is not None and clickie_value is not None
            else None
        )

        ratio = (
            gnr_value / clickie_value
            if (
                gnr_value is not None
                and clickie_value not in (None, 0)
            )
            else None
        )

        comparison = {
            "dia_operacional": clickie["dia_operacional"],
            "equipo": clickie["equipo"],
            "codigo": clickie["codigo"],
            "uuid": clickie["uuid"],
            "escala_clickie": clickie["escala"],
            "estado_clickie": clickie["estado"],
            "clickie_kwh": clickie_value,
            "clickie_ea_fin_kwh": clickie["ea_fin_kwh"],
            "gnr_id": gnr["id"] if gnr else None,
            "gnr_value": gnr_value,
            "gnr_accumulated": gnr_accumulated,
            "diferencia_gnr_menos_clickie": difference,
            "ratio_gnr_sobre_clickie": ratio,
            "cantidad_gnr": len(gnr_rows),
            "diagnostico": status,
        }

        comparison_rows.append(comparison)

        # ---------------------------------------------------------------------
        # Corrección candidata.
        # ---------------------------------------------------------------------
        # NO se ejecuta nada.
        # Solo se propone cuando:
        #
        #     - Clickie es defendible;
        #     - existe exactamente una fila gnrMain;
        #     - no coincide ya con Clickie.
        # ---------------------------------------------------------------------

        if (
            clickie_valid
            and len(gnr_rows) == 1
            and status != "OK"
        ):
            correction_rows.append(
                {
                    **comparison,
                    "valor_propuesto": clickie_value,
                    "acumulado_propuesto": clickie["ea_fin_kwh"],
                }
            )

    return comparison_rows, correction_rows


def export_comparison(rows):
    """Exporta comparación Clickie vs gnrMain."""

    headers = [
        "dia_operacional",
        "equipo",
        "codigo",
        "uuid",
        "escala_clickie",
        "estado_clickie",
        "clickie_kwh",
        "clickie_ea_fin_kwh",
        "gnr_id",
        "gnr_value",
        "gnr_accumulated",
        "diferencia_gnr_menos_clickie",
        "ratio_gnr_sobre_clickie",
        "cantidad_gnr",
        "diagnostico",
    ]

    with COMPARISON_FILE.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers)
        writer.writeheader()

        for row in rows:
            writer.writerow(row)

    return COMPARISON_FILE


def export_corrections(rows):
    """
    Exporta CANDIDATOS a corrección.

    Este archivo no es SQL y no modifica nada.
    """

    headers = [
        "dia_operacional",
        "equipo",
        "codigo",
        "gnr_id",
        "diagnostico",
        "gnr_value",
        "clickie_kwh",
        "valor_propuesto",
        "gnr_accumulated",
        "clickie_ea_fin_kwh",
        "acumulado_propuesto",
        "diferencia_gnr_menos_clickie",
    ]

    with CORRECTIONS_FILE.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()

        for row in rows:
            writer.writerow(row)

    return CORRECTIONS_FILE


# =============================================================================
# SALIDA DE CONSOLA
# =============================================================================

def print_critical_period(rows):
    """Muestra el tramo crítico de forma compacta."""

    print()
    print("=" * 100)
    print("PERÍODO CRÍTICO - RESUMEN CLICKIE")
    print("=" * 100)

    critical_rows = [
        row
        for row in rows
        if CRITICAL_PERIOD_START
        <= date.fromisoformat(row["dia_operacional"])
        <= CRITICAL_PERIOD_END
    ]

    for row in critical_rows:
        consumption = row["consumo_kwh"]

        consumption_text = (
            "N/D"
            if consumption is None
            else f"{consumption:,.3f} kWh"
        )

        print(
            f"{row['dia_operacional']} | "
            f"{row['codigo']:<12} | "
            f"{consumption_text:>18} | "
            f"{row['estado']:<25} | "
            f"escala={row['escala']}"
        )


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Flujo principal de la auditoría."""

    print()
    print("=" * 100)
    print("AUDITORÍA CLICKIE MULTI-MEDIDOR / RASPBERRY -> IGNITION")
    print("=" * 100)

    if not CLICKIE_API_KEY:
        raise RuntimeError(
            "Falta CLICKIE_API_KEY en .env. "
            "El proceso se detiene antes de hacer cualquier consulta."
        )

    last_day = last_closed_operational_day()

    if last_day < FIRST_OPERATIONAL_DAY:
        raise RuntimeError("El rango calculado es inválido.")

    global_start = operational_start(FIRST_OPERATIONAL_DAY)
    global_end = operational_start(last_day + timedelta(days=1))

    print(f"Primer día operacional : {FIRST_OPERATIONAL_DAY}")
    print(f"Último día cerrado     : {last_day}")
    print(f"Frontera post-cambio   : {POST_CHANGE_START_DAY}")
    print(f"Equipos configurados   : {len(EQUIPMENTS)}")

    # -------------------------------------------------------------------------
    # 1. Exportar configuración utilizada.
    # -------------------------------------------------------------------------

    export_configuration()

    # -------------------------------------------------------------------------
    # 2. Descargar Clickie para todos los equipos.
    # -------------------------------------------------------------------------

    all_series = {}

    for equipment in EQUIPMENTS:
        points = fetch_equipment_series(
            equipment,
            global_start,
            global_end,
        )

        all_series[equipment["code"]] = points

        raw_file = export_raw_equipment_csv(equipment, points)
        print(f"Raw CSV        : {raw_file}")

    # -------------------------------------------------------------------------
    # 3. Construir todos los días 07:00 -> 07:00.
    # -------------------------------------------------------------------------

    daily_rows = build_all_daily_rows(
        all_series,
        FIRST_OPERATIONAL_DAY,
        last_day,
    )

    # -------------------------------------------------------------------------
    # 4. Reporte maestro.
    # -------------------------------------------------------------------------

    export_daily_rows(MASTER_REPORT_FILE, daily_rows)

    # -------------------------------------------------------------------------
    # 5. Reporte post-cambio.
    # -------------------------------------------------------------------------

    post_rows = [
        row
        for row in daily_rows
        if date.fromisoformat(row["dia_operacional"]) >= POST_CHANGE_START_DAY
    ]

    export_daily_rows(POST_CHANGE_FILE, post_rows)

    # -------------------------------------------------------------------------
    # 6. Reporte del período crítico.
    # -------------------------------------------------------------------------

    critical_rows = [
        row
        for row in daily_rows
        if CRITICAL_PERIOD_START
        <= date.fromisoformat(row["dia_operacional"])
        <= CRITICAL_PERIOD_END
    ]

    export_daily_rows(CRITICAL_PERIOD_FILE, critical_rows)

    # -------------------------------------------------------------------------
    # 7. Resumen por medidor.
    # -------------------------------------------------------------------------

    export_summary(all_series, daily_rows)

    # -------------------------------------------------------------------------
    # 8. Generar SELECT para gnrMain.
    # -------------------------------------------------------------------------

    generate_gnrmain_query(
        FIRST_OPERATIONAL_DAY,
        last_day,
    )

    # -------------------------------------------------------------------------
    # 9. Si ya existe el CSV de gnrMain, compararlo automáticamente.
    # -------------------------------------------------------------------------

    comparison_generated = False

    if GNRMAIN_EXPORT_EXPECTED_FILE.exists():
        print()
        print("=" * 100)
        print("SE ENCONTRÓ gnrMain_Auditoria.csv -> INICIANDO COMPARACIÓN")
        print("=" * 100)

        gnr_index = read_gnrmain_export(
            GNRMAIN_EXPORT_EXPECTED_FILE
        )

        comparison_rows, correction_rows = compare_with_gnrmain(
            daily_rows,
            gnr_index,
        )

        export_comparison(comparison_rows)
        export_corrections(correction_rows)

        comparison_generated = True

        diagnostics = defaultdict(int)

        for row in comparison_rows:
            diagnostics[row["diagnostico"]] += 1

        print("Diagnósticos:")

        for key in sorted(diagnostics):
            print(f"  {key:<30}: {diagnostics[key]}")

        print(f"Candidatos corrección: {len(correction_rows)}")

    # -------------------------------------------------------------------------
    # 10. Mostrar tramo crítico por consola.
    # -------------------------------------------------------------------------

    print_critical_period(daily_rows)

    # -------------------------------------------------------------------------
    # 11. Resumen final.
    # -------------------------------------------------------------------------

    print()
    print("=" * 100)
    print("ARCHIVOS GENERADOS")
    print("=" * 100)
    print(f"Maestro Clickie       : {MASTER_REPORT_FILE}")
    print(f"Post cambio           : {POST_CHANGE_FILE}")
    print(f"Período crítico       : {CRITICAL_PERIOD_FILE}")
    print(f"Resumen equipos       : {SUMMARY_FILE}")
    print(f"Configuración         : {CONFIG_FILE}")
    print(f"Query gnrMain         : {GNRMAIN_QUERY_FILE}")
    print(f"Raw por medidor       : {RAW_DIR}")

    if comparison_generated:
        print(f"Comparación           : {COMPARISON_FILE}")
        print(f"Correcciones candid.  : {CORRECTIONS_FILE}")
    else:
        print()
        print("Comparación gnrMain aún NO generada.")
        print("Ejecuta el SELECT generado en gnrProDb01, exporta el resultado como:")
        print(f"  {GNRMAIN_EXPORT_EXPECTED_FILE}")
        print("y vuelve a ejecutar este mismo script.")

    print()
    print("=" * 100)
    print("POSTGRESQL NO FUE MODIFICADO")
    print("=" * 100)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
