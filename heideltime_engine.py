from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import List, Match, Optional, Sequence

from context_analyzer import get_last_mentioned_x, get_last_tense
from date_calculator import (
    get_week_of_date,
    get_weekday_of_date,
    get_x_next_century,
    get_x_next_day,
    get_x_next_decade,
    get_x_next_month,
    get_x_next_week,
    get_x_next_year,
)
from heideltime_loader import HeidelTimeLoader, NormalizationManager, RePatternManager, Rule
from comprehend_preprocessor import Sentence, Token, preprocess
from processors.decade_processor import apply_decade_processor
from processors.holiday_processor import apply_holiday_processor


@dataclass
class Timex:
    timex_type: str
    begin: int
    end: int
    text: str
    value: str
    quant: str
    freq: str
    mod: str
    empty_value: str
    rule: str
    timex_id: str
    found_by_rule: str
    first_token_id: Optional[int] = None
    all_token_ids: str = ""
    sentence_begin: Optional[int] = None
    sentence_end: Optional[int] = None
    sentence_tokens: Optional[List[Token]] = None


def apply_rule_functions(
    tonormalize: str,
    match: Match[str],
    normalizations: NormalizationManager,
    language_name: str,
) -> Optional[str]:
    pa_norm = re.compile(r"%([A-Za-z0-9]+?)\(group\(([0-9]+)\)\)")
    pa_group = re.compile(r"group\(([0-9]+)\)")
    pa_substring = re.compile(r"%SUBSTRING%\((.*?),([0-9]+),([0-9]+)\)")
    pa_lowercase = re.compile(r"%LOWERCASE%\((.*?)\)")
    pa_uppercase = re.compile(r"%UPPERCASE%\((.*?)\)")
    pa_sum = re.compile(r"%SUM%\((.*?),(.*?)\)")
    pa_norm_no_group = re.compile(r"%([A-Za-z0-9]+?)\((.*?)\)")
    pa_chinese = re.compile(r"%CHINESENUMBERS%\((.*?)\)")

    def _replace_norm_group(value: str) -> Optional[str]:
        for mr in list(pa_norm.finditer(value)):
            group_num = int(mr.group(2))
            group_value = match.group(group_num)
            if group_value is None:
                value = value.replace(mr.group(), "")
                continue
            part_to_replace = re.sub(r"[\n\s]+", " ", group_value)
            norm_map = normalizations.get_from_hm_all_normalization(mr.group(1))
            if not norm_map.contains_key(part_to_replace):
                if "Temponym" in mr.group(1):
                    return None
            else:
                replacement = norm_map.get(part_to_replace) or ""
                value = value.replace(mr.group(), replacement)
        return value

    def _replace_group(value: str) -> str:
        for mr in list(pa_group.finditer(value)):
            group_num = int(mr.group(1))
            group_value = match.group(group_num) or ""
            value = value.replace(mr.group(), group_value)
        return value

    def _replace_substring(value: str) -> str:
        for mr in list(pa_substring.finditer(value)):
            start = int(mr.group(2))
            end = int(mr.group(3))
            substring = mr.group(1)[start:end]
            value = value.replace(mr.group(), substring)
        return value

    def _replace_case(value: str) -> str:
        if language_name == "arabic":
            return value
        for mr in list(pa_lowercase.finditer(value)):
            value = value.replace(mr.group(), mr.group(1).lower())
        for mr in list(pa_uppercase.finditer(value)):
            value = value.replace(mr.group(), mr.group(1).upper())
        return value

    def _replace_sum(value: str) -> str:
        for mr in list(pa_sum.finditer(value)):
            try:
                new_value = int(mr.group(1)) + int(mr.group(2))
            except ValueError:
                continue
            value = value.replace(mr.group(), str(new_value))
        return value

    def _replace_norm_no_group(value: str) -> str:
        for mr in list(pa_norm_no_group.finditer(value)):
            norm_map = normalizations.get_from_hm_all_normalization(mr.group(1))
            replacement = norm_map.get(mr.group(2)) or ""
            value = value.replace(mr.group(), replacement)
        return value

    def _replace_chinese_numbers(value: str) -> str:
        for mr in list(pa_chinese.finditer(value)):
            map_digits = {
                "零": "0",
                "０": "0",
                "0": "0",
                "一": "1",
                "１": "1",
                "1": "1",
                "二": "2",
                "２": "2",
                "2": "2",
                "三": "3",
                "３": "3",
                "3": "3",
                "四": "4",
                "４": "4",
                "4": "4",
                "五": "5",
                "５": "5",
                "5": "5",
                "六": "6",
                "６": "6",
                "6": "6",
                "七": "7",
                "７": "7",
                "7": "7",
                "八": "8",
                "８": "8",
                "8": "8",
                "九": "9",
                "９": "9",
                "9": "9",
            }
            out = []
            for char in mr.group(1):
                out.append(map_digits.get(char, char))
            value = value.replace(mr.group(), "".join(out))
        return value

    while ("%" in tonormalize) or ("group" in tonormalize):
        changed = False
        result = _replace_norm_group(tonormalize)
        if result is None:
            return None
        if result != tonormalize:
            changed = True
            tonormalize = result

        replaced = _replace_group(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        replaced = _replace_substring(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        replaced = _replace_case(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        replaced = _replace_sum(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        replaced = _replace_norm_no_group(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        replaced = _replace_chinese_numbers(tonormalize)
        if replaced != tonormalize:
            changed = True
            tonormalize = replaced

        if not changed:
            break
    return tonormalize


def correct_duration_value(value: str) -> str:
    if re.fullmatch(r"PT[0-9]+H", value):
        match = re.match(r"PT([0-9]+)H", value)
        if match:
            hours = int(match.group(1))
            if hours % 24 == 0:
                return f"P{hours // 24}D"
    if re.fullmatch(r"PT[0-9]+M", value):
        match = re.match(r"PT([0-9]+)M", value)
        if match:
            minutes = int(match.group(1))
            if minutes % 60 == 0:
                return f"PT{minutes // 60}H"
    if re.fullmatch(r"P[0-9]+M", value):
        match = re.match(r"P([0-9]+)M", value)
        if match:
            months = int(match.group(1))
            if months % 12 == 0:
                return f"P{months // 12}Y"
    return value


def _check_infront_behind(match: Match[str], sentence: Sentence) -> bool:
    text = sentence.text
    start = match.start()
    end = match.end()
    if start > 1:
        if re.match(r"\d\.", text[start - 2:start]):
            return False
    if start > 0:
        if re.match(r"[\w\$\+]", text[start - 1:start]) and not re.match(r"\(", text[start - 1:start]):
            return False
    if end < len(text):
        if re.match(r"[°\w]", text[end:end + 1]) and not re.match(r"\)", text[end:end + 1]):
            return False
        if end + 1 < len(text) and re.match(r"[.,]\d", text[end:end + 2]):
            return False
    return True


def _check_token_boundaries(match: Match[str], sentence: Sentence) -> bool:
    text = sentence.text
    if (match.end() - match.start()) == (sentence.end - sentence.begin):
        return True
    if (
        match.start() > 0
        and text[match.start() - 1:match.start()] == " "
        and match.end() < len(text)
        and text[match.end():match.end() + 1] == " "
    ):
        return True
    begin_ok = False
    end_ok = False
    for token in sentence.tokens:
        if (match.start() + sentence.begin) == token.begin:
            begin_ok = True
        elif match.start() > 0 and text[match.start() - 1:match.start()] in {".", "/", "–", "-"}:
            begin_ok = True
        if (match.end() + sentence.begin) == token.end:
            end_ok = True
        elif match.end() < len(text) and text[match.end():match.end() + 1] in {".", "/", "–", "-"}:
            end_ok = True
        if begin_ok and end_ok:
            return True
    return False


def _get_pos_from_match_result(match: Match[str], group_number: int, sentence: Sentence) -> str:
    token_begin = sentence.begin + match.start(group_number)
    for token in sentence.tokens:
        if token.begin == token_begin:
            return token.pos
    return ""


def _check_pos_constraint(match: Match[str], sentence: Sentence, pos_constraint: str) -> bool:
    pa_constraint = re.compile(r"group\(([0-9]+)\):(.*?):")
    for mr in pa_constraint.finditer(pos_constraint):
        group_number = int(mr.group(1))
        pos_pattern = mr.group(2)
        pos_as_is = _get_pos_from_match_result(match, group_number, sentence)
        if not re.fullmatch(pos_pattern, pos_as_is):
            return False
    return True


def _apply_offset(match: Match[str], offset: str) -> Optional[tuple[int, int]]:
    pa_offset = re.compile(r"group\(([0-9]+)\)-group\(([0-9]+)\)")
    offset_match = pa_offset.search(offset)
    if not offset_match:
        return None
    start_offset = int(offset_match.group(1))
    end_offset = int(offset_match.group(2))
    return match.start(start_offset), match.end(end_offset)


class HeidelTimeEngine:
    def __init__(
        self,
        language_dir: str,
        doc_type: str = "news",
        dct: Optional[str] = None,
        resolve_with_dct: bool = True,
        find_dates: bool = True,
        find_times: bool = True,
        find_durations: bool = True,
        find_sets: bool = True,
        find_temponyms: bool = False,
        group_granularity: bool = True,
        use_pos: bool = True,
        split_on_newlines: bool = False,
    ) -> None:
        self.loader = HeidelTimeLoader(language_dir, load_temponym_resources=find_temponyms)
        self.language_dir = language_dir
        self.language_name = os.path.basename(language_dir)
        self.doc_type = doc_type
        self.dct = dct
        # If False, treat DCT as unavailable during ambiguity resolution (even if provided).
        self.resolve_with_dct = resolve_with_dct
        self.find_dates = find_dates
        self.find_times = find_times
        self.find_durations = find_durations
        self.find_sets = find_sets
        self.find_temponyms = find_temponyms
        self.group_granularity = group_granularity
        self.use_pos = use_pos
        self.split_on_newlines = split_on_newlines
        self.timex_id = 1

    def extract(
        self,
        text: str,
        sentences: Optional[List[Sentence]] = None,
    ) -> List[Timex]:
        """
        Extract temporal expressions from text.
        
        Args:
            text: Input text to process (used if sentences not provided)
            sentences: Optional pre-processed sentences with tokens and POS tags.
                      If provided, text is ignored and no Comprehend call is made.
                      Useful when NLP preprocessing is done upstream and shared
                      across multiple services.
            
        Returns:
            List of Timex objects representing temporal expressions
        """
        if sentences is None:
            sentences = preprocess(
                text,
                use_pos=self.use_pos,
                split_on_newlines=self.split_on_newlines,
            )
        timexes: List[Timex] = []
        for sentence in sentences:
            if self.find_dates:
                self._find_timexes("DATE", self.loader.rules.rules["daterules"], sentence, timexes)
            if self.find_times:
                self._find_timexes("TIME", self.loader.rules.rules["timerules"], sentence, timexes)
            if self.find_sets:
                self._find_timexes("SET", self.loader.rules.rules["setrules"], sentence, timexes)
            if self.find_durations:
                self._find_timexes("DURATION", self.loader.rules.rules["durationrules"], sentence, timexes)
            if self.find_temponyms and "temponymrules" in self.loader.rules.rules:
                self._find_timexes("TEMPONYM", self.loader.rules.rules["temponymrules"], sentence, timexes)
        timexes = delete_overlapped_preprocessing(timexes)
        dct_for_resolution = self.dct if self.resolve_with_dct else None
        timexes = specify_ambiguous_values(
            timexes,
            self.doc_type,
            dct_for_resolution,
            self.loader.normalizations,
            self.loader.repatterns,
        )
        if self.doc_type in {"narrative", "narratives"} and any(
            timex.value.startswith("BC") for timex in timexes
        ):
            timexes = disambiguate_historic_dates(timexes)
        timexes = delete_overlapped_postprocessing(timexes)
        timexes = remove_invalids(timexes)
        timexes = apply_holiday_processor(timexes)
        timexes = apply_decade_processor(timexes)
        return timexes

    def _find_timexes(
        self,
        timex_type: str,
        rules: Sequence[Rule],
        sentence: Sentence,
        timexes: List[Timex],
    ) -> None:
        # Preserve rule order as loaded from the resource files (closest to Java behavior).
        for rule in rules:
            if not self.use_pos and rule.pos_constraint:
                # Java `-pos no` cannot evaluate POS_CONSTRAINT; for parity, skip such rules.
                continue
            if rule.fast_check_pattern is not None and not rule.fast_check_pattern.search(sentence.text):
                continue
            for match in rule.pattern.finditer(sentence.text):
                if not _check_token_boundaries(match, sentence):
                    continue
                if not _check_infront_behind(match, sentence):
                    continue
                if self.use_pos and rule.pos_constraint and not _check_pos_constraint(match, sentence, rule.pos_constraint):
                    continue

                timex_start = match.start()
                timex_end = match.end()
                if rule.offset:
                    offset = _apply_offset(match, rule.offset)
                    if offset:
                        timex_start, timex_end = offset

                attributes = self._get_attributes(rule, match, timex_type)
                if attributes is None:
                    continue

                value, quant, freq, mod, empty_value = attributes
                begin = timex_start + sentence.begin
                end = timex_end + sentence.begin
                span_text = sentence.text[timex_start:timex_end]
                found_by_rule = rule.name
                if timex_type in {"DATE", "TIME"}:
                    if value.startswith("X") or value.startswith("UNDEF"):
                        found_by_rule = f"{found_by_rule}-relative"
                    else:
                        found_by_rule = f"{found_by_rule}-explicit"

                first_token_id = None
                all_token_ids = ""
                for token in sentence.tokens:
                    if token.begin <= begin < token.end:
                        first_token_id = token.token_id
                        all_token_ids = f"BEGIN<-->{token.token_id}"
                    if begin < token.begin and token.end <= end:
                        all_token_ids = f"{all_token_ids}<-->{token.token_id}"

                timexes.append(
                    Timex(
                        timex_type=timex_type,
                        begin=begin,
                        end=end,
                        text=span_text,
                        value=value,
                        quant=quant,
                        freq=freq,
                        mod=mod,
                        empty_value=empty_value,
                        rule=rule.name,
                        timex_id=f"t{self.timex_id}",
                        found_by_rule=found_by_rule,
                        first_token_id=first_token_id,
                        all_token_ids=all_token_ids,
                        sentence_begin=sentence.begin,
                        sentence_end=sentence.end,
                        sentence_tokens=sentence.tokens,
                    )
                )
                self.timex_id += 1

    def _get_attributes(
        self,
        rule: Rule,
        match: Match[str],
        timex_type: str,
    ) -> Optional[List[str]]:
        norm = self.loader.normalizations
        value = apply_rule_functions(rule.normalization, match, norm, self.language_name)
        if value is None:
            return None
        quant = apply_rule_functions(rule.quant, match, norm, self.language_name) if rule.quant else ""
        freq = apply_rule_functions(rule.freq, match, norm, self.language_name) if rule.freq else ""
        mod = apply_rule_functions(rule.mod, match, norm, self.language_name) if rule.mod else ""
        empty_value = (
            apply_rule_functions(rule.empty_value, match, norm, self.language_name) if rule.empty_value else ""
        )
        if empty_value:
            empty_value = correct_duration_value(empty_value)
        if self.group_granularity:
            value = correct_duration_value(value)
        return [value, quant or "", freq or "", mod or "", empty_value or ""]


def remove_invalids(timexes: List[Timex]) -> List[Timex]:
    return [timex for timex in timexes if timex.value != "REMOVE"]


def delete_overlapped_preprocessing(timexes: List[Timex]) -> List[Timex]:
    to_remove: set[int] = set()
    # Performance: comparing all pairs is O(n^2) and dominates runtime on large corpora.
    # We only need to compare spans that actually overlap. Sort by begin offset and walk a window.
    ordered = sorted(timexes, key=lambda t: (t.begin, t.end))
    n = len(ordered)
    for i in range(n):
        t1 = ordered[i]
        for j in range(i + 1, n):
            t2 = ordered[j]
            if t2.begin >= t1.end:
                break
            if ((t1.begin >= t2.begin and t1.end < t2.end) or (t1.begin > t2.begin and t1.end <= t2.end)):
                to_remove.add(id(t1))
            elif ((t2.begin >= t1.begin and t2.end < t1.end) or (t2.begin > t1.begin and t2.end <= t1.end)):
                to_remove.add(id(t2))
            if t1.begin == t2.begin and t1.end == t2.end:
                t1_undef = t1.value.startswith("UNDEF")
                t2_undef = t2.value.startswith("UNDEF")
                if t1_undef and not t2_undef:
                    to_remove.add(id(t1))
                elif not t1_undef and t2_undef:
                    to_remove.add(id(t2))
                elif t1.found_by_rule.endswith("explicit") and not t2.found_by_rule.endswith("explicit"):
                    to_remove.add(id(t2))
                elif (t2.empty_value == "" or t2.empty_value is None) and (t1.empty_value not in ("", None)):
                    to_remove.add(id(t2))
                else:
                    if int(t1.timex_id[1:]) < int(t2.timex_id[1:]):
                        to_remove.add(id(t1))
    return [timex for timex in timexes if id(timex) not in to_remove]


def delete_overlapped_postprocessing(timexes: List[Timex]) -> List[Timex]:
    # Performance: build overlap neighborhoods without an O(n^2) scan.
    # We preserve original ordering by later sorting overlap indices by the original timex list index.
    import heapq

    overlaps: List[set[int]] = [set() for _ in timexes]
    candidates: List[tuple[int, int, int]] = []
    for idx, t in enumerate(timexes):
        if t.timex_type == "TEMPONYM":
            continue
        candidates.append((t.begin, t.end, idx))
    candidates.sort(key=lambda item: item[0])

    active: List[tuple[int, int]] = []  # (end, idx)
    for begin, end, idx in candidates:
        while active and active[0][0] <= begin:
            heapq.heappop(active)
        for _, a_idx in active:
            overlaps[a_idx].add(idx)
            overlaps[idx].add(a_idx)
        heapq.heappush(active, (end, idx))

    overlapping_sets: List[List[Timex]] = []
    inspected: List[Timex] = []
    for idx, t in enumerate(timexes):
        if t.timex_type == "TEMPONYM":
            continue
        overlap_idxs = sorted(overlaps[idx])
        if not overlap_idxs:
            continue
        tset = [t] + [timexes[j] for j in overlap_idxs]
        overlapping_sets.append(tset)
        for j in overlap_idxs:
            inspected.extend([t, timexes[j]])

    pruned_sets: List[List[Timex]] = []
    for t in inspected:
        set_to_keep: List[Timex] = []
        for tset in overlapping_sets:
            if t in tset and len(tset) > len(set_to_keep):
                set_to_keep = tset
        if set_to_keep:
            pruned_sets.append(set_to_keep)

    result = timexes[:]
    for tset in pruned_sets:
        tset = [t for t in tset if t.value != "REMOVE"]
        if not tset:
            continue

        all_same_types = True
        timex_type = None
        longest_timex = None
        combined_begin = min(t.begin for t in tset)
        combined_end = max(t.end for t in tset)
        token_ids: List[int] = []

        for t in tset:
            if timex_type is None:
                timex_type = t.timex_type
            elif timex_type != t.timex_type or timex_type not in {"DATE", "TIME"}:
                all_same_types = False

            if longest_timex is None:
                longest_timex = t
            elif all_same_types and "-BCADhint" in t.found_by_rule:
                longest_timex = t
            elif all_same_types and "relative" not in t.found_by_rule and "relative" in longest_timex.found_by_rule:
                longest_timex = t
            elif len(longest_timex.value) == len(t.value):
                if t.begin < longest_timex.begin:
                    longest_timex = t
            elif len(longest_timex.value) < len(t.value):
                longest_timex = t

            if t.all_token_ids:
                parts = t.all_token_ids.split("<-->")
                for part in parts[1:]:
                    if part.isdigit() and int(part) not in token_ids:
                        token_ids.append(int(part))

        if longest_timex is None:
            continue
        if all_same_types:
            token_ids.sort()
            longest_timex.begin = combined_begin
            longest_timex.end = combined_end
            if token_ids:
                longest_timex.first_token_id = token_ids[0]
                longest_timex.all_token_ids = "BEGIN" + "".join(f"<-->{tid}" for tid in token_ids)

        for t in tset:
            if t in result:
                result.remove(t)
        result.append(longest_timex)
    return result


def _parse_dct(dct: Optional[str]) -> Optional[dict]:
    if not dct:
        return None
    if re.fullmatch(r"\d{8}", dct):
        year = int(dct[0:4])
        month = int(dct[4:6])
        day = int(dct[6:8])
    else:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})", dct)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
    century = int(str(year)[:2])
    decade = int(str(year)[2:3])
    return {"year": year, "month": month, "day": day, "century": century, "decade": decade}


def specify_ambiguous_values(
    timexes: List[Timex],
    doc_type: str,
    dct: Optional[str],
    normalizations: NormalizationManager,
    repatterns: RePatternManager,
) -> List[Timex]:
    class _LastMentionedContext:
        """
        Single-pass cache of the 'last mentioned' temporal anchors needed by disambiguation.

        The original Java logic effectively uses document order. Our previous Python approach
        relied on repeated backward scans (O(n^2)). This cache keeps parity while making
        disambiguation O(n).
        """

        def __init__(self) -> None:
            self._last: dict[str, str] = {}

        def snapshot(self) -> dict[str, str]:
            # Shallow copy so callers can't mutate internal state.
            return dict(self._last)

        def update_from_value(self, value: str, normalizations: NormalizationManager) -> None:
            if not value or "funcDate" in value:
                return

            # BC-aware helpers (only for fields get_last_mentioned_x supports with BC).
            if value.startswith("BC"):
                if re.match(r"^BC[0-9]{4}", value):
                    self._last["year"] = value[:6]
                    self._last["dateYear"] = value
                if re.match(r"^BC[0-9]{2}", value):
                    self._last["century"] = value[:4]
                if re.match(r"^BC[0-9]{3}", value):
                    self._last["decade"] = value[:5]
                if re.match(r"^BC[0-9]{4}-[0-9]{2}", value):
                    self._last["month"] = value[:9]
                return

            # Year / century / decade (AD).
            if re.match(r"^[0-9]{4}", value):
                self._last["year"] = value[:4]
                self._last["dateYear"] = value
                if re.match(r"^[0-9]{2}", value):
                    self._last["century"] = value[:2]
                if re.match(r"^[0-9]{3}", value):
                    self._last["decade"] = value[:3]

            # Month.
            if re.match(r"^[0-9]{4}-[0-9]{2}", value):
                month_val = value[:7]
                self._last["month"] = month_val
                year_val = value[:4]

                # Quarter (derived from month).
                quarter = normalizations.get_from_norm_month_in_quarter(month_val[5:7]) or "1"
                self._last["quarter"] = f"{year_val}-Q{quarter}"

                # Season (derived from month).
                season = normalizations.get_from_norm_month_in_season(month_val[5:7]) or ""
                if season:
                    self._last["season"] = f"{year_val}-{season}"

            # Day.
            if re.match(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
                day_val = value[:10]
                self._last["day"] = day_val
                year_val = value[:4]
                self._last["week"] = f"{year_val}-W{get_week_of_date(day_val):02d}"

            # Week.
            if re.match(r"^[0-9]{4}-W[0-9]{2}", value):
                self._last["week"] = value[:8]

            # Quarter (explicit).
            if re.match(r"^[0-9]{4}-Q[1234]", value):
                self._last["quarter"] = value[:7]

            # Season (explicit).
            if re.match(r"^[0-9]{4}-(SP|SU|FA|WI)", value):
                self._last["season"] = value[:7]

    linear_dates: List[Timex] = []
    for timex in timexes:
        if timex.timex_type in {"DATE", "TIME"}:
            linear_dates.append(timex)
        if timex.timex_type == "DURATION" and timex.empty_value:
            linear_dates.append(timex)

    # Java resolves context-dependent values (e.g., UNDEF-year months/seasons) in document order.
    # Our extraction order is influenced by rule ordering; sort by span offsets so context lookup
    # (get_last_mentioned_x) uses the nearest preceding mention in the text.
    linear_dates.sort(key=lambda t: (t.begin, t.end))

    ctx = _LastMentionedContext()
    pending_same_begin: List[Timex] = []
    current_begin: Optional[int] = None

    for idx, timex in enumerate(linear_dates):
        if current_begin is None:
            current_begin = timex.begin
        elif timex.begin != current_begin:
            # Commit the prior begin-group into the context cache.
            for prev in pending_same_begin:
                ctx.update_from_value(prev.value, normalizations)
            pending_same_begin = []
            current_begin = timex.begin

        last_mentioned = ctx.snapshot()
        if timex.timex_type in {"DATE", "TIME"}:
            timex.value = specify_ambiguous_values_string(
                timex.value,
                timex,
                idx,
                linear_dates,
                doc_type,
                dct,
                normalizations,
                repatterns,
                last_mentioned=last_mentioned,
            )
        if timex.empty_value:
            timex.empty_value = specify_ambiguous_values_string(
                timex.empty_value,
                timex,
                idx,
                linear_dates,
                doc_type,
                dct,
                normalizations,
                repatterns,
                last_mentioned=last_mentioned,
            )
        pending_same_begin.append(timex)

    # Commit the final begin-group.
    for prev in pending_same_begin:
        ctx.update_from_value(prev.value, normalizations)
    return timexes


def specify_ambiguous_values_string(
    ambig_string: str,
    timex: Timex,
    index: int,
    linear_dates: List[Timex],
    doc_type: str,
    dct: Optional[str],
    normalizations: NormalizationManager,
    repatterns: RePatternManager,
    *,
    last_mentioned: Optional[dict[str, str]] = None,
) -> str:
    def _get_last(x: str) -> str:
        if last_mentioned is not None:
            return last_mentioned.get(x, "")
        return get_last_mentioned_x(linear_dates, index, x, normalizations)

    dct_info = _parse_dct(dct)
    dct_available = dct_info is not None
    document_type_news = doc_type == "news"
    document_type_narrative = doc_type in {"narrative", "narratives"}
    document_type_colloquial = doc_type == "colloquial"
    document_type_scientific = doc_type == "scientific"

    dct_year = dct_info["year"] if dct_info else 0
    dct_month = dct_info["month"] if dct_info else 0
    dct_day = dct_info["day"] if dct_info else 0
    dct_century = dct_info["century"] if dct_info else 0
    dct_decade = dct_info["decade"] if dct_info else 0
    dct_quarter = ""
    dct_half = ""
    dct_season = ""
    dct_weekday = 0
    dct_week = 0
    if dct_info:
        dct_quarter = "Q" + normalizations.get_from_norm_month_in_quarter(
            normalizations.get_from_norm_number(str(dct_month)) or ""
        )
        dct_half = "H1" if dct_month <= 6 else "H2"
        dct_season = normalizations.get_from_norm_month_in_season(
            (normalizations.get_from_norm_number(str(dct_month)) or "") + ""
        ) or ""
        dct_weekday = get_weekday_of_date(
            f"{dct_year}-{normalizations.get_from_norm_number(str(dct_month))}-"
            f"{normalizations.get_from_norm_number(str(dct_day))}"
        )
        dct_week = get_week_of_date(
            f"{dct_year}-{normalizations.get_from_norm_number(str(dct_month))}-"
            f"{normalizations.get_from_norm_number(str(dct_day))}"
        )

    # Resolve weekday-only references (and weekday+time) using the most recent anchored day.
    # Examples:
    # - UNDEF-day-sunday -> 1945-05-06
    # - UNDEF-day-mondayTNI -> 1937-12-20TNI
    if ambig_string.startswith("UNDEF-day-"):
        from datetime import datetime, timedelta

        rest = ambig_string[len("UNDEF-day-") :]
        if "T" in rest:
            weekday_word, time_part = rest.split("T", 1)
            time_suffix = "T" + time_part
        else:
            weekday_word, time_suffix = rest, ""

        weekday_word = weekday_word.strip()
        weekday_num_str = normalizations.get_from_norm_day_in_week(weekday_word) or ""
        target_weekday = int(weekday_num_str) if weekday_num_str.isdigit() else 0

        # Choose reference day: narratives prefer last mentioned, other document types can fall back to DCT.
        ref_day = ""
        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
            ref_day = f"{dct_year:04d}-{dct_month:02d}-{dct_day:02d}"
        if not ref_day:
            ref_day = _get_last("day")
        if not ref_day and dct_available:
            ref_day = f"{dct_year:04d}-{dct_month:02d}-{dct_day:02d}"

        if target_weekday and re.fullmatch(r"\d{4}-\d{2}-\d{2}", ref_day or ""):
            dt = datetime.strptime(ref_day, "%Y-%m-%d")
            current_weekday = int(dt.strftime("%w")) + 1  # Sunday=1 .. Saturday=7
            # Match HeidelTime Java behavior: resolve to the most recent occurrence of the weekday
            # on or before the reference day (rather than the next occurrence).
            delta = target_weekday - current_weekday
            if delta > 0:
                delta -= 7
            resolved = (dt + timedelta(days=delta)).strftime("%Y-%m-%d")
            return resolved + time_suffix
        return ambig_string

    value_parts = ambig_string.split("-")
    vi_has_month = False
    vi_has_day = False
    vi_has_season = False
    vi_has_week = False
    vi_has_quarter = False
    vi_has_half = False
    vi_this_month = 0
    vi_this_day = 0
    vi_this_season = ""
    vi_this_quarter = ""
    vi_this_half = ""

    if ambig_string.startswith("UNDEF-year") or ambig_string.startswith("UNDEF-century"):
        if len(value_parts) > 2:
            if re.fullmatch(r"\d\d", value_parts[2]):
                vi_has_month = True
                vi_this_month = int(value_parts[2])
            elif value_parts[2] in {"SP", "SU", "FA", "WI"}:
                vi_has_season = True
                vi_this_season = value_parts[2]
            elif value_parts[2] in {"Q1", "Q2", "Q3", "Q4"}:
                vi_has_quarter = True
                vi_this_quarter = value_parts[2]
            elif value_parts[2] in {"H1", "H2"}:
                vi_has_half = True
                vi_this_half = value_parts[2]
            if len(value_parts) > 3 and re.fullmatch(r"\d\d", value_parts[3]):
                vi_has_day = True
                vi_this_day = int(value_parts[3])
    else:
        if len(value_parts) > 1:
            if re.fullmatch(r"\d\d", value_parts[1]):
                vi_has_month = True
                vi_this_month = int(value_parts[1])
            elif value_parts[1] in {"SP", "SU", "FA", "WI"}:
                vi_has_season = True
                vi_this_season = value_parts[1]
            elif value_parts[1] in {"Q1", "Q2", "Q3", "Q4"}:
                vi_has_quarter = True
                vi_this_quarter = value_parts[1]
            elif value_parts[1] in {"H1", "H2"}:
                vi_has_half = True
                vi_this_half = value_parts[1]
            if len(value_parts) > 2 and re.fullmatch(r"\d\d", value_parts[2]):
                vi_has_day = True
                vi_this_day = int(value_parts[2])

    last_used_tense = get_last_tense(timex, repatterns)
    value_new = ambig_string

    if ambig_string.startswith("UNDEF-year"):
        new_year_value = str(dct_year)
        if vi_has_month and not vi_has_season:
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                if last_used_tense in {"FUTURE", "PRESENTFUTURE"} and dct_month > vi_this_month:
                    new_year_value = str(dct_year + 1)
                if last_used_tense == "PAST" and dct_month < vi_this_month:
                    new_year_value = str(dct_year - 1)
            else:
                new_year_value = _get_last("year")
        if vi_has_quarter:
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                if last_used_tense in {"FUTURE", "PRESENTFUTURE"}:
                    if int(dct_quarter[1]) < int(vi_this_quarter[1]):
                        new_year_value = str(dct_year + 1)
                if last_used_tense == "PAST":
                    if int(dct_quarter[1]) < int(vi_this_quarter[1]):
                        new_year_value = str(dct_year - 1)
                if last_used_tense == "":
                    if document_type_colloquial and int(dct_quarter[1]) < int(vi_this_quarter[1]):
                        new_year_value = str(dct_year + 1)
                    elif int(dct_quarter[1]) < int(vi_this_quarter[1]):
                        new_year_value = str(dct_year - 1)
            else:
                new_year_value = _get_last("year")
        if vi_has_half:
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                if last_used_tense in {"FUTURE", "PRESENTFUTURE"} and int(dct_half[1]) < int(vi_this_half[1]):
                    new_year_value = str(dct_year + 1)
                if last_used_tense == "PAST" and int(dct_half[1]) < int(vi_this_half[1]):
                    new_year_value = str(dct_year - 1)
                if last_used_tense == "":
                    if document_type_colloquial and int(dct_half[1]) < int(vi_this_half[1]):
                        new_year_value = str(dct_year + 1)
                    elif int(dct_half[1]) < int(vi_this_half[1]):
                        new_year_value = str(dct_year - 1)
            else:
                new_year_value = _get_last("year")
        if not vi_has_month and not vi_has_day and vi_has_season:
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                new_year_value = str(dct_year)
            else:
                new_year_value = _get_last("year")
        if vi_has_week:
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                new_year_value = str(dct_year)
            else:
                new_year_value = _get_last("year")

        value_new = ambig_string.replace("UNDEF-year", new_year_value or "XXXX")

    elif ambig_string.startswith("UNDEF-century"):
        new_century_value = str(dct_century)
        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ambig_string != "UNDEF-century":
            vi_this_decade = int(ambig_string[13:14])
            if last_used_tense in {"FUTURE", "PRESENTFUTURE"} and vi_this_decade < dct_decade:
                new_century_value = str(dct_century + 1)
            if last_used_tense == "PAST" and dct_decade < vi_this_decade:
                new_century_value = str(dct_century - 1)
        else:
            new_century_value = _get_last("century")
            if not new_century_value.startswith("BC"):
                if re.match(r"^\d\d.*", new_century_value) and int(new_century_value[:2]) < 10:
                    new_century_value = "00"
            else:
                new_century_value = "00"
        if new_century_value == "":
            if not document_type_narrative:
                value_new = ambig_string.replace("UNDEF-century", "19")
            else:
                value_new = ambig_string.replace("UNDEF-century", "00")
        else:
            value_new = ambig_string.replace("UNDEF-century", new_century_value)
        if re.fullmatch(r"\d\d\d", value_new) and not document_type_narrative:
            value_new = "19" + value_new[2:]

    elif ambig_string.startswith("UNDEF"):
        if re.fullmatch(r"UNDEF-REFDATE", ambig_string):
            if index > 0:
                value_new = linear_dates[index - 1].value
            else:
                value_new = "XXXX-XX-XX"

        # Handle UNDEF-this-day, UNDEF-next-day, UNDEF-last-day (today/tomorrow/yesterday)
        elif ambig_string == "UNDEF-this-day" or ambig_string.startswith("UNDEF-this-dayT"):
            # "today" → PRESENT_REF (Java returns PRESENT_REF for all document types)
            value_new = ambig_string.replace("UNDEF-this-day", "PRESENT_REF")

        elif ambig_string == "UNDEF-next-day" or ambig_string.startswith("UNDEF-next-dayT"):
            # "tomorrow" → DCT + 1 for news/colloquial/scientific, last-mentioned + 1 for narratives
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                date_val = f"{dct_year}-{dct_month:02d}-{dct_day:02d}"
                value_new = ambig_string.replace("UNDEF-next-day", get_x_next_day(date_val, 1))
            else:
                lm_day = _get_last("day")
                if lm_day:
                    value_new = ambig_string.replace("UNDEF-next-day", get_x_next_day(lm_day, 1))
                else:
                    value_new = ambig_string.replace("UNDEF-next-day", "XXXX-XX-XX")

        elif ambig_string == "UNDEF-last-day" or ambig_string.startswith("UNDEF-last-dayT"):
            # "yesterday" → DCT - 1 for news/colloquial/scientific, last-mentioned - 1 for narratives
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                date_val = f"{dct_year}-{dct_month:02d}-{dct_day:02d}"
                value_new = ambig_string.replace("UNDEF-last-day", get_x_next_day(date_val, -1))
            else:
                lm_day = _get_last("day")
                if lm_day:
                    value_new = ambig_string.replace("UNDEF-last-day", get_x_next_day(lm_day, -1))
                else:
                    value_new = ambig_string.replace("UNDEF-last-day", "XXXX-XX-XX")

        # Handle UNDEF-this/last/next-<weekday> (e.g., UNDEF-this-tuesday)
        elif re.match(r"^UNDEF-(this|last|next)-(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", ambig_string, re.IGNORECASE):
            weekday_match = re.match(r"^UNDEF-(this|last|next)-(monday|tuesday|wednesday|thursday|friday|saturday|sunday)(.*)", ambig_string, re.IGNORECASE)
            if weekday_match:
                direction = weekday_match.group(1).lower()
                weekday_name = weekday_match.group(2).lower()
                suffix = weekday_match.group(3)  # e.g., "TNI" for time part
                # Note: get_weekday_of_date uses %w+1 convention: Sunday=1, Monday=2, ..., Saturday=7
                weekday_map = {"sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4, "thursday": 5, "friday": 6, "saturday": 7}
                target_weekday = weekday_map.get(weekday_name, 2)

                if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                    base_date = f"{dct_year}-{dct_month:02d}-{dct_day:02d}"
                    base_weekday = dct_weekday
                else:
                    lm_day = _get_last("day")
                    if lm_day and re.match(r"^\d{4}-\d{2}-\d{2}", lm_day):
                        base_date = lm_day[:10]
                        base_weekday = get_weekday_of_date(base_date)
                    else:
                        value_new = ambig_string  # Can't resolve
                        base_date = None

                if base_date:
                    # Calculate offset from base_weekday to target_weekday
                    # Java behavior: "this <weekday>" finds the nearest occurrence in the future
                    # (same as "next" if weekday has passed, otherwise same week)
                    if direction == "this":
                        diff = target_weekday - base_weekday
                        # If target is today or past this week, go to next week's occurrence
                        if diff <= 0:
                            diff += 7
                    elif direction == "next":
                        # Next occurrence (future) - always at least 1 day ahead
                        diff = target_weekday - base_weekday
                        if diff <= 0:
                            diff += 7
                    else:  # last
                        # Previous occurrence (past) - always at least 1 day back
                        diff = target_weekday - base_weekday
                        if diff >= 0:
                            diff -= 7
                    resolved_date = get_x_next_day(base_date, diff)
                    value_new = resolved_date + suffix

        # Handle UNDEF-last-quarter
        elif ambig_string == "UNDEF-last-quarter":
            if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available:
                year_val = dct_year
                quarter = int(dct_quarter[1]) - 1
                if quarter < 1:
                    quarter = 4
                    year_val -= 1
                value_new = f"{year_val}-Q{quarter}"
            else:
                lm_quarter = _get_last("quarter")
                if lm_quarter and re.match(r"^\d{4}-Q[1-4]", lm_quarter):
                    year_val = int(lm_quarter[:4])
                    quarter = int(lm_quarter[6]) - 1
                    if quarter < 1:
                        quarter = 4
                        year_val -= 1
                    value_new = f"{year_val}-Q{quarter}"

        else:
            match = re.match(r"^(UNDEF-(this|REFUNIT|REF)-(.*?)-(MINUS|PLUS)-([0-9]+)).*", ambig_string)
            if match:
                check_undef = match.group(1)
                ltn = match.group(2)
                unit = match.group(3)
                op = match.group(4)
                diff = int(match.group(5))
                if document_type_scientific:
                    op_symbol = "-" if op == "MINUS" else "+"
                    if unit == "year":
                        value_new = f"TPZ{op_symbol}{diff:04d}"
                    elif unit == "month":
                        value_new = f"TPZ{op_symbol}0000-{diff:02d}"
                    elif unit == "week":
                        value_new = f"TPZ{op_symbol}0000-W{diff:02d}"
                    elif unit == "day":
                        value_new = f"TPZ{op_symbol}0000-00-{diff:02d}"
                    elif unit == "hour":
                        value_new = f"TPZ{op_symbol}0000-00-00T{diff:02d}"
                    elif unit == "minute":
                        value_new = f"TPZ{op_symbol}0000-00-00T00:{diff:02d}"
                    elif unit == "second":
                        value_new = f"TPZ{op_symbol}0000-00-00T00:00:{diff:02d}"
                else:
                    if ltn == "REFUNIT" and unit == "year":
                        date_with_year = _get_last("dateYear")
                        if not date_with_year:
                            value_new = value_new.replace(check_undef, "XXXX")
                        else:
                            if op == "MINUS":
                                diff = -diff
                            year_new = get_x_next_year(date_with_year[:4], diff)
                            rest = date_with_year[4:]
                            value_new = value_new.replace(check_undef, year_new + rest)
                    elif unit == "century":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            century = dct_century - diff if op == "MINUS" else dct_century + diff
                            value_new = value_new.replace(check_undef, str(century))
                        else:
                            lm_century = _get_last("century")
                            if not lm_century:
                                value_new = value_new.replace(check_undef, "XX")
                            else:
                                if op == "MINUS":
                                    diff = -diff
                                lm_century = get_x_next_century(lm_century, diff)
                                value_new = value_new.replace(check_undef, lm_century)
                    elif unit == "decade":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            dct_decade_long = int(f"{dct_century}{dct_decade}")
                            decade = dct_decade_long - diff if op == "MINUS" else dct_decade_long + diff
                            value_new = value_new.replace(check_undef, f"{decade}X")
                        else:
                            lm_decade = _get_last("decade")
                            if not lm_decade:
                                value_new = value_new.replace(check_undef, "XXX")
                            else:
                                if op == "MINUS":
                                    diff = -diff
                                lm_decade = get_x_next_decade(lm_decade, diff)
                                value_new = value_new.replace(check_undef, lm_decade)
                    elif unit == "year":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            year_val = dct_year - diff if op == "MINUS" else dct_year + diff
                            value_new = value_new.replace(check_undef, str(year_val))
                        else:
                            lm_year = _get_last("year")
                            if not lm_year:
                                value_new = value_new.replace(check_undef, "XXXX")
                            else:
                                if op == "MINUS":
                                    diff = -diff
                                lm_year = get_x_next_year(lm_year, diff)
                                value_new = value_new.replace(check_undef, lm_year)
                    elif unit == "quarter":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            year_val = dct_year
                            quarter = int(dct_quarter[1])
                            diff_quarters = diff % 4
                            diff_years = diff // 4
                            if op == "MINUS":
                                diff_quarters *= -1
                                diff_years *= -1
                            year_val += diff_years
                            quarter += diff_quarters
                            value_new = value_new.replace(check_undef, f"{year_val}-Q{quarter}")
                        else:
                            lm_quarter = _get_last("quarter")
                            if not lm_quarter:
                                value_new = value_new.replace(check_undef, "XXXX-XX")
                            else:
                                year_val = int(lm_quarter[:4])
                                quarter = int(lm_quarter[6:])
                                diff_quarters = diff % 4
                                diff_years = diff // 4
                                if op == "MINUS":
                                    diff_quarters *= -1
                                    diff_years *= -1
                                year_val += diff_years
                                quarter += diff_quarters
                                value_new = value_new.replace(check_undef, f"{year_val}-Q{quarter}")
                    elif unit == "month":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            date_val = f"{dct_year}-{dct_month:02d}"
                            diff = -diff if op == "MINUS" else diff
                            value_new = value_new.replace(check_undef, get_x_next_month(date_val, diff))
                        else:
                            lm_month = _get_last("month")
                            if not lm_month:
                                # Keep UNDEF-REF pattern for SCATEX conversion instead of XXXX
                                pass  # value_new remains unchanged (preserves UNDEF-REF-month-...)
                            else:
                                diff = -diff if op == "MINUS" else diff
                                value_new = value_new.replace(check_undef, get_x_next_month(lm_month, diff))
                    elif unit == "week":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            date_val = f"{dct_year}-{dct_month:02d}-{dct_day:02d}"
                            diff = -diff if op == "MINUS" else diff
                            value_new = value_new.replace(check_undef, get_x_next_week(date_val, diff))
                        else:
                            lm_week = _get_last("week")
                            if not lm_week:
                                # Keep UNDEF-REF pattern for SCATEX conversion instead of XXXX-WXX
                                pass  # value_new remains unchanged (preserves UNDEF-REF-week-...)
                            else:
                                diff = -diff if op == "MINUS" else diff
                                value_new = value_new.replace(check_undef, get_x_next_week(lm_week, diff))
                    elif unit == "day":
                        if (document_type_news or document_type_colloquial or document_type_scientific) and dct_available and ltn == "this":
                            date_val = f"{dct_year}-{dct_month:02d}-{dct_day:02d}"
                            diff = -diff if op == "MINUS" else diff
                            value_new = value_new.replace(check_undef, get_x_next_day(date_val, diff))
                        else:
                            lm_day = _get_last("day")
                            if not lm_day:
                                # Keep UNDEF-REF pattern for SCATEX conversion instead of XXXX-XX-XX
                                pass  # value_new remains unchanged (preserves UNDEF-REF-day-...)
                            else:
                                diff = -diff if op == "MINUS" else diff
                                value_new = value_new.replace(check_undef, get_x_next_day(lm_day, diff))
                    elif unit in ("hour", "minute", "second"):
                        # Time units - keep UNDEF-REF pattern for SCATEX conversion
                        pass  # value_new remains unchanged (preserves UNDEF-REF-{hour,minute,second}-...)
    return value_new


def disambiguate_historic_dates(timexes: List[Timex]) -> List[Timex]:
    for i in range(1, len(timexes)):
        t_i = timexes[i]
        value_i = t_i.value
        new_value = value_i
        if "-BCADhint" not in t_i.found_by_rule and value_i.startswith("0"):
            offset = 1
            counter = 1
            change = False
            while counter < 5 and offset < i:
                t_prev = timexes[i - offset]
                if t_prev.value.startswith("BC"):
                    if len(value_i) > 1:
                        if t_prev.value.startswith("BC" + value_i[:2]) or t_prev.value.startswith(
                            "BC" + f"{int(value_i[:2]) + 1:02d}"
                        ):
                            if (value_i.startswith("00") and t_prev.value.startswith("BC00")) or (
                                value_i.startswith("01") and t_prev.value.startswith("BC01")
                            ):
                                if len(value_i) > 2 and len(t_prev.value) > 4:
                                    if int(value_i[:3]) <= int(t_prev.value[2:5]):
                                        new_value = "BC" + value_i
                                        change = True
                            else:
                                new_value = "BC" + value_i
                                change = True
                if t_prev.timex_type in {"TIME", "DATE"} and re.match(r"^\d", t_prev.value):
                    counter += 1
                if change:
                    break
                offset += 1
        if new_value != value_i:
            t_i.value = new_value
    return timexes
