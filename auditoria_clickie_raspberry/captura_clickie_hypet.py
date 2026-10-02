# =============================================================================
# CAPTURA Y AUDITORÍA CLICKIE
# =============================================================================
#
# PROYECTO:
#     Saneamiento histórico Raspberry -> Ignition
#
# OBJETIVO:
#
#     Consultar Clickie para:
#
#         - Hypet 400-3
#         - Hypet 500-2
#
#     y reconstruir el consumo energético de cada día operacional:
#
#             07:00 del día D
#                 hasta
#             07:00 del día D+1
#
#
# MOTIVACIÓN:
#
#     En el Historian de Ignition encontramos:
#
#         1. valores de EA iguales a cero;
#         2. cambios de escala aproximados x0.1;
#         3. consumos diarios absurdamente altos en gnrMain.
#
#     En lugar de intentar reconstruir todavía esos errores desde el propio
#     Historian, utilizaremos Clickie como fuente externa de contraste.
#
#
# IMPORTANTE:
#
#     ESTE SCRIPT:
#
#         - NO se conecta a PostgreSQL;
#         - NO ejecuta UPDATE;
#         - NO ejecuta INSERT;
#         - NO modifica Ignition;
#
#     Solamente consulta Clickie y genera archivos CSV/JSON de auditoría.
#
#
# SALIDAS:
#
#     raw/
#         clickie_raw_hyp400_3.json
#         clickie_raw_hyp400_3.csv
#         clickie_raw_hyp500_2.json
#         clickie_raw_hyp500_2.csv
#
#     reportes/
#         Clickie_Consumo_07a07.csv
#         Clickie_Validacion_PostCambio.csv
#         Clickie_Resumen_Equipos.csv
#
#
# =============================================================================


# =============================================================================
# IMPORTACIONES
# =============================================================================

import os
import csv
import json
import math
import requests

from pathlib import Path
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
from dotenv import load_dotenv


# =============================================================================
# RUTAS DEL PROYECTO
# =============================================================================
#
# El archivo está pensado para quedar en:
#
#     telemetria_modular/
#         .env
#         auditoria_clickie_raspberry/
#             captura_clickie_hypet.py
#
# Por lo tanto:
#
#     BASE_DIR
#         = auditoria_clickie_raspberry/
#
#     PROJECT_ROOT
#         = telemetria_modular/
#
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = BASE_DIR.parent

RAW_DIR = BASE_DIR / "raw"

REPORT_DIR = BASE_DIR / "reportes"

SQL_DIR = BASE_DIR / "sql"


# -----------------------------------------------------------------------------
# Crear automáticamente las carpetas si por algún motivo no existen.
# -----------------------------------------------------------------------------

RAW_DIR.mkdir(
    parents=True,
    exist_ok=True
)

REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

SQL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =============================================================================
# ARCHIVO .ENV
# =============================================================================
#
# Evitamos escribir la API KEY dentro del script.
#
# El archivo:
#
#     telemetria_modular/.env
#
# debería contener:
#
#     CLICKIE_API_KEY=xxxxxxxxxxxxxxxx
#     CLICKIE_ACCOUNT_ID=63
#
# =============================================================================

load_dotenv(
    PROJECT_ROOT / ".env"
)


# =============================================================================
# CONFIGURACIÓN GENERAL
# =============================================================================

TZ = ZoneInfo(
    "America/Santiago"
)


API_URL = (
    "https://api.clickie.io/v4/data/metric"
)


API_KEY = "0580c356-8b91-4298-bd20-385c2f46226a"
ACCOUNT_ID = "63"


# =============================================================================
# EQUIPOS CLICKIE
# =============================================================================
#
# Se mantiene una estructura por equipo para poder agregar fácilmente más
# dispositivos Raspberry después.
#
# uuid:
#     UUID de la métrica Clickie.
#
# codigo:
#     Nombre lógico utilizado posteriormente para relacionarlo con gnrMain.
#
# nombre:
#     Nombre legible.
#
# =============================================================================

