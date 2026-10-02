from datetime import datetime, timedelta
from typing import Iterator, Optional

from .config import (
    DIAS_ES,
    MESES_HISTORICOS,
    OPERATIONAL_DAY_START_HOUR,
    TZ_CHILE,
)


def parsear_fecha_hora_chile(fecha: str, hora: str) -> datetime:
    """
    Convierte textos AAAA-MM-DD y HH:MM a un datetime de Chile.

    La función se mantiene fuera de la interfaz para que pueda reutilizarse
    desde consultas, pruebas o futuras ejecuciones sin Tkinter.
    """
    fecha = fecha.strip()
    hora = hora.strip()

    try:
        fecha_hora = datetime.strptime(
            f"{fecha} {hora}",
            "%Y-%m-%d %H:%M",
        )
    except ValueError as exc:
        raise ValueError(
            "Fecha u hora inválida. Usa AAAA-MM-DD y HH:MM."
        ) from exc

    return fecha_hora.replace(tzinfo=TZ_CHILE)


def validar_rango_fecha_hora(
    fecha_inicio: str,
    hora_inicio: str,
    fecha_fin: str,
    hora_fin: str,
) -> tuple[datetime, datetime]:
    """Construye y valida un rango local de fecha y hora."""
    inicio_dt = parsear_fecha_hora_chile(fecha_inicio, hora_inicio)
    fin_dt = parsear_fecha_hora_chile(fecha_fin, hora_fin)

    if inicio_dt > fin_dt:
        raise ValueError(
            "El inicio del rango no puede ser posterior al término."
        )

    return inicio_dt, fin_dt


def at_operational_hour(dt: datetime) -> datetime:
    return dt.replace(
        hour=OPERATIONAL_DAY_START_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )


def get_last_closed_cutoff(now: Optional[datetime] = None) -> datetime:
    if now is None:
        now = datetime.now(TZ_CHILE)

    cutoff_today = at_operational_hour(now)
    return cutoff_today if now >= cutoff_today else cutoff_today - timedelta(days=1)


def get_operational_date(now: Optional[datetime] = None) -> datetime:
    if now is None:
        now = datetime.now(TZ_CHILE)

    cutoff_today = at_operational_hour(now)

    if now < cutoff_today:
        now -= timedelta(days=1)

    return now.replace(hour=12, minute=0, second=0, microsecond=0)


def start_of_month_operational(dt: datetime) -> datetime:
    return datetime(
        dt.year,
        dt.month,
        1,
        OPERATIONAL_DAY_START_HOUR,
        tzinfo=TZ_CHILE,
    )


def add_months(dt: datetime, months: int) -> datetime:
    month_index = dt.month - 1 + months
    year = dt.year + month_index // 12
    month = month_index % 12 + 1

    return datetime(
        year,
        month,
        1,
        OPERATIONAL_DAY_START_HOUR,
        tzinfo=TZ_CHILE,
    )


def start_of_iso_week_operational(dt: datetime) -> datetime:
    monday = dt - timedelta(days=dt.weekday())
    return monday.replace(
        hour=OPERATIONAL_DAY_START_HOUR,
        minute=0,
        second=0,
        microsecond=0,
    )


