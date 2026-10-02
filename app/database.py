from datetime import datetime

import mysql.connector
import pandas as pd

from .config import DB_CONFIG, DGA_NIVEL_FREATICO_VAR, VARIABLE_AGUA
from .time_ranges import validar_rango_fecha_hora


# ============================================================
# VARIABLES ALMACENADAS EN LA TABLA "mediciones"
# ============================================================

VARIABLES_MEDICIONES = {
    "Totalizado_Pozo",
    "Flujo_Instantaneo",
    "Nivel_Pozo",
}

# Mantener compatibilidad con las variables configuradas
# anteriormente en config.py.
if VARIABLE_AGUA:
    VARIABLES_MEDICIONES.add(VARIABLE_AGUA)

if DGA_NIVEL_FREATICO_VAR:
    VARIABLES_MEDICIONES.add(DGA_NIVEL_FREATICO_VAR)


# ============================================================
# CONEXIÓN
# ============================================================

def get_connection():
    """Crea una conexión nueva a MySQL."""
    return mysql.connector.connect(**DB_CONFIG)


# ============================================================
# RESOLUCIÓN DE ORIGEN
# ============================================================

def resolver_origen_dato(nombre_variable: str) -> dict:
    """
    Define la tabla y las columnas según la variable seleccionada.

    Variables de agua / pozo:
        - Totalizado_Pozo
        - Flujo_Instantaneo
        - Nivel_Pozo

    se almacenan en:
        tabla: mediciones
        variable: variable
        valor: value

    Los medidores eléctricos se almacenan en:
        tabla: energia
        variable: equipo
        valor: kWh
    """

    if nombre_variable in VARIABLES_MEDICIONES:
        return {
            "tabla": "mediciones",
            "campo_nombre": "variable",
            "campo_valor": "value",
        }

    return {
        "tabla": "energia",
        "campo_nombre": "equipo",
        "campo_valor": "kWh",
    }


# ============================================================
# LISTADO DE VARIABLES
# ============================================================

def obtener_variables() -> list[str]:
    """
    Carga todas las variables disponibles desde las tablas
    mediciones y energia.
    """

    query = """
    SELECT nombre
    FROM (
        SELECT DISTINCT variable AS nombre
        FROM mediciones

        UNION

        SELECT DISTINCT equipo AS nombre
        FROM energia
    ) t
    WHERE nombre IS NOT NULL
    ORDER BY nombre;
    """

    conn = get_connection()

    try:
        df = pd.read_sql(query, conn)

        return (
            df["nombre"]
            .dropna()
            .astype(str)
            .tolist()
        )

    finally:
        conn.close()


# ============================================================
# CONSULTA INTERNA POR RANGO
# ============================================================

def _consultar_rango(
    nombre_variable: str,
    inicio_dt: datetime,
    fin_dt: datetime,
    *,
    fin_exclusivo: bool,
) -> pd.DataFrame:
    """
    Consulta datos crudos según la variable y rango temporal.

    Detecta automáticamente si la variable pertenece a:
        - mediciones
        - energia
    """

    if inicio_dt >= fin_dt:
        return pd.DataFrame(
            columns=["timestamp", "valor"]
        )

    origen = resolver_origen_dato(nombre_variable)

    tabla = origen["tabla"]
    campo_nombre = origen["campo_nombre"]
    campo_valor = origen["campo_valor"]

    ts_inicio = int(inicio_dt.timestamp())
    ts_fin = int(fin_dt.timestamp())

    if fin_exclusivo:
        condicion_rango = (
            "`timestamp` >= %s "
            "AND `timestamp` < %s"
        )
    else:
        condicion_rango = (
            "`timestamp` BETWEEN %s AND %s"
        )

    query = f"""
    SELECT
        `timestamp`,
        {campo_valor} AS valor
    FROM {tabla}
    WHERE {campo_nombre} = %s
      AND {condicion_rango}
    ORDER BY `timestamp`;
    """

    conn = get_connection()
    cursor = None

    try:
        cursor = conn.cursor()

        cursor.execute(
            query,
            (
                nombre_variable,
                ts_inicio,
                ts_fin,
            ),
        )

        rows = cursor.fetchall()

        if not rows:
            return pd.DataFrame(
                columns=["timestamp", "valor"]
            )

        df = pd.DataFrame(
            rows,
            columns=["timestamp", "valor"],
        )

        # Asegurar tipo numérico para cálculos posteriores
        df["timestamp"] = pd.to_numeric(
            df["timestamp"],
            errors="coerce",
        )

        df["valor"] = pd.to_numeric(
            df["valor"],
            errors="coerce",
        )

        # Eliminar registros inválidos
        df = df.dropna(
            subset=["timestamp", "valor"]
        )

        return df.reset_index(drop=True)

    finally:
        if cursor is not None:
            cursor.close()

        conn.close()


# ============================================================
# CONSULTA DIAGNÓSTICA
# ============================================================

def obtener_datos_por_rango(
    nombre_variable: str,
    inicio_dt: datetime,
    fin_dt: datetime,
) -> pd.DataFrame:
    """
    Consulta diagnóstica.

    Utiliza límite final inclusivo:
        inicio <= timestamp <= fin
    """

    return _consultar_rango(
        nombre_variable,
        inicio_dt,
        fin_dt,
        fin_exclusivo=False,
    )


# ============================================================
# CONSULTA OPERACIONAL
# ============================================================

def obtener_datos_por_rango_exclusivo(
    nombre_variable: str,
    inicio_dt: datetime,
    fin_dt: datetime,
) -> pd.DataFrame:
    """
    Consulta operacional.

    Utiliza intervalo:
        [inicio, fin)

    Es decir:
        inicio <= timestamp < fin
    """

    return _consultar_rango(
        nombre_variable,
        inicio_dt,
        fin_dt,
        fin_exclusivo=True,
    )


# ============================================================
# INTERFAZ COMPATIBLE CON LA APLICACIÓN
# ============================================================

def obtener_datos(
    nombre_variable: str,
    fecha_inicio: str,
    fecha_fin: str,
    hora_inicio: str = "00:00",
    hora_fin: str = "23:59",
) -> pd.DataFrame:
    """
    Convierte fecha y hora local de Chile y consulta los datos crudos.

    Los valores por defecto mantienen compatibilidad con llamadas
    antiguas que solamente entregaban fechas.
    """

    inicio_dt, fin_dt = validar_rango_fecha_hora(
        fecha_inicio,
        hora_inicio,
        fecha_fin,
        hora_fin,
    )

    return obtener_datos_por_rango(
        nombre_variable,
        inicio_dt,
        fin_dt,
    )