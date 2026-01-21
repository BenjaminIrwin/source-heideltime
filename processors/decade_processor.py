from __future__ import annotations

import re
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from heideltime_engine import Timex


def apply_decade_processor(timexes: List["Timex"]) -> List["Timex"]:
    cmd_p = re.compile(r"(\w\w\w\w)-(\w\w)-(\w\w)\s+decadeCalc\((\d+)\)")
    for timex in timexes:
        if timex.timex_type != "DATE":
            continue
        match = cmd_p.fullmatch(timex.value)
        if not match:
            continue
        year = match.group(1)
        argument = match.group(4)
        timex.value = year[:2] + argument[:1]
    return timexes
