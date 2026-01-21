import os
import re
import warnings
from dataclasses import dataclass
from typing import Dict, List, Optional

from regex_hash_map import RegexHashMap

SPACE_CLASS = r"[\u2000-\u200A \u202F\u205F\u3000\u00A0\u1680\u180E]+"
SPACE_CLASS_NESTED = SPACE_CLASS.replace(" ", r"[\s]+")
SPACE_CLASS_EQUIV = r"[\s\u2000-\u200A\u202F\u205F\u3000\u00A0\u1680\u180E]+"


def replace_spaces(text: str) -> str:
    return text.replace(" ", SPACE_CLASS)


def _effective_length(pattern: str) -> int:
    effective = re.sub(r"\[[^\]]*\]", "X", pattern)
    effective = re.sub(r"\?", "", effective)
    effective = re.sub(r"\\.(?:\{([^\}])+\})?", r"X\1", effective)
    return len(effective)


def _finalize_repattern(pattern: str) -> str:
    if pattern.startswith("|"):
        pattern = pattern[1:]
    # Convert user-created capturing groups to non-capturing groups.
    pattern = re.sub(r"\(([^?])", r"(?:\1", pattern)
    return f"({pattern})"


def _replace_spaces_outside_char_classes(pattern: str) -> str:
    parts: List[str] = []
    in_class = False
    escaped = False
    for ch in pattern:
        if escaped:
            parts.append(ch)
            escaped = False
            continue
        if ch == "\\":
            parts.append(ch)
            escaped = True
            continue
        if ch == "[":
            in_class = True
            parts.append(ch)
            continue
        if ch == "]":
            in_class = False
            parts.append(ch)
            continue
        if ch == " " and not in_class:
            parts.append(r"[\s]+")
            continue
        parts.append(ch)
    return "".join(parts)


def _list_resource_files(directory: str, prefix: str) -> Dict[str, str]:
    resources: Dict[str, str] = {}
    for filename in os.listdir(directory):
        match = re.match(rf"{re.escape(prefix)}(.+)\.txt$", filename)
        if match:
            resources[match.group(1)] = os.path.join(directory, filename)
    return resources


@dataclass
class Rule:
    name: str
    extraction: str
    pattern: re.Pattern
    normalization: str
    offset: str = ""
    quant: str = ""
    freq: str = ""
    mod: str = ""
    pos_constraint: str = ""
    empty_value: str = ""
    fast_check: str = ""
    fast_check_pattern: Optional[re.Pattern] = None


class RePatternManager:
    def __init__(self, language_dir: str, load_temponym_resources: bool = False) -> None:
        self.language_dir = language_dir
        self.load_temponym_resources = load_temponym_resources
        self.repatterns = self._load_repatterns()

    def _load_repatterns(self) -> Dict[str, str]:
        repattern_dir = os.path.join(self.language_dir, "repattern")
        resources = _list_resource_files(repattern_dir, "resources_repattern_")
        repatterns: Dict[str, str] = {}

        for resource_name, path in resources.items():
            if "Temponym" in resource_name and not self.load_temponym_resources:
                repatterns[resource_name] = ""
                continue
            patterns: List[str] = []
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    patterns.append(replace_spaces(line))

            patterns.sort(key=_effective_length, reverse=True)
            combined = "".join(f"|{pattern}" for pattern in patterns)
            repatterns[resource_name] = _finalize_repattern(combined)

        return repatterns

    def get(self, key: str) -> str:
        return self.repatterns[key]

    def contains(self, key: str) -> bool:
        return key in self.repatterns


