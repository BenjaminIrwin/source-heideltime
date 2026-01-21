from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from heideltime_engine import Timex


def _get_easter_sunday(year: int, days: int = 0) -> str:
    k = year // 100
    m = 15 + ((3 * k + 3) // 4) - ((8 * k + 13) // 25)
    s = 2 - ((3 * k + 3) // 4)
    a = year % 19
    d = (19 * a + m) % 30
    r = (d // 29) + ((d // 28) - (d // 29) * (a // 11))
    og = 21 + d - r
    sz = 7 - (year + (year // 4) + s) % 7
    oe = 7 - (og - sz) % 7
    os = og + oe
    if os <= 31:
        date = f"{year:04d}-03-{os:02d}"
    else:
        date = f"{year:04d}-04-{os - 31:02d}"
    dt = datetime.strptime(date, "%Y-%m-%d")
    return (dt + timedelta(days=days)).strftime("%Y-%m-%d")


def _get_easter_sunday_orthodox(year: int, days: int = 0) -> str:
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = ((2 * a + 4 * b - d + 34)) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    date = f"{year:04d}-{month:02d}-{day:02d}"
    dt = datetime.strptime(date, "%Y-%m-%d")
    dt = dt + timedelta(days=days + _get_julian_difference(year))
    return dt.strftime("%Y-%m-%d")


def _get_shrove_tide_week_orthodox(year: int) -> str:
    easter = _get_easter_sunday_orthodox(year)
    dt = datetime.strptime(easter, "%Y-%m-%d")
    dt = dt - timedelta(days=49)
    week = int(dt.strftime("%W"))
    return f"{year}-W{week:02d}"


def _get_weekday_relative_to(date: str, weekday: int, number: int, count_itself: bool) -> str:
    if number == 0:
        return datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d")
    if number < 0:
        number += 1
    dt = datetime.strptime(date, "%Y-%m-%d")
    day = int(dt.strftime("%w")) + 1
    if (count_itself and number > 0) or ((not count_itself) and number <= 0):
        if day <= weekday:
            add = weekday - day
        else:
            add = weekday - day + 7
    else:
        if day < weekday:
            add = weekday - day
        else:
            add = weekday - day + 7
    add += (number - 1) * 7
    return (dt + timedelta(days=add)).strftime("%Y-%m-%d")


def _get_julian_difference(year: int) -> int:
    century = year // 100 + 1
    if century < 18:
        return 10
    if century == 18:
        return 11
    if century == 19:
        return 12
    if century in {20, 21}:
        return 13
    if century == 22:
        return 14
    return 15


def apply_holiday_processor(timexes: List["Timex"]) -> List["Timex"]:
    cmd_p = re.compile(r"((\w\w\w\w)-(\w\w)-(\w\w))\s+funcDateCalc\((\w+)\((.+)\)\)")
    year_p = re.compile(r"(\d\d\d\d)")
    date_p = re.compile(r"(\d\d\d\d)-(0[1-9]|1[012])-(0[1-9]|[12][0-9]|3[01])")

    for timex in timexes:
        if timex.timex_type not in {"DATE", "TIME"}:
            continue
        value_i = timex.value
        match = cmd_p.fullmatch(value_i)
        if not match:
            continue
        date = match.group(1)
        year = match.group(2)
        month = match.group(3)
        day = match.group(4)
        function = match.group(5)
        args = [arg.strip() for arg in match.group(6).split(",")]
        for idx, arg in enumerate(args):
            arg = arg.replace("DATE", date)
            arg = arg.replace("YEAR", year)
            arg = arg.replace("MONTH", month)
            arg = arg.replace("DAY", day)
            args[idx] = arg

        if function == "EasterSunday" and year_p.fullmatch(args[0]):
            timex.value = _get_easter_sunday(int(args[0]), int(args[1]))
        elif function == "WeekdayRelativeTo" and date_p.fullmatch(args[0]):
            timex.value = _get_weekday_relative_to(
                args[0], int(args[1]), int(args[2]), args[3].lower() == "true"
            )
        elif function == "EasterSundayOrthodox" and year_p.fullmatch(args[0]):
            timex.value = _get_easter_sunday_orthodox(int(args[0]), int(args[1]))
        elif function == "ShroveTideOrthodox" and year_p.fullmatch(args[0]):
            timex.value = _get_shrove_tide_week_orthodox(int(args[0]))
        else:
            timex.value = "XXXX-XX-XX"
    return timexes