def format_week_period(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def get_operational_month_window(
    now: Optional[datetime] = None,
    months_back: int = 0,
) -> tuple[datetime, datetime]:
    """
    Retorna el rango operacional de un mes como [inicio, fin).

    months_back = 0:
        mes actual hasta el último corte cerrado.

    months_back >= 1:
        mes histórico completo, desde el día 1 a las 07:00 hasta
        el día 1 del mes siguiente a las 07:00.
    """
    if months_back < 0:
        raise ValueError("months_back no puede ser negativo.")

    if now is None:
        now = datetime.now(TZ_CHILE)

    operational_date = get_operational_date(now)
    current_month_start = start_of_month_operational(operational_date)
    target_month_start = add_months(current_month_start, -months_back)
    target_month_end = add_months(target_month_start, 1)

    if months_back == 0:
        return target_month_start, min(
            get_last_closed_cutoff(now),
            target_month_end,
        )

    return target_month_start, target_month_end


def build_agua_ranges(now: Optional[datetime] = None) -> dict:
    """
    Construye los bloques operacionales usando intervalos [from, to).

    Incluye:
    - mes actual;
    - mes anterior;
    - hasta MESES_HISTORICOS meses cerrados hacia atrás;
    - semana actual y anterior;
    - día anterior y día anterior anterior.
    """
    if now is None:
        now = datetime.now(TZ_CHILE)

    last_cutoff = get_last_closed_cutoff(now)
    operational_date = get_operational_date(now)

    ranges = {}

    # Mes actual y meses históricos. Se insertan primero para conservar
    # un orden estable y facilitar la lectura desde Apps Script.
    for months_back in range(0, MESES_HISTORICOS + 1):
        inicio_mes, fin_mes = get_operational_month_window(
            now=now,
            months_back=months_back,
        )

        if months_back == 0:
            bloque = "mes_actual"
        elif months_back == 1:
            bloque = "mes_anterior"
        else:
            bloque = f"mes_anterior_{months_back}"

        ranges[bloque] = {
            "periodo": inicio_mes.strftime("%Y-%m"),
            "from": inicio_mes,
            "to": fin_mes,
        }

    semana_actual_inicio = start_of_iso_week_operational(operational_date)
    semana_anterior_inicio = semana_actual_inicio - timedelta(days=7)

    dia_anterior_inicio = last_cutoff - timedelta(days=1)
    dia_anterior_anterior_inicio = last_cutoff - timedelta(days=2)

    ranges.update({
        "semana_actual": {
            "periodo": format_week_period(semana_actual_inicio),
            "from": semana_actual_inicio,
            "to": last_cutoff,
        },
        "semana_anterior": {
            "periodo": format_week_period(semana_anterior_inicio),
            "from": semana_anterior_inicio,
            "to": semana_actual_inicio,
        },
        "dia_anterior": {
            "periodo": dia_anterior_inicio.strftime("%Y-%m-%d"),
            "from": dia_anterior_inicio,
            "to": last_cutoff,
        },
        "dia_anterior_anterior": {
            "periodo": dia_anterior_anterior_inicio.strftime("%Y-%m-%d"),
            "from": dia_anterior_anterior_inicio,
            "to": dia_anterior_inicio,
        },
    })

    return ranges


def start_of_year_operational(dt: datetime) -> datetime:
    return datetime(
        dt.year,
        1,
        1,
        OPERATIONAL_DAY_START_HOUR,
        tzinfo=TZ_CHILE,
    )


def iter_month_starts(
    start_dt: datetime,
    end_dt: datetime,
) -> Iterator[tuple[datetime, datetime]]:
    current = start_of_month_operational(start_dt)

    while current < end_dt:
        next_month = add_months(current, 1)
        yield current, min(next_month, end_dt)
        current = next_month


def iter_week_starts(
    start_dt: datetime,
    end_dt: datetime,
) -> Iterator[tuple[datetime, datetime, datetime]]:
    current = start_of_iso_week_operational(start_dt)

    while current < end_dt:
        next_week = current + timedelta(days=7)
        yield max(current, start_dt), min(next_week, end_dt), current
        current = next_week


def iter_day_starts(
    start_dt: datetime,
    end_dt: datetime,
) -> Iterator[tuple[datetime, datetime]]:
    current = at_operational_hour(start_dt)

    if current < start_dt:
        current += timedelta(days=1)

    if (
        start_dt.hour == OPERATIONAL_DAY_START_HOUR
        and start_dt.minute == 0
        and start_dt.second == 0
    ):
        current = start_dt

    while current < end_dt:
        next_day = current + timedelta(days=1)
        yield current, min(next_day, end_dt)
        current = next_day


def format_day_label(dt: datetime) -> str:
    return f"{DIAS_ES.get(dt.weekday(), '')} {dt.day:02d}"