class NormalizationManager:
    def __init__(self, language_dir: str, load_temponym_resources: bool = False) -> None:
        self.language_dir = language_dir
        self.load_temponym_resources = load_temponym_resources
        self.normalizations = self._load_normalizations()
        self.norm_number = self._load_norm_number()
        self.norm_day_in_week = self._load_norm_day_in_week()
        self.norm_month_name = self._load_norm_month_name()
        self.norm_month_in_season = self._load_norm_month_in_season()
        self.norm_month_in_quarter = self._load_norm_month_in_quarter()

    def _load_normalizations(self) -> Dict[str, RegexHashMap]:
        normalization_dir = os.path.join(self.language_dir, "normalization")
        resources = _list_resource_files(normalization_dir, "resources_normalization_")
        normalizations: Dict[str, RegexHashMap] = {}
        line_pattern = re.compile(r"\"(.*?)\",\"(.*?)\"")

        for resource_name, path in resources.items():
            if "Temponym" in resource_name and not self.load_temponym_resources:
                normalizations[resource_name] = RegexHashMap()
                continue
            normalizations[resource_name] = RegexHashMap()
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    match = line_pattern.search(line)
                    if match:
                        resource_word = replace_spaces(match.group(1))
                        normalized_word = match.group(2)
                        normalizations[resource_name].put(resource_word, normalized_word)
        return normalizations

    @staticmethod
    def _load_norm_number() -> Dict[str, str]:
        norm_number: Dict[str, str] = {}
        for value in range(0, 61):
            key = str(value)
            norm_number[key] = f"{value:02d}"
        norm_number["00"] = "00"
        return norm_number

    @staticmethod
    def _load_norm_day_in_week() -> Dict[str, str]:
        return {
            "sunday": "1",
            "monday": "2",
            "tuesday": "3",
            "wednesday": "4",
            "thursday": "5",
            "friday": "6",
            "saturday": "7",
            "Sunday": "1",
            "Monday": "2",
            "Tuesday": "3",
            "Wednesday": "4",
            "Thursday": "5",
            "Friday": "6",
            "Saturday": "7",
        }

    @staticmethod
    def _load_norm_month_name() -> Dict[str, str]:
        return {
            "january": "01",
            "february": "02",
            "march": "03",
            "april": "04",
            "may": "05",
            "june": "06",
            "july": "07",
            "august": "08",
            "september": "09",
            "october": "10",
            "november": "11",
            "december": "12",
        }

    @staticmethod
    def _load_norm_month_in_season() -> Dict[str, str]:
        return {
            "": "",
            "01": "WI",
            "02": "WI",
            "03": "SP",
            "04": "SP",
            "05": "SP",
            "06": "SU",
            "07": "SU",
            "08": "SU",
            "09": "FA",
            "10": "FA",
            "11": "FA",
            "12": "WI",
        }

    @staticmethod
    def _load_norm_month_in_quarter() -> Dict[str, str]:
        return {
            "01": "1",
            "02": "1",
            "03": "1",
            "04": "2",
            "05": "2",
            "06": "2",
            "07": "3",
            "08": "3",
            "09": "3",
            "10": "4",
            "11": "4",
            "12": "4",
        }

    def get_from_hm_all_normalization(self, key: str) -> RegexHashMap:
        return self.normalizations[key]

    def get_from_norm_number(self, key: str) -> Optional[str]:
        return self.norm_number.get(key)

    def get_from_norm_day_in_week(self, key: str) -> Optional[str]:
        return self.norm_day_in_week.get(key)

    def get_from_norm_month_name(self, key: str) -> Optional[str]:
        return self.norm_month_name.get(key)

    def get_from_norm_month_in_season(self, key: str) -> Optional[str]:
        return self.norm_month_in_season.get(key)

    def get_from_norm_month_in_quarter(self, key: str) -> Optional[str]:
        return self.norm_month_in_quarter.get(key)


