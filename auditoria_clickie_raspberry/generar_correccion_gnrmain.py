#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# =============================================================================
# GENERADOR DE CORRECCIÓN CONTROLADA PARA gnrMain
# =============================================================================
#
# PROYECTO:
#     Auditoría Clickie / Raspberry / Ignition
#
# PROPÓSITO:
#     Tomar el archivo:
#
#         Comparacion_Clickie_gnrMain.csv
#
#     generado por la etapa anterior y construir una PROPUESTA DE CORRECCIÓN
#     para:
#
#         gnrProDb01
#         process."gnrMain"
#
#     siguiendo las reglas que ya fueron validadas durante la auditoría.
#
#
# ESTRATEGIAS APLICADAS
# =============================================================================
#
# 1) HYPET 400-3 / HYPET 500-2
#    --------------------------------
#
#    Período a reconstruir:
#
#        2026-01-02 -> 2026-08-03 inclusive
#
#    Estrategia:
#
#        value       = consumo 07:00 -> 07:00 obtenido desde Clickie
#        accumulated = acumulador de cierre obtenido desde Clickie
#
#    Sólo se reemplazan filas cuyo estado Clickie sea "OK".
#
#    Los días donde Clickie no tiene datos NO se inventan y NO se modifican.
#
#
# 2) CCM2 / CCM3 / KHS8 / BLOMACS 10
#    ---------------------------------
#
#    Período auditado:
#
#        2026-01-02 -> 2026-08-23 inclusive
#
#    Hallazgo:
#
#        gnrMain está almacenado exactamente en una escala x10 respecto del
#        acumulador de Clickie.
#
#    Estrategia:
#
#        value       = value_actual * 0.1
#        accumulated = accumulated_actual * 0.1
#
#    Se aplica por ID explícito obtenido desde el CSV de auditoría.
#
#
# 3) EQUIPOS QUE ESTE SCRIPT NO TOCA
#    --------------------------------
#
#        CCM1
#        SB08
#        IPS400-2
#
#    CCM1 y SB08 fueron utilizados como controles y están esencialmente sanos.
#
#    IPS400-2 presenta una historia diferente y queda deliberadamente fuera de
#    esta primera corrección para tratarlo como caso independiente.
#
#
# SEGURIDAD
# =============================================================================
#
# ESTE SCRIPT:
#
#     - NO abre conexión a PostgreSQL.
#     - NO ejecuta UPDATE.
#     - NO ejecuta INSERT sobre gnrMain.
#
# Solamente genera:
#
#     reportes/Correccion_gnrMain_Detalle.csv
#     reportes/Correccion_gnrMain_Resumen.csv
#     sql/Correccion_gnrMain_PREVIEW_ROLLBACK.sql
#
# El SQL generado termina SIEMPRE con:
#
#     ROLLBACK;
#
# Por lo tanto la primera ejecución en pgAdmin sirve exclusivamente como
# simulación y validación.
#
#
# PROTECCIONES DEL SQL
# =============================================================================
#
# Antes de ejecutar el UPDATE, el SQL generado verifica:
#
#     - que todos los IDs sigan existiendo;
#     - que nameTag siga coincidiendo;
#     - que dateIn siga correspondiendo al día operacional auditado;
#     - que value no haya cambiado desde la auditoría;
#     - que accumulated no haya cambiado desde la auditoría.
#
# Si alguna de esas verificaciones falla:
#
#     RAISE EXCEPTION
#
# y el UPDATE NO continúa.
#
# Esto también evita ejecutar accidentalmente dos veces la misma corrección.
#
# =============================================================================


# =============================================================================
# IMPORTACIONES
# =============================================================================

import csv

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path


# =============================================================================
# RUTAS DEL PROYECTO
# =============================================================================
#
# Estructura esperada:
#
# auditoria_clickie_raspberry/
# │
# ├── generar_correccion_gnrmain.py
# │
# ├── reportes/
# │   ├── Comparacion_Clickie_gnrMain.csv
# │   └── ...
# │
# └── sql/
#
# =============================================================================

BASE_DIR = Path(__file__).resolve().parent

REPORT_DIR = BASE_DIR / "reportes"

SQL_DIR = BASE_DIR / "sql"


REPORT_DIR.mkdir(
    parents=True,
    exist_ok=True
)

SQL_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# =============================================================================
# ARCHIVO DE ENTRADA
# =============================================================================

NOMBRE_COMPARACION = "Comparacion_Clickie_gnrMain.csv"


# =============================================================================
# ARCHIVOS DE SALIDA
# =============================================================================

ARCHIVO_DETALLE = (
    REPORT_DIR
    / "Correccion_gnrMain_Detalle.csv"
)

ARCHIVO_RESUMEN = (
    REPORT_DIR
    / "Correccion_gnrMain_Resumen.csv"
)

ARCHIVO_SQL = (
    SQL_DIR
    / "Correccion_gnrMain_PREVIEW_ROLLBACK.sql"
)


# =============================================================================
# CONFIGURACIÓN DE REGLAS
# =============================================================================


# -----------------------------------------------------------------------------
# HYPET
# -----------------------------------------------------------------------------

HYPET_CODES = {
    "hyp400_3",
    "hyp500_2",
}


HYPET_DESDE = date(
    2026,
    1,
    2
)


