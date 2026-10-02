import pandas as pd

from .config import TZ_CHILE
from .database import obtener_datos


def asignar_turno(fecha_hora) -> str:
    """
    Turno A: 07:00 a 14:29
    Turno B: 14:30 a 22:59
    Turno C: 23:00 a 06:59
    """
    minutos_dia = fecha_hora.hour * 60 + fecha_hora.minute

    inicio_a = 7 * 60
    inicio_b = 14 * 60 + 30
    inicio_c = 23 * 60

    if inicio_a <= minutos_dia < inicio_b:
        return "Turno A"

    if inicio_b <= minutos_dia < inicio_c:
        return "Turno B"

    return "Turno C"


def preparar_dataframe(
    nombre_variable: str,
    fecha_inicio: str,
    fecha_fin: str,
    hora_inicio: str = "00:00",
    hora_fin: str = "23:59",
) -> pd.DataFrame:
    """
    Prepara el DataFrame diagnóstico sin depender de la interfaz.
    """
    df = obtener_datos(
        nombre_variable,
        fecha_inicio,
        fecha_fin,
        hora_inicio,
        hora_fin,
    )

    if df.empty:
        return df

    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["timestamp", "valor"])

    if df.empty:
        return df

    df = df.sort_values("timestamp").reset_index(drop=True)

    df["fecha_hora_chile"] = pd.to_datetime(
        df["timestamp"],
        unit="s",
        utc=True,
    ).dt.tz_convert(TZ_CHILE)

    df["fecha"] = df["fecha_hora_chile"].dt.strftime("%Y-%m-%d")
    df["hora"] = df["fecha_hora_chile"].dt.strftime("%H:%M:%S")
    df["turno"] = df["fecha_hora_chile"].apply(asignar_turno)

    df["consumo_tramo"] = df["valor"].diff().fillna(0)
    df["consumo_tramo"] = df["consumo_tramo"].clip(lower=0)

    return df


def calcular_consumo_total_periodo(df: pd.DataFrame) -> float:
    """Calcula último acumulado menos primer acumulado."""
    if df.empty or len(df) < 2:
        return 0.0

    consumo = float(df.iloc[-1]["valor"]) - float(df.iloc[0]["valor"])
    return max(consumo, 0.0)


def calcular_turnos_por_intervalos(df: pd.DataFrame) -> pd.DataFrame:
    """Agrupa las diferencias entre registros según el turno actual."""
    columnas = ["turno", "consumo_total", "registros"]

    if df.empty:
        return pd.DataFrame(columns=columnas)

    resumen = (
        df.groupby("turno", as_index=False)
        .agg(
            consumo_total=("consumo_tramo", "sum"),
            registros=("consumo_tramo", "count"),
        )
    )

    turnos_base = pd.DataFrame({
        "turno": ["Turno A", "Turno B", "Turno C"],
        "orden": [1, 2, 3],
    })

    resumen = turnos_base.merge(resumen, on="turno", how="left")
    resumen["consumo_total"] = resumen["consumo_total"].fillna(0.0)
    resumen["registros"] = resumen["registros"].fillna(0).astype(int)

    return resumen.sort_values("orden").drop(columns="orden")[columnas]


def calcular_kpis(df: pd.DataFrame) -> dict:
    """Calcula indicadores base para diagnóstico."""
    if df.empty or len(df) < 2:
        return {
            "consumo_total_periodo": 0.0,
            "valor_inicial": None,
            "valor_final": None,
            "registros": len(df),
        }

    return {
        "consumo_total_periodo": calcular_consumo_total_periodo(df),
        "valor_inicial": float(df.iloc[0]["valor"]),
        "valor_final": float(df.iloc[-1]["valor"]),
        "registros": len(df),
    }