class RuleManager:
    def __init__(
        self,
        language_dir: str,
        repattern_manager: RePatternManager,
        load_temponym_resources: bool = False,
    ) -> None:
        self.language_dir = language_dir
        self.repattern_manager = repattern_manager
        self.load_temponym_resources = load_temponym_resources
        self.rules = self._load_rules()

    def _compile_extraction(self, extraction: str) -> str:
        extraction = replace_spaces(extraction)
        variable_pattern = re.compile(r"%(re[a-zA-Z0-9]*)")
        variables = [match.group(1) for match in variable_pattern.finditer(extraction)]
        for variable in variables:
            if not self.repattern_manager.contains(variable):
                raise KeyError(f"Missing repattern %{variable} in extraction: {extraction}")
            repattern = self.repattern_manager.get(variable)
            extraction = re.sub(
                rf"%{re.escape(variable)}",
                lambda _: repattern,
                extraction,
            )
        # Match Java behavior: replace literal spaces outside char classes.
        extraction = _replace_spaces_outside_char_classes(extraction)
        # Normalize inserted space classes into a Java-equivalent union for Python.
        return extraction.replace(SPACE_CLASS, SPACE_CLASS_EQUIV)

    def _compile_fast_check(self, fast_check: str) -> str:
        return self._compile_extraction(fast_check)

    def _load_rules(self) -> Dict[str, List[Rule]]:
        rules_dir = os.path.join(self.language_dir, "rules")
        resources = _list_resource_files(rules_dir, "resources_rules_")
        rules: Dict[str, List[Rule]] = {name: [] for name in resources}
        main_pattern = re.compile(r"RULENAME=\"(.*?)\",EXTRACTION=\"(.*?)\",NORM_VALUE=\"(.*?)\"(.*)")
        seen_rule_names = set()
        ordered_resources = sorted(
            resources.items(),
            key=lambda item: (
                0 if item[0] == "daterules"
                else 1 if item[0] == "timerules"
                else 2 if item[0] == "durationrules"
                else 3 if item[0] == "setrules"
                else 4
            ),
        )

        for resource_name, path in ordered_resources:
            if resource_name == "temponymrules" and not self.load_temponym_resources:
                continue
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    match = main_pattern.search(line)
                    if not match:
                        continue

                    rule_name = match.group(1)
                    rule_extraction = match.group(2)
                    rule_normalization = match.group(3)
                    tail = match.group(4) or ""
                    if rule_name in seen_rule_names and resource_name != "temponymrules":
                        continue

                    compiled_extraction = self._compile_extraction(rule_extraction)
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            "ignore",
                            message="Possible nested set.*",
                            category=FutureWarning,
                        )
                        pattern = re.compile(compiled_extraction)

                    def _find_field(field: str) -> str:
                        field_match = re.search(rf"{field}=\"(.*?)\"", line)
                        return field_match.group(1) if field_match else ""

                    rule_offset = _find_field("OFFSET")
                    rule_quant = _find_field("NORM_QUANT")
                    rule_freq = _find_field("NORM_FREQ")
                    rule_mod = _find_field("NORM_MOD")
                    rule_pos = _find_field("POS_CONSTRAINT")
                    rule_empty = _find_field("EMPTY_VALUE")
                    rule_fast = _find_field("FAST_CHECK")

                    fast_check_pattern = None
                    if rule_fast:
                        compiled_fast = self._compile_fast_check(rule_fast)
                        with warnings.catch_warnings():
                            warnings.filterwarnings(
                                "ignore",
                                message="Possible nested set.*",
                                category=FutureWarning,
                            )
                            fast_check_pattern = re.compile(compiled_fast)

                    rules[resource_name].append(
                        Rule(
                            name=rule_name,
                            extraction=compiled_extraction,
                            pattern=pattern,
                            normalization=rule_normalization,
                            offset=rule_offset,
                            quant=rule_quant,
                            freq=rule_freq,
                            mod=rule_mod,
                            pos_constraint=rule_pos,
                            empty_value=rule_empty,
                            fast_check=rule_fast,
                            fast_check_pattern=fast_check_pattern,
                        )
                    )
                    if resource_name != "temponymrules":
                        seen_rule_names.add(rule_name)

        return rules


class HeidelTimeLoader:
    def __init__(self, language_dir: str, load_temponym_resources: bool = False) -> None:
        if not os.path.isdir(language_dir):
            raise FileNotFoundError(f"Language directory not found: {language_dir}")

        self.language_dir = language_dir
        self.repatterns = RePatternManager(language_dir, load_temponym_resources)
        self.normalizations = NormalizationManager(language_dir, load_temponym_resources)
        self.rules = RuleManager(language_dir, self.repatterns, load_temponym_resources)

    def summary(self) -> Dict[str, int]:
        return {
            "repattern_count": len(self.repatterns.repatterns),
            "normalization_count": len(self.normalizations.normalizations),
            "rule_files": len(self.rules.rules),
            "rule_count": sum(len(items) for items in self.rules.rules.values()),
        }
