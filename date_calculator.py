from __future__ import annotations

import re
from datetime import datetime, timedelta


def _parse_year_to_number(date: str) -> tuple[int, int]:
    if date.startswith("BC"):
        year = int(date[2:])
        return -(year - 1), len(date[2:])
    return int(date), len(date)


def _format_year_from_number(year_num: int, width: int) -> str:
    if year_num <= 0:
        year = 1 - year_num
        return f"BC{year:0{width}d}"
    return f"{year_num:0{width}d}"


def get_x_next_year(date: str, x: int) -> str:
    year_num, width = _parse_year_to_number(date)
    return _format_year_from_number(year_num + x, width)


def get_x_next_decade(date: str, x: int) -> str:
    year_num, width = _parse_year_to_number(date + "0")
    new_year = year_num + x * 10
    formatted = _format_year_from_number(new_year, width + 1)
    return formatted[:3] if formatted.startswith("BC") is False else formatted[:5]


def get_x_next_century(date: str, x: int) -> str:
    year_num, width = _parse_year_to_number(date + "00")
    old_era_bc = year_num <= 0
    new_year = year_num + x * 100
    new_era_bc = new_year <= 0
    if new_era_bc != old_era_bc:
        new_year += -100 if old_era_bc else 100
    formatted = _format_year_from_number(new_year, width + 2)
    return formatted[:2] if not formatted.startswith("BC") else formatted[:4]


def get_x_next_day(date: str, x: int) -> str:
    dt = datetime.strptime(date, "%Y-%m-%d")
    return (dt + timedelta(days=x)).strftime("%Y-%m-%d")


def get_x_next_month(date: str, x: int) -> str:
    fmt = "%Y-%m"
    dt = datetime.strptime(date, fmt)
    month = dt.month - 1 + x
    year = dt.year + month // 12
    month = month % 12 + 1
    return f"{year:04d}-{month:02d}"


def get_x_next_week(date: str, x: int) -> str:
    if "W" in date:
        match = re.match(r"(\d{4})-W(\d{1,2})", date)
        if match:
            year = int(match.group(1))
            week = int(match.group(2))
            dt = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
        else:
            dt = datetime.strptime(date, "%Y-%m-%d")
    else:
        dt = datetime.strptime(date, "%Y-%m-%d")
    dt = dt + timedelta(weeks=x)
    return dt.strftime("%Y-W%W")


def get_weekday_of_date(date: str) -> int:
    dt = datetime.strptime(date, "%Y-%m-%d")
    return int(dt.strftime("%w")) + 1


def get_week_of_date(date: str) -> int:
    dt = datetime.strptime(date, "%Y-%m-%d")
    return int(dt.strftime("%W"))
