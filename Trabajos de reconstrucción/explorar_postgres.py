#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Explorador interactivo de PostgreSQL para la base gnrProDb01.

Configuración actual:
    Servidor: 192.168.131.66
    Puerto:   5432
    Base:     gnrProDb01
    Usuario:  postgres

El programa abre la conexión en modo de solo lectura para reducir el riesgo
de modificar datos accidentalmente.

Dependencia:
    py -m pip install "psycopg[binary]"

Ejecución:
    py explorar_gnrProDb01.py
"""

import os
import sys
from typing import Any, Iterable, Sequence

try:
    import psycopg
    from psycopg import sql
except ImportError:
    print("\n[ERROR] Falta instalar psycopg.")
    print('Ejecuta: py -m pip install "psycopg[binary]"\n')
    sys.exit(1)


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------

DB_CONFIG = {
    "host": os.getenv("PGHOST", "192.168.131.66"),
    "port": int(os.getenv("PGPORT", "5432")),
    "dbname": os.getenv("PGDATABASE", "gnrProDb01"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
    "connect_timeout": 5,

    # Solo lectura y tiempo máximo de 30 segundos por consulta.
    "options": (
        "-c default_transaction_read_only=on "
        "-c statement_timeout=30000 "
        "-c application_name=explorador_gnrProDb01"
    ),
}

DEFAULT_SCHEMA = "process"
MAX_DISPLAY_ROWS = 200
MAX_CELL_LENGTH = 80


# ---------------------------------------------------------------------------
# UTILIDADES DE PRESENTACIÓN
# ---------------------------------------------------------------------------

def shorten(value: Any, max_length: int = MAX_CELL_LENGTH) -> str:
    """Convierte un valor a texto y limita su longitud para la consola."""
    if value is None:
        return "NULL"

    if isinstance(value, memoryview):
        return f"<binary {len(value)} bytes>"

    text = str(value).replace("\r", "\\r").replace("\n", "\\n")

    if len(text) > max_length:
        return text[: max_length - 3] + "..."

    return text


def print_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[Any]],
    truncated: bool = False,
) -> None:
    """Imprime resultados en formato de tabla."""
    rows_text = [[shorten(value) for value in row] for row in rows]

    if not rows_text:
        print("\nSin resultados.\n")
        return

    widths = [len(str(header)) for header in headers]

    for row in rows_text:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))

    separator = "+-" + "-+-".join("-" * width for width in widths) + "-+"

    print()
    print(separator)
    print(
        "| "
        + " | ".join(
            str(header).ljust(widths[index])
            for index, header in enumerate(headers)
        )
        + " |"
    )
    print(separator)

    for row in rows_text:
        print(
            "| "
            + " | ".join(
                value.ljust(widths[index])
                for index, value in enumerate(row)
            )
            + " |"
        )

    print(separator)
    print(f"{len(rows_text)} fila(s) mostrada(s).")

    if truncated:
        print(
            f"Resultado limitado a las primeras {MAX_DISPLAY_ROWS} filas."
        )

    print()


def execute_and_print(
    conn: psycopg.Connection,
    query: Any,
    params: Sequence[Any] | None = None,
    max_rows: int = MAX_DISPLAY_ROWS,
) -> None:
    """Ejecuta una consulta y muestra una cantidad limitada de registros."""
    if params is None:
        params = ()

    with conn.cursor() as cur:
        cur.execute(query, params)

        if cur.description is None:
            print("\nLa consulta no devolvió columnas.\n")
            return

        headers = [column.name for column in cur.description]
        rows = cur.fetchmany(max_rows + 1)

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]

    print_table(headers, rows, truncated=truncated)


def read_int(
    prompt: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Lee un entero validado desde consola."""
    value = input(prompt).strip()

    if not value:
        return default

    try:
        number = int(value)
    except ValueError:
        print(f"\nValor inválido. Se utilizará {default}.\n")
        return default

    return max(minimum, min(number, maximum))


# ---------------------------------------------------------------------------
# CONSULTAS DEL EXPLORADOR
# ---------------------------------------------------------------------------

def show_connection_info(conn: psycopg.Connection) -> None:
    query = """
        SELECT
            current_database() AS base_datos,
            current_user AS usuario,
            inet_server_addr()::TEXT AS ip_servidor,
            inet_server_port() AS puerto,
            current_schema() AS esquema_actual,
            pg_size_pretty(
                pg_database_size(current_database())
            ) AS tamano_bd,
            version() AS version_postgresql;
    """
    execute_and_print(conn, query)


def list_schemas(conn: psycopg.Connection) -> None:
    query = """
        SELECT
            schema_name AS esquema,
            schema_owner AS propietario
        FROM information_schema.schemata
        ORDER BY schema_name;
    """
    execute_and_print(conn, query)