EQUIPOS = [

    {
        "nombre": "Hypet 400-3",
        "codigo": "hyp400_3",
        "uuid": "38e371c4-f2e7-46ed-a0a7-7ba6a5dab360"
    },

    {
        "nombre": "Hypet 500-2",
        "codigo": "hyp500_2",
        "uuid": "9faeb035-e10e-4fd9-87f4-70632f2753d2"
    }

]


# =============================================================================
# PERÍODO DE ANÁLISIS
# =============================================================================
#
# Queremos capturar:
#
#     - período anterior al problema;
#     - días donde aparecieron los ceros;
#     - día donde ocurrió el cambio de escala;
#     - varios días posteriores;
#     - datos posteriores hasta el último día operacional completamente cerrado.
#
#
# PRIMER_DIA_OPERACIONAL:
#
#     2026-07-30 significa:
#
#         inicio = 2026-07-30 07:00
#         cierre = 2026-07-31 07:00
#
#
# El último día se calcula automáticamente.
#
# Si actualmente son, por ejemplo:
#
#     24-08-2026 11:00
#
# entonces el último día operacional cerrado es:
#
#     23-08-2026
#
# porque:
#
#     23-08 07:00 -> 24-08 07:00
#
# ya terminó.
#
# =============================================================================

PRIMER_DIA_OPERACIONAL = date(
    2026,
    1,
    2
)


# -----------------------------------------------------------------------------
# Inicio del tramo que consideramos "posterior al cambio".
#
# La discontinuidad detectada ocurrió el 03-08 aproximadamente a las 13:12.
#
# Desde el día operacional 04-08 ambos bordes 07:00 deberían estar ya en el
# nuevo régimen, por lo que este tramo será muy útil para validar estabilidad.
# -----------------------------------------------------------------------------

INICIO_VALIDACION_POST_CAMBIO = date(
    2026,
    8,
    4
)


# =============================================================================
# PARÁMETROS DEL DÍA OPERACIONAL
# =============================================================================

HORA_CORTE = 7

MINUTO_CORTE = 0


# =============================================================================
# TOLERANCIAS
# =============================================================================
#
# Clickie puede no tener exactamente un dato:
#
#     07:00:00
#
# Puede existir:
#
#     06:58
#     07:01
#     07:04
#
# Buscaremos el punto más cercano dentro de esta tolerancia.
#
# =============================================================================

TOLERANCIA_BORDE_MINUTOS = 10


# -----------------------------------------------------------------------------
# Margen extra pedido a la API.
#
# Evita que un punto cercano al inicio o cierre quede fuera del rango solicitado.
# -----------------------------------------------------------------------------

MARGEN_API_MINUTOS = 30


# =============================================================================
# UTILIDADES DE FECHA
# =============================================================================

def ultimo_dia_operacional_cerrado():
    """
    Calcula automáticamente cuál es el último día operacional completamente
    cerrado en el momento de ejecutar el script.

    Ejemplo:

        Ahora:
            24-08 11:00

        Último día cerrado:
            23-08

        porque:
            23-08 07:00 -> 24-08 07:00

        ya terminó.

    Si ejecutáramos antes de las 07:00, habría que retroceder un día adicional.
    """

    ahora = datetime.now(
        TZ
    )

    corte_hoy = datetime.combine(
        ahora.date(),
        time(
            HORA_CORTE,
            MINUTO_CORTE
        ),
        tzinfo=TZ
    )


    if ahora >= corte_hoy:

        return (
            ahora.date()
            - timedelta(days=1)
        )

    else:

        return (
            ahora.date()
            - timedelta(days=2)
        )


# =============================================================================
# FORMATO DATETIME
# =============================================================================

def formato_dt(dt):
    """
    Convierte datetime a texto legible con milisegundos.
    """

    if dt is None:

        return ""


    return dt.strftime(
        "%Y-%m-%d %H:%M:%S.%f"
    )[:-3]


# =============================================================================
# AGREGAR PUNTO CLICKIE
# =============================================================================

