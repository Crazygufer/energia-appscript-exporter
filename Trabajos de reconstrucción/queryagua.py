import mysql.connector
import pandas as pd

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


# ============================================================
# 1. CONFIGURACIÓN
# ============================================================

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Password123",
    "database": "telemetria"
}

# Variable histórica que queremos consultar
VARIABLE = "Totalizado_Pozo"

# Desde cuándo intentar reconstruir el histórico
FECHA_INICIO = "2026-03-01"

# Día operacional:
# 07:00 de un día -> 07:00 del día siguiente
HORA_CORTE = 7

TIMEZONE = "America/Santiago"

# Información fija para conservar el formato requerido
NOMBRE_VISIBLE = "Agua Pozo"
AREA = "Inyección"

# Buscar hasta 4 horas antes o después de las 07:00.
# IMPORTANTE:
# Dentro de esa ventana siempre se toma el registro MÁS CERCANO.
TOLERANCIA_MINUTOS = 240

ARCHIVO_SALIDA = "Historico_Agua_Ignition.xlsx"


# ============================================================
# 2. FUNCIONES AUXILIARES
# ============================================================

def clasificar_offset(minutos):
    """
    Clasificación únicamente para diagnóstico por consola.
    No se exporta al Excel.
    """

    minutos = abs(minutos)

    if minutos <= 15:
        return "EXCELENTE"
    elif minutos <= 60:
        return "BUENO"
    elif minutos <= 120:
        return "ACEPTABLE"
    elif minutos <= 240:
        return "LEJANO"
    else:
        return "FUERA_RANGO"


def formatear_offset(minutos):
    """
    Convierte minutos en texto más legible.
    Ejemplo:
        +73 min -> +1h 13m
        -125 min -> -2h 05m
    """

    signo = "+" if minutos >= 0 else "-"

    minutos_abs = abs(int(round(minutos)))

    horas = minutos_abs // 60
    minutos_restantes = minutos_abs % 60

    if horas == 0:
        return f"{signo}{minutos_restantes} min"

    return f"{signo}{horas}h {minutos_restantes:02d}m"


# ============================================================
# 3. DEFINIR RANGO TEMPORAL
# ============================================================

tz = ZoneInfo(TIMEZONE)

ahora = datetime.now(tz)

inicio = datetime.strptime(
    FECHA_INICIO,
    "%Y-%m-%d"
).replace(
    hour=HORA_CORTE,
    minute=0,
    second=0,
    microsecond=0,
    tzinfo=tz
)

# Corte de las 07:00 de hoy
ultimo_corte = ahora.replace(
    hour=HORA_CORTE,
    minute=0,
    second=0,
    microsecond=0
)

# Si todavía no son las 07:00, el último corte válido fue ayer
if ahora < ultimo_corte:
    ultimo_corte -= timedelta(days=1)


print()
print("========================================")
print("EXTRACCIÓN HISTÓRICA DE AGUA")
print("========================================")
print(f"Variable            : {VARIABLE}")
print(f"Desde               : {inicio}")
print(f"Hasta               : {ultimo_corte}")
print(f"Hora operacional    : {HORA_CORTE:02d}:00")
print(
    f"Tolerancia          : "
    f"±{TOLERANCIA_MINUTOS // 60} horas"
)
print()


# ============================================================
# 4. RANGO SQL
# ============================================================

# Agregamos la tolerancia al inicio y al final porque
# necesitamos registros que puedan estar antes/después
# del corte de las 07:00.

inicio_query = (
    inicio - timedelta(minutes=TOLERANCIA_MINUTOS)
)

fin_query = (
    ultimo_corte + timedelta(minutes=TOLERANCIA_MINUTOS)
)

timestamp_inicio = int(inicio_query.timestamp())
timestamp_fin = int(fin_query.timestamp())


# ============================================================
# 5. CONECTAR A MYSQL
# ============================================================

print("Conectando a MySQL...")

try:

    conexion = mysql.connector.connect(
        **DB_CONFIG
    )

