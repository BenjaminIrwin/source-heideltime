from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Optional

from date_calculator import get_week_of_date
from heideltime_loader import NormalizationManager, RePatternManager

if TYPE_CHECKING:
    from heideltime_engine import Timex


def get_last_mentioned_x(
    linear_dates: List["Timex"],
    index: int,
    x: str,
    normalizations: NormalizationManager,
) -> str:
    j = index - 1
    while j >= 0:
        timex = linear_dates[j]
        if timex.begin == linear_dates[index].begin:
            j -= 1
            continue
        value = timex.value
        if "funcDate" in value:
            j -= 1
            continue

        if x == "century":
            if re.match(r"^[0-9][0-9].*", value):
                return value[:2]
            if re.match(r"^BC[0-9][0-9].*", value):
                return value[:4]
        elif x == "decade":
            if re.match(r"^[0-9][0-9][0-9].*", value):
                return value[:3]
            if re.match(r"^BC[0-9][0-9][0-9].*", value):
                return value[:5]
        elif x == "year":
            if re.match(r"^[0-9][0-9][0-9][0-9].*", value):
                return value[:4]
            if re.match(r"^BC[0-9][0-9][0-9][0-9].*", value):
                return value[:6]
        elif x == "dateYear":
            if re.match(r"^[0-9][0-9][0-9][0-9].*", value):
                return value
            if re.match(r"^BC[0-9][0-9][0-9][0-9].*", value):
                return value
        elif x == "month":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9].*", value):
                return value[:7]
            if re.match(r"^BC[0-9][0-9][0-9][0-9]-[0-9][0-9].*", value):
                return value[:9]
        elif x == "month-with-details":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9].*", value):
                return value
        elif x == "day":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].*", value):
                return value[:10]
        elif x == "week":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].*", value):
                return f"{value[:4]}-W{get_week_of_date(value[:10])}"
            if re.match(r"^[0-9][0-9][0-9][0-9]-W[0-9][0-9].*", value):
                return value[:8]
        elif x == "quarter":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9].*", value):
                month = value[5:7]
                quarter = normalizations.get_from_norm_month_in_quarter(month) or "1"
                return f"{value[:4]}-Q{quarter}"
            if re.match(r"^[0-9][0-9][0-9][0-9]-Q[1234].*", value):
                return value[:7]
        elif x == "dateQuarter":
            if re.match(r"^[0-9][0-9][0-9][0-9]-Q[1234].*", value):
                return value[:7]
        elif x == "season":
            if re.match(r"^[0-9][0-9][0-9][0-9]-[0-9][0-9].*", value):
                month = value[5:7]
                season = normalizations.get_from_norm_month_in_season(month)
                return f"{value[:4]}-{season}"
            if re.match(r"^[0-9][0-9][0-9][0-9]-(SP|SU|FA|WI).*", value):
                return value[:7]
        j -= 1
    return ""


def get_last_tense(timex: "Timex", repatterns: RePatternManager) -> str:
    if not timex.sentence_tokens:
        return ""

    def _match_pos(pattern_key: str, pos: str) -> bool:
        if not repatterns.contains(pattern_key):
            return False
        return re.fullmatch(repatterns.get(pattern_key), pos or "") is not None

    def _match_word(pattern_key: str, word: str) -> bool:
        if not repatterns.contains(pattern_key):
            return False
        return re.fullmatch(repatterns.get(pattern_key), word) is not None

    last_tense = ""
    for token in timex.sentence_tokens:
        if token.end < timex.begin:
            if _match_pos("tensePos4PresentFuture", token.pos):
                last_tense = "PRESENTFUTURE"
            elif _match_pos("tensePos4Past", token.pos):
                last_tense = "PAST"
            elif _match_pos("tensePos4Future", token.pos) and _match_word("tenseWord4Future", token.text):
                last_tense = "FUTURE"
            if token.text == "since":
                last_tense = "PAST"
            if token.text == "depuis":
                last_tense = "PAST"

    if last_tense == "":
        for token in timex.sentence_tokens:
            if token.begin > timex.end:
                if _match_pos("tensePos4PresentFuture", token.pos):
                    last_tense = "PRESENTFUTURE"
                elif _match_pos("tensePos4Past", token.pos):
                    last_tense = "PAST"
                elif _match_pos("tensePos4Future", token.pos) and _match_word("tenseWord4Future", token.text):
                    last_tense = "FUTURE"
                if last_tense:
                    break

    prev_pos = ""
    long_tense = ""
    if last_tense == "PRESENTFUTURE":
        for token in timex.sentence_tokens:
            if token.end < timex.begin:
                if prev_pos in {"VHZ", "VBZ", "VHP", "VBP", "VER:pres"}:
                    if token.pos in {"VVN", "VER:pper"}:
                        if token.text not in {"expected", "scheduled"}:
                            last_tense = "PAST"
                            long_tense = "PAST"
                prev_pos = token.pos
            if long_tense == "" and token.begin > timex.end:
                if prev_pos in {"VHZ", "VBZ", "VHP", "VBP", "VER:pres"}:
                    if token.pos in {"VVN", "VER:pper"}:
                        if token.text not in {"expected", "scheduled"}:
                            last_tense = "PAST"
                            long_tense = "PAST"
                prev_pos = token.pos

    if last_tense == "PAST":
        for token in timex.sentence_tokens:
            if token.end < timex.begin:
                if prev_pos == "VER:pres" and token.pos == "VER:pper":
                    if re.fullmatch(r"^prévue?s?$", token.text) or re.fullmatch(r"^envisagée?s?$", token.text):
                        last_tense = "FUTURE"
                        long_tense = "FUTURE"
                prev_pos = token.pos
            if long_tense == "" and token.begin > timex.end:
                if prev_pos == "VER:pres" and token.pos == "VER:pper":
                    if re.fullmatch(r"^prévue?s?$", token.text) or re.fullmatch(r"^envisagée?s?$", token.text):
                        last_tense = "FUTURE"
                        long_tense = "FUTURE"
                prev_pos = token.pos

    return last_tense