# -----------------------------------------------------------------------------
# Se reconstruye hasta 03-08 inclusive.
#
# Desde 04-08 en adelante la auditoría mostró que los acumuladores de gnrMain
# ya están en la misma unidad que Clickie y los consumos vuelven a estar
# razonablemente alineados.
# -----------------------------------------------------------------------------

HYPET_HASTA = date(
    2026,
    8,
    3
)


# -----------------------------------------------------------------------------
# Sólo aceptamos días donde la captura Clickie pudo construir correctamente
# ambos bordes del día operacional.
# -----------------------------------------------------------------------------

ESTADO_CLICKIE_VALIDO = "OK"


# -----------------------------------------------------------------------------
# EQUIPOS CON ERROR DE ESCALA x10 EN gnrMain.
#
# La corrección requerida es x0.1.
# -----------------------------------------------------------------------------

ESCALA_X01_CODES = {
    "ccm2",
    "ccm3",
    "khs8",
    "blm10",
}


ESCALA_X01_DESDE = date(
    2026,
    1,
    2
)


# -----------------------------------------------------------------------------
# Usamos como corte el último día incluido en la auditoría entregada.
#
# Deliberadamente NO incluimos filas posteriores.
#
# Esto evita modificar datos nuevos que puedan haber sido generados después
# de corregir el escalamiento directamente en Ignition.
# -----------------------------------------------------------------------------

ESCALA_X01_HASTA = date(
    2026,
    8,
    23
)


FACTOR_ESCALA = Decimal(
    "0.1"
)


# =============================================================================
# COLUMNAS OBLIGATORIAS DEL CSV
# =============================================================================

COLUMNAS_REQUERIDAS = {

    "dia_operacional",
    "equipo",
    "codigo",

    "estado_clickie",

    "clickie_kwh",
    "clickie_ea_fin_kwh",

    "gnr_id",
    "gnr_value",
    "gnr_accumulated",

    "cantidad_gnr",
    "diagnostico",
}


# =============================================================================
# UTILIDADES
# =============================================================================

def buscar_archivo_entrada():
    """
    Busca el CSV de comparación en ubicaciones habituales.

    Orden de búsqueda:

        1. reportes/
        2. carpeta del propio script
        3. directorio desde el cual se ejecutó Python

    Esto hace que el script sea cómodo tanto dentro del proyecto como durante
    pruebas aisladas.
    """

    candidatos = [

        REPORT_DIR / NOMBRE_COMPARACION,

        BASE_DIR / NOMBRE_COMPARACION,

        Path.cwd() / NOMBRE_COMPARACION,
    ]


    for candidato in candidatos:

        if candidato.exists():

            return candidato


    texto = "\n".join(
        f"  - {ruta}"
        for ruta in candidatos
    )


    raise FileNotFoundError(
        "\n"
        f"No se encontró {NOMBRE_COMPARACION}.\n"
        "\n"
        "Ubicaciones revisadas:\n"
        f"{texto}\n"
    )


def limpiar_texto(valor):
    """
    Normaliza texto proveniente del CSV.
    """

    if valor is None:

        return ""


    return str(
        valor
    ).strip()


def parse_fecha(valor):
    """
    Convierte YYYY-MM-DD a datetime.date.
    """

    texto = limpiar_texto(
        valor
    )


    if not texto:

        return None


    return datetime.strptime(
        texto[:10],
        "%Y-%m-%d"
    ).date()


def parse_decimal(valor):
    """
    Convierte un valor de CSV a Decimal.

    Usamos Decimal en vez de float porque:

        - evita introducir errores binarios innecesarios;
        - conserva mejor los valores originales de gnrMain;
        - permite generar SQL numéricamente limpio.
    """

    texto = limpiar_texto(
        valor
    )


    if not texto:

        return None


    if texto.lower() in {
        "nan",
        "none",
        "null"
    }:

        return None


    try:

        return Decimal(
            texto
        )

    except InvalidOperation:

        raise ValueError(
            f"Valor numérico inválido: {valor!r}"
        )


def parse_int(valor):
    """
    Convierte IDs / contadores provenientes del CSV a int.

    Algunos CSV pueden almacenar IDs como:
        1234
    o:
        1234.0

    Decimal permite aceptar ambos sin perder precisión.
    """

    numero = parse_decimal(
        valor
    )


    if numero is None:

        return None


    return int(
        numero
    )


def decimal_sql(valor):
    """
    Convierte Decimal a literal SQL.

    None -> NULL
    """

    if valor is None:

        return "NULL"


    return format(
        valor,
        "f"
    )


def sql_text(valor):
    """
    Escapa texto para incorporarlo de forma segura como literal SQL generado.

    No estamos recibiendo texto arbitrario desde internet; aun así conviene
    escapar comillas simples correctamente.
    """

    if valor is None:

        return "NULL"


    texto = str(
        valor
    ).replace(
        "'",
        "''"
    )


    return (
        "'"
        + texto
        + "'"
    )


def valor_csv(valor):
    """
    Convierte Decimal / None a representación apta para CSV.
    """

    if valor is None:

        return ""


    if isinstance(
        valor,
        Decimal
    ):

        return format(
            valor,
            "f"
        )


    return valor


# =============================================================================
# CARGA DEL CSV
# =============================================================================