def agregar_punto(
    puntos,
    ts,
    value
):
    """
    Convierte una pareja:

        timestamp
        value

    en la estructura estándar utilizada internamente por el script.
    """

    try:

        ts = float(ts)
        value = float(value)

    except (
        TypeError,
        ValueError
    ):

        return


    # -------------------------------------------------------------------------
    # Rechazar NaN / infinito.
    # -------------------------------------------------------------------------

    if not math.isfinite(value):

        return


    # -------------------------------------------------------------------------
    # Clickie puede entregar timestamp en:
    #
    #     segundos
    #
    # o
    #
    #     milisegundos.
    #
    # Si el número es muy grande asumimos milisegundos.
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


# =============================================================================
# PARSER DE RESPUESTA CLICKIE
# =============================================================================

def parse_clickie_response(
    payload
):
    """
    Interpreta distintos formatos posibles de respuesta Clickie.

    Se reutiliza la lógica del script que ya habíamos probado anteriormente.
    """

    puntos = []


    # =========================================================================
    # Si la respuesta viene encapsulada dentro de "data".
    # =========================================================================

    if (
        isinstance(payload, dict)
        and "data" in payload
    ):

        data = payload["data"]

    else:

        data = payload


    # =========================================================================
    # FORMATO DICCIONARIO
    # =========================================================================

    if isinstance(
        data,
        dict
    ):

        for key, value in data.items():


            # -----------------------------------------------------------------
            # Ejemplo:
            #
            # {
            #     "1787280000": 2583000
            # }
            # -----------------------------------------------------------------

            if isinstance(
                value,
                (
                    int,
                    float,
                    str
                )
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
            #     "x": {
            #         "timestamp": 1787280000,
            #         "value": 2583000
            #     }
            # }
            # -----------------------------------------------------------------

            elif isinstance(
                value,
                dict
            ):

                ts = (
                    value.get("timestamp")
                    or value.get("ts")
                    or value.get("time")
                    or key
                )


                val = (

                    value.get("value")

                    if value.get("value")
                    is not None

                    else value.get("val")

                )


                if val is not None:

                    agregar_punto(
                        puntos,
                        ts,
                        val
                    )


    # =========================================================================
    # FORMATO LISTA
    # =========================================================================

    elif isinstance(
        data,
        list
    ):

        for item in data:


            # -----------------------------------------------------------------
            # Lista de objetos.
            # -----------------------------------------------------------------

            if isinstance(
                item,
                dict
            ):

                ts = (
                    item.get("timestamp")
                    or item.get("ts")
                    or item.get("time")
                    or item.get("date")
                )


                val = (

                    item.get("value")

                    if item.get("value")
                    is not None

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
            # Lista del tipo:
            #
            # [
            #     [timestamp, value],
            #     [timestamp, value]
            # ]
            # -----------------------------------------------------------------

            elif (
                isinstance(
                    item,
                    (
                        list,
                        tuple
                    )
                )
                and len(item) >= 2
            ):

                agregar_punto(
                    puntos,
                    item[0],
                    item[1]
                )


    # =========================================================================
    # ELIMINACIÓN DE DUPLICADOS
    # =========================================================================
    #
    # Si Clickie devuelve dos veces el mismo timestamp,
    # nos quedamos con la última aparición.
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
    equipo,
    desde,
    hasta
):
    """
    Consulta la serie completa de un equipo dentro del rango solicitado.

    Además guarda la respuesta JSON original para auditoría.
    """

    if not API_KEY:

        raise RuntimeError(
            "\n"
            "No existe CLICKIE_API_KEY en el .env.\n"
            "\n"
            "Agrega en:\n"
            f"    {PROJECT_ROOT / '.env'}\n"
            "\n"
            "la variable:\n"
            "    CLICKIE_API_KEY=...\n"
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

        "Authorization":
            API_KEY,

        "Account":
            ACCOUNT_ID,

        "Accept":
            "application/json"

    }


    params = {

        "metric":
            equipo["uuid"],

        "from":
            int(
                desde_api.timestamp()
            ),

        "to":
            int(
                hasta_api.timestamp()
            )

    }


    print()
    print("=" * 90)

    print(
        f"CONSULTANDO CLICKIE | "
        f"{equipo['nombre']}"
    )

    print("=" * 90)


    print(
        f"UUID  : {equipo['uuid']}"
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
        timeout=90
    )


    print(
        f"HTTP  : {response.status_code}"
    )


    response.raise_for_status()


    payload = response.json()


    # =========================================================================
    # GUARDAR JSON ORIGINAL
    # =========================================================================

    archivo_json = (
        RAW_DIR
        / f"clickie_raw_{equipo['codigo']}.json"
    )


    with open(
        archivo_json,
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
            f"No fue posible interpretar puntos "
            f"para {equipo['nombre']}."
        )


    print(
        f"Lecturas interpretadas : "
        f"{len(puntos):,}"
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
# EXPORTAR RAW A CSV
# =============================================================================

def exportar_raw_csv(
    equipo,
    puntos
):
    """
    Guarda cada lectura interpretada de Clickie.

    Esto nos permite posteriormente revisar manualmente cualquier timestamp.
    """

    archivo = (
        RAW_DIR
        / f"clickie_raw_{equipo['codigo']}.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )


        writer.writerow([

            "equipo",

            "codigo",

            "uuid",

            "fecha_hora",

            "timestamp_epoch",

            "ea"

        ])


        for punto in puntos:

            writer.writerow([

                equipo["nombre"],

                equipo["codigo"],

                equipo["uuid"],

                formato_dt(
                    punto["datetime"]
                ),

                punto["timestamp"],

                punto["value"]

            ])


    return archivo


# =============================================================================
# BUSCAR PUNTO MÁS CERCANO
# =============================================================================

def buscar_mas_cercano(
    puntos,
    objetivo,
    tolerancia_minutos
):
    """
    Busca en la serie Clickie el punto temporalmente más cercano a un timestamp.

    Si el punto más cercano está fuera de la tolerancia, devuelve None.
    """

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
# RECONSTRUCCIÓN 07:00 -> 07:00
# =============================================================================

def calcular_consumos_diarios(
    equipo,
    puntos,
    primer_dia,
    ultimo_dia
):
    """
    Calcula los consumos de cada día operacional utilizando directamente
    los acumuladores de Clickie.

    Fórmula:

        consumo = EA(fin) - EA(inicio)

    donde:

        inicio = D 07:00
        fin    = D+1 07:00
    """

    filas = []


    dia_actual = primer_dia


    while dia_actual <= ultimo_dia:


        # =====================================================================
        # DEFINIR BORDES DEL DÍA OPERACIONAL
        # =====================================================================

        inicio_objetivo = datetime.combine(

            dia_actual,

            time(
                HORA_CORTE,
                MINUTO_CORTE
            ),

            tzinfo=TZ

        )


        fin_objetivo = (

            inicio_objetivo
            + timedelta(days=1)

        )


        # =====================================================================
        # BUSCAR DATOS CLICKIE CERCANOS A LOS BORDES
        # =====================================================================

        inicio = buscar_mas_cercano(

            puntos,

            inicio_objetivo,

            TOLERANCIA_BORDE_MINUTOS

        )


        fin = buscar_mas_cercano(

            puntos,

            fin_objetivo,

            TOLERANCIA_BORDE_MINUTOS

        )


        # =====================================================================
        # CLASIFICACIÓN
        # =====================================================================

        estado = "OK"

        consumo = None


        if inicio is None:

            estado = "SIN_BORDE_INICIAL"


        elif fin is None:

            estado = "SIN_BORDE_FINAL"


        elif (
            inicio["value"] == 0
            or fin["value"] == 0
        ):

            estado = "BORDE_EN_CERO"


        else:

            consumo = (
                fin["value"]
                - inicio["value"]
            )


            if consumo < 0:

                estado = "DELTA_NEGATIVO"


        # =====================================================================
        # GUARDAR RESULTADO
        # =====================================================================

        filas.append({

            "equipo":
                equipo["nombre"],

            "codigo":
                equipo["codigo"],

            "uuid":
                equipo["uuid"],

            "dia_operacional":
                dia_actual.isoformat(),

            "inicio_objetivo":
                inicio_objetivo,

            "inicio_clickie":
                (
                    inicio["datetime"]
                    if inicio
                    else None
                ),

            "distancia_inicio_segundos":
                (
                    inicio["distancia_segundos"]
                    if inicio
                    else None
                ),

            "ea_inicio":
                (
                    inicio["value"]
                    if inicio
                    else None
                ),

            "fin_objetivo":
                fin_objetivo,

            "fin_clickie":
                (
                    fin["datetime"]
                    if fin
                    else None
                ),

            "distancia_fin_segundos":
                (
                    fin["distancia_segundos"]
                    if fin
                    else None
                ),

            "ea_fin":
                (
                    fin["value"]
                    if fin
                    else None
                ),

            "consumo_kwh":
                consumo,

            "estado":
                estado

        })


        dia_actual += timedelta(
            days=1
        )


    return filas


# =============================================================================
# AUDITORÍA BÁSICA DE LA SERIE RAW
# =============================================================================

def auditar_serie_raw(
    equipo,
    puntos
):
    """
    Hace únicamente una auditoría informativa.

    NO se utiliza para decidir correcciones.

    Cuenta:
        - ceros;
        - retrocesos;
        - rango de valores.

    Lo hacemos porque es útil conocer el comportamiento de Clickie antes de
    utilizarlo como referencia.
    """

    ceros = 0

    retrocesos = 0


    anterior = None


    for punto in puntos:

        valor = punto["value"]


        if valor == 0:

            ceros += 1


        if (
            anterior is not None
            and valor < anterior
            and valor != 0
            and anterior != 0
        ):

            retrocesos += 1


        anterior = valor


    return {

        "equipo":
            equipo["nombre"],

        "codigo":
            equipo["codigo"],

        "uuid":
            equipo["uuid"],

        "lecturas":
            len(puntos),

        "primera_fecha":
            puntos[0]["datetime"],

        "ultima_fecha":
            puntos[-1]["datetime"],

        "valor_minimo":
            min(
                p["value"]
                for p in puntos
            ),

        "valor_maximo":
            max(
                p["value"]
                for p in puntos
            ),

        "ceros":
            ceros,

        "retrocesos_sin_ceros":
            retrocesos

    }


# =============================================================================
# EXPORTAR CONSUMOS 07:00 -> 07:00
# =============================================================================

def exportar_consumos_diarios(
    filas
):
    """
    Genera el archivo maestro que posteriormente compararemos con gnrMain.
    """

    archivo = (
        REPORT_DIR
        / "Clickie_Consumo_07a07.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )


        writer.writerow([

            "equipo",

            "codigo",

            "uuid",

            "dia_operacional",

            "inicio_objetivo",

            "inicio_clickie",

            "distancia_inicio_min",

            "ea_inicio",

            "fin_objetivo",

            "fin_clickie",

            "distancia_fin_min",

            "ea_fin",

            "consumo_kwh",

            "estado"

        ])


        for fila in filas:

            writer.writerow([

                fila["equipo"],

                fila["codigo"],

                fila["uuid"],

                fila["dia_operacional"],

                formato_dt(
                    fila["inicio_objetivo"]
                ),

                formato_dt(
                    fila["inicio_clickie"]
                ),

                (
                    round(
                        fila[
                            "distancia_inicio_segundos"
                        ] / 60,
                        3
                    )

                    if fila[
                        "distancia_inicio_segundos"
                    ] is not None

                    else ""
                ),

                (
                    fila["ea_inicio"]
                    if fila["ea_inicio"] is not None
                    else ""
                ),

                formato_dt(
                    fila["fin_objetivo"]
                ),

                formato_dt(
                    fila["fin_clickie"]
                ),

                (
                    round(
                        fila[
                            "distancia_fin_segundos"
                        ] / 60,
                        3
                    )

                    if fila[
                        "distancia_fin_segundos"
                    ] is not None

                    else ""
                ),

                (
                    fila["ea_fin"]
                    if fila["ea_fin"] is not None
                    else ""
                ),

                (
                    fila["consumo_kwh"]
                    if fila["consumo_kwh"] is not None
                    else ""
                ),

                fila["estado"]

            ])


    return archivo


# =============================================================================
# EXPORTAR MUESTREO POSTERIOR AL CAMBIO
# =============================================================================

def exportar_validacion_post_cambio(
    filas
):
    """
    Guarda únicamente el período posterior al cambio observado en Ignition.

    Esto nos permitirá responder una pregunta muy concreta:

        ¿Después de la fecha problemática los consumos Clickie se mantienen
        coherentes día tras día?

    Posteriormente compararemos este CSV contra gnrMain.
    """

    archivo = (
        REPORT_DIR
        / "Clickie_Validacion_PostCambio.csv"
    )


    filas_post = [

        fila

        for fila in filas

        if date.fromisoformat(
            fila["dia_operacional"]
        ) >= INICIO_VALIDACION_POST_CAMBIO

    ]


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )


        writer.writerow([

            "equipo",

            "codigo",

            "dia_operacional",

            "ea_inicio",

            "ea_fin",

            "consumo_kwh",

            "estado"

        ])


        for fila in filas_post:

            writer.writerow([

                fila["equipo"],

                fila["codigo"],

                fila["dia_operacional"],

                fila["ea_inicio"],

                fila["ea_fin"],

                fila["consumo_kwh"],

                fila["estado"]

            ])


    return archivo


# =============================================================================
# EXPORTAR RESUMEN DE EQUIPOS
# =============================================================================

def exportar_resumen(
    resumenes
):
    """
    Guarda información general sobre las series Clickie consultadas.
    """

    archivo = (
        REPORT_DIR
        / "Clickie_Resumen_Equipos.csv"
    )


    with open(
        archivo,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as f:

        writer = csv.writer(
            f
        )


        writer.writerow([

            "equipo",

            "codigo",

            "uuid",

            "lecturas",

            "primera_fecha",

            "ultima_fecha",

            "valor_minimo",

            "valor_maximo",

            "ceros",

            "retrocesos_sin_ceros"

        ])


        for item in resumenes:

            writer.writerow([

                item["equipo"],

                item["codigo"],

                item["uuid"],

                item["lecturas"],

                formato_dt(
                    item["primera_fecha"]
                ),

                formato_dt(
                    item["ultima_fecha"]
                ),

                item["valor_minimo"],

                item["valor_maximo"],

                item["ceros"],

                item["retrocesos_sin_ceros"]

            ])


    return archivo


# =============================================================================
# MOSTRAR CONSUMOS DE INTERÉS EN CONSOLA
# =============================================================================

def mostrar_periodo_critico(
    filas
):
    """
    Imprime los días cercanos al problema para revisarlos inmediatamente sin
    necesidad de abrir los CSV.
    """

    desde = date(
        2026,
        7,
        31
    )

    hasta = date(
        2026,
        8,
        6
    )


    print()
    print("=" * 90)

    print(
        "CONSUMOS CLICKIE - PERÍODO CRÍTICO"
    )

    print("=" * 90)


    for fila in filas:

        dia = date.fromisoformat(
            fila["dia_operacional"]
        )


        if not (
            desde
            <= dia
            <= hasta
        ):

            continue


        consumo = fila[
            "consumo_kwh"
        ]


        if consumo is None:

            consumo_texto = "N/D"

        else:

            consumo_texto = (
                f"{consumo:,.3f} kWh"
            )


        print(

            f"{fila['dia_operacional']} | "
            f"{fila['equipo']:<15} | "
            f"{consumo_texto:>18} | "
            f"{fila['estado']}"

        )


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Flujo principal.
    """

    print()
    print("=" * 90)

    print(
        "AUDITORÍA CLICKIE - RASPBERRY / HYPET 400-3 Y HYPET 500-2"
    )

    print("=" * 90)


    # =========================================================================
    # CALCULAR ÚLTIMO DÍA OPERACIONAL CERRADO
    # =========================================================================

    ultimo_dia = (
        ultimo_dia_operacional_cerrado()
    )


    print()
    print(
        f"Primer día operacional : "
        f"{PRIMER_DIA_OPERACIONAL}"
    )

    print(
        f"Último día cerrado     : "
        f"{ultimo_dia}"
    )


    # =========================================================================
    # VENTANA COMPLETA PARA CONSULTAR API
    # =========================================================================

    inicio_api = datetime.combine(

        PRIMER_DIA_OPERACIONAL,

        time(
            HORA_CORTE,
            MINUTO_CORTE
        ),

        tzinfo=TZ

    )


    fin_api = datetime.combine(

        ultimo_dia
        + timedelta(days=1),

        time(
            HORA_CORTE,
            MINUTO_CORTE
        ),

        tzinfo=TZ

    )


    todas_filas = []

    resumenes = []


    # =========================================================================
    # PROCESAR CADA EQUIPO
    # =========================================================================

    for equipo in EQUIPOS:


        # ---------------------------------------------------------------------
        # Consultar Clickie.
        # ---------------------------------------------------------------------

        puntos = consultar_clickie(

            equipo,

            inicio_api,

            fin_api

        )


        # ---------------------------------------------------------------------
        # Guardar serie completa en CSV.
        # ---------------------------------------------------------------------

        archivo_raw = exportar_raw_csv(

            equipo,

            puntos

        )


        # ---------------------------------------------------------------------
        # Auditoría informativa.
        # ---------------------------------------------------------------------

        resumen = auditar_serie_raw(

            equipo,

            puntos

        )


        resumenes.append(
            resumen
        )


        # ---------------------------------------------------------------------
        # Calcular día operacional.
        # ---------------------------------------------------------------------

        filas = calcular_consumos_diarios(

            equipo,

            puntos,

            PRIMER_DIA_OPERACIONAL,

            ultimo_dia

        )


        todas_filas.extend(
            filas
        )


        print()
        print(
            f"Raw CSV : {archivo_raw}"
        )


    # =========================================================================
    # ORDENAR RESULTADOS
    # =========================================================================

    todas_filas.sort(

        key=lambda fila: (

            fila["dia_operacional"],

            fila["equipo"]

        )

    )


    # =========================================================================
    # GENERAR REPORTES
    # =========================================================================

    archivo_diario = (
        exportar_consumos_diarios(
            todas_filas
        )
    )


    archivo_post = (
        exportar_validacion_post_cambio(
            todas_filas
        )
    )


    archivo_resumen = (
        exportar_resumen(
            resumenes
        )
    )


    # =========================================================================
    # MOSTRAR DÍAS CRÍTICOS
    # =========================================================================

    mostrar_periodo_critico(
        todas_filas
    )


    # =========================================================================
    # RESUMEN FINAL
    # =========================================================================

    print()
    print("=" * 90)

    print(
        "ARCHIVOS GENERADOS"
    )

    print("=" * 90)


    print(
        f"Consumo 07->07 : "
        f"{archivo_diario}"
    )

    print(
        f"Post cambio    : "
        f"{archivo_post}"
    )

    print(
        f"Resumen        : "
        f"{archivo_resumen}"
    )


    print()
    print(
        f"Raw            : "
        f"{RAW_DIR}"
    )


    # =========================================================================
    # RECORDATORIO DE SEGURIDAD
    # =========================================================================

    print()
    print("=" * 90)

    print(
        "POSTGRESQL NO FUE MODIFICADO"
    )

    print("=" * 90)


    print(
        "La siguiente etapa será comparar "
        "Clickie_Consumo_07a07.csv contra gnrMain."
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    main()