def list_tables_and_views(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    query = """
        SELECT
            table_schema AS esquema,
            table_name AS objeto,
            table_type AS tipo
        FROM information_schema.tables
        WHERE table_schema = %s

        UNION ALL

        SELECT
            table_schema AS esquema,
            table_name AS objeto,
            'VIEW' AS tipo
        FROM information_schema.views
        WHERE table_schema = %s

        ORDER BY objeto;
    """

    execute_and_print(conn, query, (schema, schema))


def show_columns(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    table = input("Tabla o vista: ").strip()

    if not table:
        print("\nDebes indicar una tabla o vista.\n")
        return

    query = """
        SELECT
            ordinal_position AS posicion,
            column_name AS columna,
            data_type AS tipo,
            udt_name AS tipo_interno,
            character_maximum_length AS largo_maximo,
            numeric_precision AS precision,
            numeric_scale AS escala,
            is_nullable AS permite_null,
            column_default AS valor_por_defecto
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """

    execute_and_print(conn, query, (schema, table))


def sample_rows(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    table = input("Tabla o vista: ").strip()

    if not table:
        print("\nDebes indicar una tabla o vista.\n")
        return

    limit = read_int(
        "Cantidad de filas [20, máximo 200]: ",
        default=20,
        minimum=1,
        maximum=200,
    )

    query = sql.SQL("SELECT * FROM {}.{} LIMIT %s").format(
        sql.Identifier(schema),
        sql.Identifier(table),
    )

    execute_and_print(conn, query, (limit,), max_rows=limit)


def show_table_sizes(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    query = """
        SELECT
            s.schemaname AS esquema,
            s.relname AS tabla,
            s.n_live_tup AS filas_estimadas,
            pg_size_pretty(
                pg_relation_size(
                    quote_ident(s.schemaname) || '.' ||
                    quote_ident(s.relname)
                )
            ) AS datos,
            pg_size_pretty(
                pg_indexes_size(
                    quote_ident(s.schemaname) || '.' ||
                    quote_ident(s.relname)
                )
            ) AS indices,
            pg_size_pretty(
                pg_total_relation_size(
                    quote_ident(s.schemaname) || '.' ||
                    quote_ident(s.relname)
                )
            ) AS total
        FROM pg_stat_user_tables s
        WHERE s.schemaname = %s
        ORDER BY pg_total_relation_size(
            quote_ident(s.schemaname) || '.' ||
            quote_ident(s.relname)
        ) DESC;
    """

    execute_and_print(conn, query, (schema,))


def show_primary_keys(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    query = """
        SELECT
            tc.table_schema AS esquema,
            tc.table_name AS tabla,
            tc.constraint_name AS restriccion,
            string_agg(
                kcu.column_name,
                ', ' ORDER BY kcu.ordinal_position
            ) AS columnas
        FROM information_schema.table_constraints tc
        INNER JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
           AND tc.table_name = kcu.table_name
        WHERE tc.constraint_type = 'PRIMARY KEY'
          AND tc.table_schema = %s
        GROUP BY
            tc.table_schema,
            tc.table_name,
            tc.constraint_name
        ORDER BY tc.table_name;
    """

    execute_and_print(conn, query, (schema,))


def show_foreign_keys(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    query = """
        SELECT
            tc.table_schema AS esquema,
            tc.table_name AS tabla,
            kcu.column_name AS columna,
            ccu.table_schema AS esquema_referenciado,
            ccu.table_name AS tabla_referenciada,
            ccu.column_name AS columna_referenciada,
            tc.constraint_name AS restriccion
        FROM information_schema.table_constraints tc
        INNER JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
           AND tc.table_schema = kcu.table_schema
        INNER JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name = tc.constraint_name
           AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = %s
        ORDER BY tc.table_name, kcu.ordinal_position;
    """

    execute_and_print(conn, query, (schema,))


def count_rows(conn: psycopg.Connection) -> None:
    schema = input(
        f"Esquema [{DEFAULT_SCHEMA}]: "
    ).strip() or DEFAULT_SCHEMA

    table = input("Tabla: ").strip()

    if not table:
        print("\nDebes indicar una tabla.\n")
        return

    print(
        "\nAdvertencia: COUNT(*) puede demorar en tablas muy grandes."
    )
    confirm = input("¿Continuar? [s/N]: ").strip().lower()

    if confirm not in ("s", "si", "sí"):
        print("\nOperación cancelada.\n")
        return

    query = sql.SQL(
        "SELECT COUNT(*) AS total_filas FROM {}.{}"
    ).format(
        sql.Identifier(schema),
        sql.Identifier(table),
    )

    execute_and_print(conn, query)


def show_recent_gnr_main(conn: psycopg.Connection) -> None:
    limit = read_int(
        "Cantidad de filas recientes [20, máximo 200]: ",
        default=20,
        minimum=1,
        maximum=200,
    )

    query = """
        SELECT
            id,
            "nameMtr",
            "nameTag",
            "idArea",
            value,
            path,
            date,
            category,
            "dateIn"
        FROM process."gnrMain"
        ORDER BY "dateIn" DESC NULLS LAST
        LIMIT %s;
    """

    execute_and_print(conn, query, (limit,), max_rows=limit)


def show_recent_production(conn: psycopg.Connection) -> None:
    limit = read_int(
        "Cantidad de filas recientes [20, máximo 200]: ",
        default=20,
        minimum=1,
        maximum=200,
    )

    query = """
        SELECT
            id,
            date,
            "shiftDefinition",
            "manufacturingLine",
            pinta,
            "ctdConfKg",
            "materialDescription",
            quarter
        FROM process."enrSapProd"
        ORDER BY date DESC NULLS LAST
        LIMIT %s;
    """

    execute_and_print(conn, query, (limit,), max_rows=limit)


def run_custom_select(conn: psycopg.Connection) -> None:
    print("\nConsulta personalizada de solo lectura.")
    print("Termina la consulta escribiendo una línea que contenga solo: FIN")
    print("Se permiten consultas que comiencen con SELECT, WITH o EXPLAIN.\n")

    lines: list[str] = []

    while True:
        line = input("SQL> ")

        if line.strip().upper() == "FIN":
            break

        lines.append(line)

    query_text = "\n".join(lines).strip()

    if not query_text:
        print("\nNo se ingresó ninguna consulta.\n")
        return

    normalized = query_text.lstrip().upper()

    allowed_prefixes = ("SELECT", "WITH", "EXPLAIN")

    if not normalized.startswith(allowed_prefixes):
        print(
            "\n[DENEGADO] Solo se permiten SELECT, WITH o EXPLAIN.\n"
        )
        return

    # Evita enviar varias instrucciones en una sola ejecución.
    if ";" in query_text.rstrip(";"):
        print(
            "\n[DENEGADO] Solo se permite una instrucción SQL por ejecución.\n"
        )
        return

    execute_and_print(conn, query_text)


# ---------------------------------------------------------------------------
# MENÚ PRINCIPAL
# ---------------------------------------------------------------------------

def print_menu() -> None:
    print("Opciones:")
    print("  1. Ver información de conexión")
    print("  2. Listar esquemas")
    print("  3. Listar tablas y vistas")
    print("  4. Ver columnas de una tabla")
    print("  5. Ver muestra de registros")
    print("  6. Ver tamaños y filas estimadas")
    print("  7. Ver llaves primarias")
    print("  8. Ver llaves foráneas")
    print("  9. Contar filas exactas de una tabla")
    print(' 10. Ver últimos registros de process."gnrMain"')
    print(' 11. Ver últimos registros de process."enrSapProd"')
    print(" 12. Ejecutar SELECT personalizado")
    print("  0. Salir")


def main() -> None:
    print("=" * 72)
    print("EXPLORADOR POSTGRESQL - gnrProDb01 - SOLO LECTURA")
    print("=" * 72)
    print(
        f"Servidor: {DB_CONFIG['host']}:{DB_CONFIG['port']} | "
        f"Base: {DB_CONFIG['dbname']} | "
        f"Usuario: {DB_CONFIG['user']}"
    )

    actions = {
        "1": show_connection_info,
        "2": list_schemas,
        "3": list_tables_and_views,
        "4": show_columns,
        "5": sample_rows,
        "6": show_table_sizes,
        "7": show_primary_keys,
        "8": show_foreign_keys,
        "9": count_rows,
        "10": show_recent_gnr_main,
        "11": show_recent_production,
        "12": run_custom_select,
    }

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            print("\n[OK] Conexión establecida correctamente.")
            print("[OK] Sesión configurada en modo de solo lectura.\n")

            while True:
                print_menu()
                option = input("\nSelecciona una opción: ").strip()

                if option == "0":
                    print("\nConexión cerrada.")
                    break

                action = actions.get(option)

                if action is None:
                    print("\nOpción no válida.\n")
                    continue

                try:
                    action(conn)

                except psycopg.errors.QueryCanceled:
                    conn.rollback()
                    print(
                        "\n[ERROR] La consulta superó el límite de "
                        "30 segundos y fue cancelada.\n"
                    )

                except psycopg.errors.UndefinedTable as error:
                    conn.rollback()
                    print("\n[ERROR] La tabla o vista no existe.")
                    print(f"Detalle: {error}\n")

                except psycopg.errors.InsufficientPrivilege as error:
                    conn.rollback()
                    print("\n[ERROR] El usuario no tiene permisos suficientes.")
                    print(f"Detalle: {error}\n")

                except psycopg.Error as error:
                    conn.rollback()
                    print("\n[ERROR POSTGRESQL]")
                    print(error)
                    print()

                except KeyboardInterrupt:
                    conn.rollback()
                    print("\nOperación cancelada.\n")

    except psycopg.OperationalError as error:
        print("\n[ERROR] No fue posible conectar a PostgreSQL.")
        print(error)
        print("\nValidaciones sugeridas:")
        print("1. Test-NetConnection 192.168.131.66 -Port 5432")
        print("2. Confirmar que la base sea gnrProDb01")
        print("3. Confirmar usuario y contraseña")
        print("4. Revisar pg_hba.conf si PostgreSQL rechaza el cliente")
        sys.exit(2)


if __name__ == "__main__":
    main()