def cargar_comparacion(
    archivo
):
    """
    Lee y valida el archivo de comparación.
    """

    filas = []


    with open(
        archivo,
        "r",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        reader = csv.DictReader(
            f
        )


        if reader.fieldnames is None:

            raise RuntimeError(
                "El CSV no contiene encabezados."
            )


        columnas = set(
            reader.fieldnames
        )


        faltantes = (
            COLUMNAS_REQUERIDAS
            - columnas
        )


        if faltantes:

            raise RuntimeError(
                "Faltan columnas obligatorias en el CSV: "
                + ", ".join(
                    sorted(
                        faltantes
                    )
                )
            )


        for numero_linea, row in enumerate(
            reader,
            start=2
        ):

            try:

                fila = {

                    "numero_linea":
                        numero_linea,

                    "dia_operacional":
                        parse_fecha(
                            row[
                                "dia_operacional"
                            ]
                        ),

                    "equipo":
                        limpiar_texto(
                            row[
                                "equipo"
                            ]
                        ),

                    "codigo":
                        limpiar_texto(
                            row[
                                "codigo"
                            ]
                        ),

                    "estado_clickie":
                        limpiar_texto(
                            row[
                                "estado_clickie"
                            ]
                        ),

                    "clickie_kwh":
                        parse_decimal(
                            row[
                                "clickie_kwh"
                            ]
                        ),

                    "clickie_ea_fin_kwh":
                        parse_decimal(
                            row[
                                "clickie_ea_fin_kwh"
                            ]
                        ),

                    "gnr_id":
                        parse_int(
                            row[
                                "gnr_id"
                            ]
                        ),

                    "gnr_value":
                        parse_decimal(
                            row[
                                "gnr_value"
                            ]
                        ),

                    "gnr_accumulated":
                        parse_decimal(
                            row[
                                "gnr_accumulated"
                            ]
                        ),

                    "cantidad_gnr":
                        parse_int(
                            row[
                                "cantidad_gnr"
                            ]
                        ),

                    "diagnostico_original":
                        limpiar_texto(
                            row[
                                "diagnostico"
                            ]
                        ),
                }


                filas.append(
                    fila
                )


            except Exception as exc:

                raise RuntimeError(
                    f"Error leyendo línea {numero_linea}: {exc}"
                ) from exc


    return filas


# =============================================================================
# CONSTRUCCIÓN DE CORRECCIONES
# =============================================================================

def construir_correcciones(
    filas
):
    """
    Aplica las reglas de negocio acordadas.

    Devuelve:

        correcciones
        omitidas
    """

    correcciones = []

    omitidas = []


    ids_usados = set()


    for fila in filas:

        dia = fila[
            "dia_operacional"
        ]

        codigo = fila[
            "codigo"
        ]

        gnr_id = fila[
            "gnr_id"
        ]


        # =====================================================================
        # VALIDACIONES GENERALES
        # =====================================================================

        if dia is None:

            omitidas.append(
                (
                    fila,
                    "SIN_DIA_OPERACIONAL"
                )
            )

            continue


        if gnr_id is None:

            omitidas.append(
                (
                    fila,
                    "SIN_GNR_ID"
                )
            )

            continue


        # ---------------------------------------------------------------------
        # No queremos corregir filas duplicadas de gnrMain mediante este script.
        #
        # En el CSV actual cantidad_gnr debería ser 1.
        # Si apareciera otra cosa, se deja fuera para revisión manual.
        # ---------------------------------------------------------------------

        if (
            fila["cantidad_gnr"] is not None
            and fila["cantidad_gnr"] != 1
        ):

            omitidas.append(
                (
                    fila,
                    "CANTIDAD_GNR_DISTINTA_DE_1"
                )
            )

            continue


        # =====================================================================
        # ESTRATEGIA 1
        # HYPET -> REEMPLAZO DIRECTO DESDE CLICKIE
        # =====================================================================

        if (
            codigo in HYPET_CODES
            and HYPET_DESDE
            <= dia
            <= HYPET_HASTA
        ):

            # -----------------------------------------------------------------
            # Sin dato Clickie válido no inventamos nada.
            # -----------------------------------------------------------------

            if (
                fila["estado_clickie"]
                != ESTADO_CLICKIE_VALIDO
            ):

                omitidas.append(
                    (
                        fila,
                        "HYPET_CLICKIE_NO_VALIDO"
                    )
                )

                continue


            if (
                fila["clickie_kwh"]
                is None
                or fila["clickie_ea_fin_kwh"]
                is None
            ):

                omitidas.append(
                    (
                        fila,
                        "HYPET_CLICKIE_SIN_VALORES"
                    )
                )

                continue


            nueva = {

                **fila,

                "estrategia":
                    "REEMPLAZO_CLICKIE_07A07",

                "valor_nuevo":
                    fila[
                        "clickie_kwh"
                    ],

                "acumulado_nuevo":
                    fila[
                        "clickie_ea_fin_kwh"
                    ],

                "factor":
                    None,
            }


            correcciones.append(
                nueva
            )


        # =====================================================================
        # ESTRATEGIA 2
        # CCM2 / CCM3 / KHS8 / BLOMACS -> x0.1
        # =====================================================================

        elif (
            codigo in ESCALA_X01_CODES
            and ESCALA_X01_DESDE
            <= dia
            <= ESCALA_X01_HASTA
        ):

            if (
                fila["gnr_value"]
                is None
                or fila["gnr_accumulated"]
                is None
            ):

                omitidas.append(
                    (
                        fila,
                        "ESCALA_SIN_VALOR_GNR"
                    )
                )

                continue


            nueva = {

                **fila,

                "estrategia":
                    "ESCALA_X0.1",

                "valor_nuevo":
                    (
                        fila[
                            "gnr_value"
                        ]
                        * FACTOR_ESCALA
                    ),

                "acumulado_nuevo":
                    (
                        fila[
                            "gnr_accumulated"
                        ]
                        * FACTOR_ESCALA
                    ),

                "factor":
                    FACTOR_ESCALA,
            }


            correcciones.append(
                nueva
            )


        # =====================================================================
        # TODO LO DEMÁS QUEDA FUERA
        # =====================================================================

        else:

            omitidas.append(
                (
                    fila,
                    "FUERA_DE_REGLA"
                )
            )

            continue


        # =====================================================================
        # PROTECCIÓN CONTRA ID DUPLICADO
        # =====================================================================

        if gnr_id in ids_usados:

            raise RuntimeError(
                "\n"
                f"El gnr_id {gnr_id} aparece más de una vez "
                "dentro de las correcciones.\n"
                "\n"
                "Proceso detenido para evitar un SQL ambiguo."
            )


        ids_usados.add(
            gnr_id
        )


    # =========================================================================
    # ORDENAR RESULTADO
    # =========================================================================

    correcciones.sort(
        key=lambda r: (
            r["dia_operacional"],
            r["codigo"],
            r["gnr_id"]
        )
    )


    return (
        correcciones,
        omitidas
    )


# =============================================================================
# EXPORTAR DETALLE
# =============================================================================

def exportar_detalle(
    correcciones
):
    """
    Exporta cada cambio propuesto.

    Este archivo es la evidencia de auditoría principal antes del SQL.
    """

    columnas = [

        "gnr_id",
        "dia_operacional",
        "equipo",
        "codigo",

        "estrategia",

        "valor_actual",
        "valor_nuevo",

        "acumulado_actual",
        "acumulado_nuevo",

        "clickie_kwh",
        "clickie_ea_fin_kwh",

        "estado_clickie",
        "diagnostico_original",
    ]


    with open(
        ARCHIVO_DETALLE,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columnas
        )


        writer.writeheader()


        for r in correcciones:

            writer.writerow({

                "gnr_id":
                    r["gnr_id"],

                "dia_operacional":
                    r[
                        "dia_operacional"
                    ].isoformat(),

                "equipo":
                    r["equipo"],

                "codigo":
                    r["codigo"],

                "estrategia":
                    r["estrategia"],

                "valor_actual":
                    valor_csv(
                        r[
                            "gnr_value"
                        ]
                    ),

                "valor_nuevo":
                    valor_csv(
                        r[
                            "valor_nuevo"
                        ]
                    ),

                "acumulado_actual":
                    valor_csv(
                        r[
                            "gnr_accumulated"
                        ]
                    ),

                "acumulado_nuevo":
                    valor_csv(
                        r[
                            "acumulado_nuevo"
                        ]
                    ),

                "clickie_kwh":
                    valor_csv(
                        r[
                            "clickie_kwh"
                        ]
                    ),

                "clickie_ea_fin_kwh":
                    valor_csv(
                        r[
                            "clickie_ea_fin_kwh"
                        ]
                    ),

                "estado_clickie":
                    r[
                        "estado_clickie"
                    ],

                "diagnostico_original":
                    r[
                        "diagnostico_original"
                    ],
            })


# =============================================================================
# EXPORTAR RESUMEN
# =============================================================================

def exportar_resumen(
    correcciones,
    omitidas
):
    """
    Genera resumen por equipo y estrategia.
    """

    agrupado = defaultdict(
        lambda: {
            "filas": 0,
            "valor_actual_suma": Decimal("0"),
            "valor_nuevo_suma": Decimal("0"),
        }
    )


    for r in correcciones:

        clave = (
            r["equipo"],
            r["codigo"],
            r["estrategia"]
        )


        agrupado[
            clave
        ]["filas"] += 1


        if r["gnr_value"] is not None:

            agrupado[
                clave
            ][
                "valor_actual_suma"
            ] += r[
                "gnr_value"
            ]


        if r["valor_nuevo"] is not None:

            agrupado[
                clave
            ][
                "valor_nuevo_suma"
            ] += r[
                "valor_nuevo"
            ]


    columnas = [

        "equipo",
        "codigo",
        "estrategia",

        "filas",

        "suma_value_actual",
        "suma_value_propuesta",

        "diferencia",
    ]


    with open(
        ARCHIVO_RESUMEN,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=columnas
        )


        writer.writeheader()


        for (
            equipo,
            codigo,
            estrategia
        ), datos in sorted(
            agrupado.items()
        ):

            diferencia = (
                datos[
                    "valor_nuevo_suma"
                ]
                - datos[
                    "valor_actual_suma"
                ]
            )


            writer.writerow({

                "equipo":
                    equipo,

                "codigo":
                    codigo,

                "estrategia":
                    estrategia,

                "filas":
                    datos[
                        "filas"
                    ],

                "suma_value_actual":
                    valor_csv(
                        datos[
                            "valor_actual_suma"
                        ]
                    ),

                "suma_value_propuesta":
                    valor_csv(
                        datos[
                            "valor_nuevo_suma"
                        ]
                    ),

                "diferencia":
                    valor_csv(
                        diferencia
                    ),
            })


    # -------------------------------------------------------------------------
    # También mostramos las causas principales de omisión en consola.
    # -------------------------------------------------------------------------

    contador_omitidas = Counter(
        motivo
        for _, motivo in omitidas
    )


    return (
        agrupado,
        contador_omitidas
    )


# =============================================================================
# GENERAR SQL DE PREVIEW / ROLLBACK
# =============================================================================

def generar_sql(
    correcciones
):
    """
    Genera SQL transaccional seguro.

    IMPORTANTE:

        El archivo termina en ROLLBACK.

    Primera etapa:
        validar.

    Segunda etapa:
        sólo después de revisar resultados se podrá generar una versión COMMIT.
    """

    with open(
        ARCHIVO_SQL,
        "w",
        encoding="utf-8"
    ) as f:


        # =====================================================================
        # ENCABEZADO
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- CORRECCIÓN gnrMain - PREVIEW CONTROLADO\n"
        )

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            "-- BASE DE DATOS: gnrProDb01\n"
        )

        f.write(
            '-- TABLA        : process."gnrMain"\n'
        )

        f.write(
            "--\n"
        )

        f.write(
            "-- IMPORTANTE:\n"
        )

        f.write(
            "--     ESTE ARCHIVO TERMINA EN ROLLBACK.\n"
        )

        f.write(
            "--     NO DEJA CAMBIOS PERMANENTES.\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            "-- Estrategias incluidas:\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            "--     H400-3 / H500-2:\n"
        )

        f.write(
            "--         reemplazo directo por Clickie 07:00 -> 07:00\n"
        )

        f.write(
            "--         desde 2026-01-02 hasta 2026-08-03.\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            "--     CCM2 / CCM3 / KHS8 / Blomacs10:\n"
        )

        f.write(
            "--         value y accumulated x 0.1\n"
        )

        f.write(
            "--         desde 2026-01-02 hasta 2026-08-23.\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            f"-- Total de IDs incluidos: {len(correcciones)}\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "BEGIN;\n\n"
        )


        # =====================================================================
        # TABLA TEMPORAL
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 1. TABLA TEMPORAL CON LA PROPUESTA DE CORRECCIÓN\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "CREATE TEMP TABLE tmp_gnr_correccion\n"
        )

        f.write(
            "(\n"
        )

        f.write(
            "    id                  BIGINT PRIMARY KEY,\n"
        )

        f.write(
            "    equipo              TEXT NOT NULL,\n"
        )

        f.write(
            "    codigo              TEXT NOT NULL,\n"
        )

        f.write(
            "    dia_operacional     DATE NOT NULL,\n"
        )

        f.write(
            "    estrategia          TEXT NOT NULL,\n"
        )

        f.write(
            "    old_value           DOUBLE PRECISION,\n"
        )

        f.write(
            "    old_accumulated     DOUBLE PRECISION,\n"
        )

        f.write(
            "    new_value           DOUBLE PRECISION,\n"
        )

        f.write(
            "    new_accumulated     DOUBLE PRECISION\n"
        )

        f.write(
            ") ON COMMIT DROP;\n\n"
        )


        # =====================================================================
        # INSERT DE PROPUESTAS
        # =====================================================================

        f.write(
            "INSERT INTO tmp_gnr_correccion\n"
        )

        f.write(
            "(\n"
        )

        f.write(
            "    id,\n"
        )

        f.write(
            "    equipo,\n"
        )

        f.write(
            "    codigo,\n"
        )

        f.write(
            "    dia_operacional,\n"
        )

        f.write(
            "    estrategia,\n"
        )

        f.write(
            "    old_value,\n"
        )

        f.write(
            "    old_accumulated,\n"
        )

        f.write(
            "    new_value,\n"
        )

        f.write(
            "    new_accumulated\n"
        )

        f.write(
            ")\n"
        )

        f.write(
            "VALUES\n"
        )


        lineas = []


        for r in correcciones:

            linea = (

                "    ("

                f"{r['gnr_id']}::bigint, "

                f"{sql_text(r['equipo'])}, "

                f"{sql_text(r['codigo'])}, "

                f"{sql_text(r['dia_operacional'].isoformat())}::date, "

                f"{sql_text(r['estrategia'])}, "

                f"{decimal_sql(r['gnr_value'])}::double precision, "

                f"{decimal_sql(r['gnr_accumulated'])}::double precision, "

                f"{decimal_sql(r['valor_nuevo'])}::double precision, "

                f"{decimal_sql(r['acumulado_nuevo'])}::double precision"

                ")"
            )


            lineas.append(
                linea
            )


        f.write(
            ",\n".join(
                lineas
            )
        )

        f.write(
            ";\n\n"
        )


        # =====================================================================
        # RESUMEN DE LO QUE SE PRETENDE HACER
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 2. RESUMEN DE PROPUESTA\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "SELECT\n"
        )

        f.write(
            "    equipo,\n"
        )

        f.write(
            "    codigo,\n"
        )

        f.write(
            "    estrategia,\n"
        )

        f.write(
            "    COUNT(*) AS filas,\n"
        )

        f.write(
            "    MIN(dia_operacional) AS desde,\n"
        )

        f.write(
            "    MAX(dia_operacional) AS hasta,\n"
        )

        f.write(
            "    SUM(old_value) AS suma_actual,\n"
        )

        f.write(
            "    SUM(new_value) AS suma_propuesta,\n"
        )

        f.write(
            "    SUM(new_value) - SUM(old_value) AS diferencia\n"
        )

        f.write(
            "FROM tmp_gnr_correccion\n"
        )

        f.write(
            "GROUP BY equipo, codigo, estrategia\n"
        )

        f.write(
            "ORDER BY equipo;\n\n"
        )


        # =====================================================================
        # VALIDACIÓN PREVIA OBLIGATORIA
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 3. VALIDACIONES PREVIAS\n"
        )

        f.write(
            "--\n"
        )

        f.write(
            "-- Si algún ID cambió desde que se exportó el CSV, el bloque DO detiene\n"
        )

        f.write(
            "-- inmediatamente el proceso mediante RAISE EXCEPTION.\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "DO $$\n"
        )

        f.write(
            "DECLARE\n"
        )

        f.write(
            "    v_errores INTEGER;\n"
        )

        f.write(
            "BEGIN\n\n"
        )


        # ---------------------------------------------------------------------
        # IDs existentes.
        # ---------------------------------------------------------------------

        f.write(
            "    SELECT COUNT(*)\n"
        )

        f.write(
            "    INTO v_errores\n"
        )

        f.write(
            "    FROM tmp_gnr_correccion t\n"
        )

        f.write(
            '    LEFT JOIN process."gnrMain" g\n'
        )

        f.write(
            "        ON g.id = t.id\n"
        )

        f.write(
            "    WHERE g.id IS NULL;\n\n"
        )


        f.write(
            "    IF v_errores > 0 THEN\n"
        )

        f.write(
            "        RAISE EXCEPTION\n"
        )

        f.write(
            "            'ABORTADO: existen % IDs que ya no están en gnrMain.',\n"
        )

        f.write(
            "            v_errores;\n"
        )

        f.write(
            "    END IF;\n\n"
        )


        # ---------------------------------------------------------------------
        # nameTag y dateIn.
        # ---------------------------------------------------------------------

        f.write(
            "    SELECT COUNT(*)\n"
        )

        f.write(
            "    INTO v_errores\n"
        )

        f.write(
            "    FROM tmp_gnr_correccion t\n"
        )

        f.write(
            '    JOIN process."gnrMain" g\n'
        )

        f.write(
            "        ON g.id = t.id\n"
        )

        f.write(
            "    WHERE g.\"nameTag\" IS DISTINCT FROM t.codigo\n"
        )

        f.write(
            "       OR g.\"dateIn\"::date IS DISTINCT FROM t.dia_operacional;\n\n"
        )


        f.write(
            "    IF v_errores > 0 THEN\n"
        )

        f.write(
            "        RAISE EXCEPTION\n"
        )

        f.write(
            "            'ABORTADO: % filas cambiaron de tag o fecha lógica.',\n"
        )

        f.write(
            "            v_errores;\n"
        )

        f.write(
            "    END IF;\n\n"
        )


        # ---------------------------------------------------------------------
        # Verificar que VALUE continúa igual.
        #
        # Se utiliza tolerancia relativa muy pequeña porque PostgreSQL almacena
        # double precision y el CSV puede haber serializado decimales.
        # ---------------------------------------------------------------------

        f.write(
            "    SELECT COUNT(*)\n"
        )

        f.write(
            "    INTO v_errores\n"
        )

        f.write(
            "    FROM tmp_gnr_correccion t\n"
        )

        f.write(
            '    JOIN process."gnrMain" g\n'
        )

        f.write(
            "        ON g.id = t.id\n"
        )

        f.write(
            "    WHERE\n"
        )

        f.write(
            "        (g.value IS NULL) <> (t.old_value IS NULL)\n"
        )

        f.write(
            "        OR\n"
        )

        f.write(
            "        (\n"
        )

        f.write(
            "            g.value IS NOT NULL\n"
        )

        f.write(
            "            AND t.old_value IS NOT NULL\n"
        )

        f.write(
            "            AND ABS(g.value - t.old_value)\n"
        )

        f.write(
            "                > GREATEST(1e-7, ABS(t.old_value) * 1e-9)\n"
        )

        f.write(
            "        );\n\n"
        )


        f.write(
            "    IF v_errores > 0 THEN\n"
        )

        f.write(
            "        RAISE EXCEPTION\n"
        )

        f.write(
            "            'ABORTADO: % valores VALUE cambiaron desde la auditoría.',\n"
        )

        f.write(
            "            v_errores;\n"
        )

        f.write(
            "    END IF;\n\n"
        )


        # ---------------------------------------------------------------------
        # Verificar ACCUMULATED.
        # ---------------------------------------------------------------------

        f.write(
            "    SELECT COUNT(*)\n"
        )

        f.write(
            "    INTO v_errores\n"
        )

        f.write(
            "    FROM tmp_gnr_correccion t\n"
        )

        f.write(
            '    JOIN process."gnrMain" g\n'
        )

        f.write(
            "        ON g.id = t.id\n"
        )

        f.write(
            "    WHERE\n"
        )

        f.write(
            "        (g.accumulated IS NULL) <> (t.old_accumulated IS NULL)\n"
        )

        f.write(
            "        OR\n"
        )

        f.write(
            "        (\n"
        )

        f.write(
            "            g.accumulated IS NOT NULL\n"
        )

        f.write(
            "            AND t.old_accumulated IS NOT NULL\n"
        )

        f.write(
            "            AND ABS(g.accumulated - t.old_accumulated)\n"
        )

        f.write(
            "                > GREATEST(1e-7, ABS(t.old_accumulated) * 1e-9)\n"
        )

        f.write(
            "        );\n\n"
        )


        f.write(
            "    IF v_errores > 0 THEN\n"
        )

        f.write(
            "        RAISE EXCEPTION\n"
        )

        f.write(
            "            'ABORTADO: % valores ACCUMULATED cambiaron desde la auditoría.',\n"
        )

        f.write(
            "            v_errores;\n"
        )

        f.write(
            "    END IF;\n\n"
        )


        f.write(
            "END $$;\n\n"
        )


        # =====================================================================
        # PREVIEW ANTES DEL UPDATE
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 4. MUESTREO ANTES DEL UPDATE\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "SELECT\n"
        )

        f.write(
            "    t.dia_operacional,\n"
        )

        f.write(
            "    t.equipo,\n"
        )

        f.write(
            "    t.codigo,\n"
        )

        f.write(
            "    t.estrategia,\n"
        )

        f.write(
            "    t.id,\n"
        )

        f.write(
            "    g.value AS value_actual,\n"
        )

        f.write(
            "    t.new_value AS value_propuesto,\n"
        )

        f.write(
            "    g.accumulated AS accumulated_actual,\n"
        )

        f.write(
            "    t.new_accumulated AS accumulated_propuesto\n"
        )

        f.write(
            "FROM tmp_gnr_correccion t\n"
        )

        f.write(
            'JOIN process."gnrMain" g\n'
        )

        f.write(
            "    ON g.id = t.id\n"
        )

        f.write(
            "WHERE\n"
        )

        f.write(
            "       t.dia_operacional BETWEEN DATE '2026-07-28' AND DATE '2026-08-05'\n"
        )

        f.write(
            "    OR t.dia_operacional = DATE '2026-01-02'\n"
        )

        f.write(
            "ORDER BY t.dia_operacional, t.equipo;\n\n"
        )


        # =====================================================================
        # UPDATE
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 5. UPDATE SIMULADO\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            'UPDATE process."gnrMain" AS g\n'
        )

        f.write(
            "SET\n"
        )

        f.write(
            "    value       = t.new_value,\n"
        )

        f.write(
            "    accumulated = t.new_accumulated\n"
        )

        f.write(
            "FROM tmp_gnr_correccion AS t\n"
        )

        f.write(
            "WHERE g.id = t.id;\n\n"
        )


        # =====================================================================
        # VALIDACIÓN POST UPDATE
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 6. VALIDACIÓN POST UPDATE\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "SELECT\n"
        )

        f.write(
            "    t.estrategia,\n"
        )

        f.write(
            "    COUNT(*) AS filas_esperadas,\n"
        )

        f.write(
            "    COUNT(*) FILTER\n"
        )

        f.write(
            "    (\n"
        )

        f.write(
            "        WHERE\n"
        )

        f.write(
            "            ABS(g.value - t.new_value)\n"
        )

        f.write(
            "                <= GREATEST(1e-7, ABS(t.new_value) * 1e-9)\n"
        )

        f.write(
            "            AND\n"
        )

        f.write(
            "            ABS(g.accumulated - t.new_accumulated)\n"
        )

        f.write(
            "                <= GREATEST(1e-7, ABS(t.new_accumulated) * 1e-9)\n"
        )

        f.write(
            "    ) AS filas_correctas\n"
        )

        f.write(
            "FROM tmp_gnr_correccion t\n"
        )

        f.write(
            'JOIN process."gnrMain" g\n'
        )

        f.write(
            "    ON g.id = t.id\n"
        )

        f.write(
            "GROUP BY t.estrategia\n"
        )

        f.write(
            "ORDER BY t.estrategia;\n\n"
        )


        # ---------------------------------------------------------------------
        # Mostrar cualquier discrepancia.
        # ---------------------------------------------------------------------

        f.write(
            "SELECT\n"
        )

        f.write(
            "    t.*,\n"
        )

        f.write(
            "    g.value AS value_db_despues,\n"
        )

        f.write(
            "    g.accumulated AS accumulated_db_despues\n"
        )

        f.write(
            "FROM tmp_gnr_correccion t\n"
        )

        f.write(
            'JOIN process."gnrMain" g\n'
        )

        f.write(
            "    ON g.id = t.id\n"
        )

        f.write(
            "WHERE\n"
        )

        f.write(
            "       ABS(g.value - t.new_value)\n"
        )

        f.write(
            "           > GREATEST(1e-7, ABS(t.new_value) * 1e-9)\n"
        )

        f.write(
            "    OR ABS(g.accumulated - t.new_accumulated)\n"
        )

        f.write(
            "           > GREATEST(1e-7, ABS(t.new_accumulated) * 1e-9)\n"
        )

        f.write(
            "ORDER BY t.dia_operacional, t.equipo;\n\n"
        )


        # =====================================================================
        # MUESTREO ESPECÍFICO DE LA TRANSICIÓN HYPET
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 7. VALIDACIÓN VISUAL DE LA TRANSICIÓN HYPET\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "SELECT\n"
        )

        f.write(
            "    id,\n"
        )

        f.write(
            '    "nameMtr",\n'
        )

        f.write(
            '    "nameTag",\n'
        )

        f.write(
            "    value,\n"
        )

        f.write(
            "    accumulated,\n"
        )

        f.write(
            '    "date",\n'
        )

        f.write(
            '    "dateIn"\n'
        )

        f.write(
            'FROM process."gnrMain"\n'
        )

        f.write(
            'WHERE "nameTag" IN (\'hyp400_3\', \'hyp500_2\')\n'
        )

        f.write(
            '  AND "dateIn" >= TIMESTAMP \'2026-07-29 00:00:00\'\n'
        )

        f.write(
            '  AND "dateIn" <  TIMESTAMP \'2026-08-06 00:00:00\'\n'
        )

        f.write(
            'ORDER BY "dateIn", "nameTag", id;\n\n'
        )


        # =====================================================================
        # ROLLBACK OBLIGATORIO
        # =====================================================================

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- 8. PRIMERA EJECUCIÓN = ROLLBACK\n"
        )

        f.write(
            "-- ============================================================================\n\n"
        )


        f.write(
            "ROLLBACK;\n"
        )


        f.write(
            "\n"
        )

        f.write(
            "-- ============================================================================\n"
        )

        f.write(
            "-- FIN DEL PREVIEW\n"
        )

        f.write(
            "-- PostgreSQL queda exactamente como estaba antes de BEGIN.\n"
        )

        f.write(
            "-- ============================================================================\n"
        )