except mysql.connector.Error as error:

    print()
    print("ERROR AL CONECTAR A MYSQL")
    print(error)

    raise


print("Conexión OK.")
print()


# ============================================================
# 6. CONSULTA SQL
# ============================================================

query = """
SELECT
    `timestamp`,
    `value`
FROM mediciones
WHERE variable = %s
  AND `timestamp` >= %s
  AND `timestamp` <= %s
ORDER BY `timestamp` ASC
"""


cursor = conexion.cursor()

cursor.execute(
    query,
    (
        VARIABLE,
        timestamp_inicio,
        timestamp_fin
    )
)

filas = cursor.fetchall()

cursor.close()
conexion.close()


# ============================================================
# 7. CREAR DATAFRAME
# ============================================================

df = pd.DataFrame(
    filas,
    columns=[
        "timestamp",
        "value"
    ]
)


print(f"Registros encontrados en BD: {len(df):,}")


if df.empty:

    print()
    print("No se encontraron datos.")
    print("Revisa:")
    print("- nombre de variable")
    print("- rango de fechas")
    print("- contenido de la tabla mediciones")

    raise SystemExit


# ============================================================
# 8. CONVERTIR EPOCH A FECHA LOCAL
# ============================================================

df["fecha"] = (
    pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True
    )
    .dt.tz_convert(TIMEZONE)
)

# Aseguramos value numérico
df["value"] = pd.to_numeric(
    df["value"],
    errors="coerce"
)

# Eliminar valores inválidos
df = df.dropna(
    subset=["value", "fecha"]
)

df = df.sort_values(
    "fecha"
).reset_index(drop=True)

df = df.set_index("fecha")


print(
    f"Primer registro BD : {df.index.min()}"
)

print(
    f"Último registro BD : {df.index.max()}"
)

print()


# ============================================================
# 9. BUSCAR EL REGISTRO MÁS CERCANO A LAS 07:00
# ============================================================

def obtener_valor_cercano(fecha_objetivo):
    """
    Busca el registro cuya hora real esté más cerca del
    corte operacional solicitado.

    Puede buscar tanto hacia atrás como hacia adelante.

    Ejemplo:

       06:31       07:00       08:15
         |-----------|------------|
         29 min                   75 min

    En este caso selecciona 06:31.
    """

    objetivo = pd.Timestamp(fecha_objetivo)

    diferencias = abs(
        df.index - objetivo
    )

    if len(diferencias) == 0:
        return None

    posicion = diferencias.argmin()

    diferencia_minutos = (
        diferencias[posicion].total_seconds()
        / 60
    )

    # Si ni siquiera el registro más cercano está
    # dentro de ±4 horas, descartamos ese corte.
    if diferencia_minutos > TOLERANCIA_MINUTOS:
        return None

    fila = df.iloc[posicion]

    fecha_real = df.index[posicion]

    # Diferencia firmada:
    #
    # negativo -> antes de las 07:00
    # positivo -> después de las 07:00

    offset_minutos = (
        (fecha_real - objetivo)
        .total_seconds()
        / 60
    )

    return {
        "valor": float(fila["value"]),
        "fecha_real": fecha_real,
        "offset_minutos": offset_minutos
    }


# ============================================================
# 10. RECORRER DÍAS OPERACIONALES
# ============================================================

resultado = []

dias_totales = 0
dias_exportados = 0
dias_sin_datos = 0
dias_negativos = 0

desde = inicio


print("Procesando días...")
print()


