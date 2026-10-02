import os
import warnings
from datetime import timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


warnings.filterwarnings("ignore", category=UserWarning)

PROJECT_DIR = Path(__file__).resolve().parent.parent


# ============================================================
# BASE DE DATOS
# ============================================================

DB_CONFIG = {
    "host": os.getenv("TELEMETRIA_DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("TELEMETRIA_DB_PORT", "3306")),
    "user": os.getenv("TELEMETRIA_DB_USER", "root"),
    "password": os.getenv(
        "TELEMETRIA_DB_PASSWORD",
        "Password123",
    ),
    "database": os.getenv(
        "TELEMETRIA_DB_NAME",
        "telemetria",
    ),
}


# ============================================================
# ZONA HORARIA / DÍA OPERATIVO
# ============================================================

TZ_CHILE = ZoneInfo("America/Santiago")

OPERATIONAL_DAY_START_HOUR = 7

REGLA_DIA_OPERATIVO = "07:00-07:00"


# ============================================================
# VARIABLES GENERALES
# ============================================================

VARIABLE_AGUA = "Totalizado_Pozo"


# ============================================================
# HISTÓRICO MAPA AGUA
# ============================================================

# Cantidad de meses cerrados que se recalculan junto
# con el mes actual.
#
# Con 3:
#   - mes actual
#   - mes anterior
#   - dos meses anteriores
#   - tres meses anteriores
#
# Las hojas históricas anteriores se conservan.
MESES_HISTORICOS = max(
    1,
    int(
        os.getenv(
            "TELEMETRIA_MESES_HISTORICOS",
            "3",
        )
    ),
)


# ============================================================
# SALIDAS
# ============================================================

OUTPUT_DIR = Path(
    os.getenv(
        "TELEMETRIA_OUTPUT_DIR",
        str(PROJECT_DIR),
    )
)

DEFAULT_OUTPUT_XLSX = (
    OUTPUT_DIR / "MapaAgua.xlsx"
)

DEFAULT_OUTPUT_RESUMEN_DIARIO_XLSX = (
    OUTPUT_DIR / "Resumen_Diario.xlsx"
)


# ============================================================
# REPORTE DGA - POZO
# ============================================================

# ------------------------------------------------------------
# Totalizador
# ------------------------------------------------------------

DGA_TOTALIZADOR_VAR = VARIABLE_AGUA


# ------------------------------------------------------------
# Nivel freático
# ------------------------------------------------------------

# Variable real almacenada en:
#
#   mediciones.variable = "Nivel_Pozo"
#
# Puede sobrescribirse mediante variable de entorno.
DGA_NIVEL_FREATICO_VAR = (
    os.getenv(
        "TELEMETRIA_DGA_NIVEL_VAR",
        "Nivel_Pozo",
    ).strip()
    or None
)


# ------------------------------------------------------------
# Flujo instantáneo
# ------------------------------------------------------------

# Variable real almacenada en:
#
#   mediciones.variable = "Flujo_Instantaneo"
#
# Se mantiene sin unidad explícita hasta confirmar
# la unidad real entregada por el instrumento.
DGA_FLUJO_INSTANTANEO_VAR = (
    os.getenv(
        "TELEMETRIA_DGA_FLUJO_VAR",
        "Flujo_Instantaneo",
    ).strip()
    or None
)


# ------------------------------------------------------------
# Hora DGA
# ------------------------------------------------------------

# Hora oficial de medición.
DGA_HORA_DEFAULT = int(
    os.getenv(
        "TELEMETRIA_DGA_HORA",
        "7",
    )
)


# ------------------------------------------------------------
# Zona horaria DGA
# ------------------------------------------------------------

# Se utiliza UTC-4 fijo para el reporte DGA.
TZ_DGA = timezone(
    timedelta(hours=-4)
)


# ============================================================
# VENTANA DE BÚSQUEDA DGA
# ============================================================

# Si no existe una muestra exactamente a las 07:00,
# se busca la PRIMERA lectura disponible hasta las 11:00.
#
# Independientemente de la hora real encontrada,
# el archivo oficial continúa informando 07:00.
DGA_HORA_LIMITE_BUSQUEDA = int(
    os.getenv(
        "TELEMETRIA_DGA_HORA_LIMITE",
        "11",
    )
)


# ============================================================
# ARCHIVO DGA
# ============================================================

DEFAULT_OUTPUT_DGA_XLSX = (
    OUTPUT_DIR / "DGA_Pozo.xlsx"
)


COLUMNAS_DGA = [
    "Fecha Medición",
    "Hora Medición",
    "Caudal (l/s)",
    "Totalizador (m3)",
    "Nivel Freático (m)",
    "Flujo Instantáneo",
]


# ============================================================
# MAPA AGUA
# ============================================================

SHEET_RESUMEN_AGUA = "Agua_Resumen"

SHEET_TENDENCIA_AGUA = "Agua_Tendencia"

SHEET_INDICE_MESES = "Indice_Meses"

SHEET_RESUMEN_DIARIO = "Resumen_Diario"


COLUMNAS_RESUMEN_DIARIO = [
    "fecha_operacional",
    "variable",
    "consumo",
    "valor_inicial",
    "valor_final",
]


COLUMNAS_REPORTE_AGUA = [
    "fecha_actualizacion",
    "origen",
    "regla_dia_operativo",
    "bloque",
    "periodo",
    "agua_m3",
    "variable",
    "valor_inicial",
    "valor_final",
    "registros",
    "desde",
    "hasta",
]


COLUMNAS_TENDENCIA_AGUA = [
    "fecha_actualizacion",
    "origen",
    "regla_dia_operativo",
    "vista",
    "bloque",
    "periodo",
    "orden",
    "agua_m3",
    "production_tons",
    "kpi_m3_ton",
    "variable",
    "valor_inicial",
    "valor_final",
    "registros",
    "desde",
    "hasta",
]


# ============================================================
# NOMBRES DE MESES / DÍAS
# ============================================================

MESES_ES = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


DIAS_ES = {
    0: "Lun",
    1: "Mar",
    2: "Mié",
    3: "Jue",
    4: "Vie",
    5: "Sáb",
    6: "Dom",
}


MESES_ES_COMPLETOS = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}