# =============================================================================
# IMPRESIÓN DE RESUMEN EN CONSOLA
# =============================================================================

def imprimir_resumen(
    archivo_entrada,
    correcciones,
    contador_omitidas
):
    """
    Presenta un resumen legible antes de que el usuario abra los archivos.
    """

    print()
    print("=" * 90)

    print(
        "GENERADOR DE CORRECCIÓN gnrMain"
    )

    print("=" * 90)


    print()
    print(
        f"Entrada : {archivo_entrada}"
    )


    print()
    print(
        "REGLAS ACTIVAS"
    )

    print(
        "  Hypet 400-3 / 500-2 : "
        f"{HYPET_DESDE} -> {HYPET_HASTA} | Clickie"
    )

    print(
        "  CCM2/CCM3/KHS8/BLM10: "
        f"{ESCALA_X01_DESDE} -> {ESCALA_X01_HASTA} | x0.1"
    )


    print()
    print(
        f"Correcciones generadas : {len(correcciones):,}"
    )


    por_estrategia = Counter(
        r["estrategia"]
        for r in correcciones
    )


    por_equipo = Counter(
        r["equipo"]
        for r in correcciones
    )


    print()
    print(
        "POR ESTRATEGIA"
    )


    for estrategia, cantidad in sorted(
        por_estrategia.items()
    ):

        print(
            f"  {estrategia:<28} "
            f"{cantidad:>6,}"
        )


    print()
    print(
        "POR EQUIPO"
    )


    for equipo, cantidad in sorted(
        por_equipo.items()
    ):

        print(
            f"  {equipo:<20} "
            f"{cantidad:>6,}"
        )


    print()
    print(
        "OMISIONES PRINCIPALES"
    )


    for motivo, cantidad in contador_omitidas.most_common():

        print(
            f"  {motivo:<34} "
            f"{cantidad:>6,}"
        )


    print()
    print("=" * 90)

    print(
        "ARCHIVOS GENERADOS"
    )

    print("=" * 90)


    print(
        f"Detalle : {ARCHIVO_DETALLE}"
    )

    print(
        f"Resumen : {ARCHIVO_RESUMEN}"
    )

    print(
        f"SQL     : {ARCHIVO_SQL}"
    )


    print()
    print("=" * 90)

    print(
        "NO SE MODIFICÓ POSTGRESQL"
    )

    print("=" * 90)


    print(
        "El SQL generado termina en ROLLBACK."
    )

    print(
        "Ejecuta primero esa versión en gnrProDb01 y revisa sus resultados."
    )


# =============================================================================
# MAIN
# =============================================================================

def main():
    """
    Flujo principal.
    """

    archivo_entrada = (
        buscar_archivo_entrada()
    )


    filas = cargar_comparacion(
        archivo_entrada
    )


    (
        correcciones,
        omitidas
    ) = construir_correcciones(
        filas
    )


    if not correcciones:

        raise RuntimeError(
            "No se generó ninguna corrección."
        )


    exportar_detalle(
        correcciones
    )


    (
        _,
        contador_omitidas
    ) = exportar_resumen(
        correcciones,
        omitidas
    )


    generar_sql(
        correcciones
    )


    imprimir_resumen(
        archivo_entrada,
        correcciones,
        contador_omitidas
    )


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":

    main()