while desde < ultimo_corte:

    dias_totales += 1

    hasta = desde + timedelta(days=1)

    lectura_inicial = obtener_valor_cercano(
        desde
    )

    lectura_final = obtener_valor_cercano(
        hasta
    )


    # ========================================================
    # FALTA ALGUNO DE LOS DOS BORDES
    # ========================================================

    if (
        lectura_inicial is None
        or lectura_final is None
    ):

        dias_sin_datos += 1

        print(
            f"SKIP | {desde.date()} | "
            f"Sin borde válido dentro de "
            f"±{TOLERANCIA_MINUTOS // 60} h"
        )

        desde = hasta

        continue


    # ========================================================
    # VALORES
    # ========================================================

    valor_inicial = lectura_inicial["valor"]

    valor_final = lectura_final["valor"]

    agua_m3 = (
        valor_final
        - valor_inicial
    )


    # ========================================================
    # OFFSET DE CADA BORDE
    # ========================================================

    offset_inicio = (
        lectura_inicial["offset_minutos"]
    )

    offset_fin = (
        lectura_final["offset_minutos"]
    )

    estado_inicio = clasificar_offset(
        offset_inicio
    )

    estado_fin = clasificar_offset(
        offset_fin
    )


    # ========================================================
    # VALIDAR CONSUMO NEGATIVO
    # ========================================================

    if agua_m3 < 0:

        dias_negativos += 1

        estado_consumo = "NEGATIVO"

    else:

        estado_consumo = "OK"


    # ========================================================
    # MOSTRAR DIAGNÓSTICO
    # ========================================================

    print(
        f"{estado_consumo:8} | "
        f"{desde.date()} | "
        f"{agua_m3:8.2f} m3 | "
        f"INI {lectura_inicial['fecha_real'].strftime('%H:%M:%S')} "
        f"{formatear_offset(offset_inicio):>9} "
        f"[{estado_inicio}] | "
        f"FIN {lectura_final['fecha_real'].strftime('%H:%M:%S')} "
        f"{formatear_offset(offset_fin):>9} "
        f"[{estado_fin}]"
    )


    # ========================================================
    # CREAR FILA CON ESTRUCTURA DEL EXCEL
    # ========================================================

    resultado.append({

        "nombre_visible":
            NOMBRE_VISIBLE,

        "area":
            AREA,

        "agua_m3":
            agua_m3,

        "valor_inicial":
            valor_inicial,

        "valor_final":
            valor_final,

        # IMPORTANTE:
        # Aquí dejamos 07:00 nominal,
        # no la hora real encontrada.
        #
        # De esta manera el histórico entregado
        # mantiene un día operacional consistente.

        "desde":
            desde.replace(tzinfo=None),

        "hasta":
            hasta.replace(tzinfo=None)

    })


    dias_exportados += 1

    desde = hasta


# ============================================================
# 11. CREAR DATAFRAME FINAL
# ============================================================

columnas = [
    "nombre_visible",
    "area",
    "agua_m3",
    "valor_inicial",
    "valor_final",
    "desde",
    "hasta"
]


salida = pd.DataFrame(
    resultado,
    columns=columnas
)


# ============================================================
# 12. REDONDEO
# ============================================================

if not salida.empty:

    salida["agua_m3"] = (
        salida["agua_m3"]
        .round(3)
    )

    salida["valor_inicial"] = (
        salida["valor_inicial"]
        .round(3)
    )

    salida["valor_final"] = (
        salida["valor_final"]
        .round(3)
    )


# ============================================================
# 13. EXPORTAR EXCEL
# ============================================================

salida.to_excel(
    ARCHIVO_SALIDA,
    index=False,
    sheet_name="Datos"
)


# ============================================================
# 14. RESUMEN
# ============================================================

print()
print("========================================")
print("EXPORTACIÓN TERMINADA")
print("========================================")

print(
    f"Días analizados   : "
    f"{dias_totales}"
)

print(
    f"Días exportados   : "
    f"{dias_exportados}"
)

print(
    f"Días sin datos    : "
    f"{dias_sin_datos}"
)

print(
    f"Días negativos    : "
    f"{dias_negativos}"
)


if not salida.empty:

    print(
        f"Primer día        : "
        f"{salida.iloc[0]['desde']}"
    )

    print(
        f"Último día        : "
        f"{salida.iloc[-1]['hasta']}"
    )

    print(
        f"Consumo total     : "
        f"{salida['agua_m3'].sum():,.2f} m3"
    )

    print(
        f"Consumo promedio  : "
        f"{salida['agua_m3'].mean():,.2f} m3/día"
    )


print(
    f"Archivo           : "
    f"{ARCHIVO_SALIDA}"
)

print("========================================")