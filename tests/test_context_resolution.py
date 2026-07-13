"""Fix 2 (error map F07/F08): narrative last-mentioned anchoring must be disableable.

With context_resolution=False, relative/bare expressions keep their UNDEF-* values
(for downstream unanchored SCATEX conversion) instead of being resolved to absolute
dates from the document context. Default behavior (True) is unchanged.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heideltime_engine import HeidelTimeEngine
from tests.test_token_boundaries import create_mock_sentence, RESOURCES_DIR

TEXT = "The war began on October 7, 2023. The next day, fighting intensified. On Monday the troops left."


def _extract(context_resolution):
    eng = HeidelTimeEngine(
        language_dir=os.path.join(RESOURCES_DIR, "english"),
        doc_type="narrative", use_pos=False, resolve_with_dct=False,
        context_resolution=context_resolution,
    )
    return eng.extract(TEXT, sentences=[create_mock_sentence(TEXT)])


def test_leak_stopped_when_disabled():
    values = {t.text: t.value for t in _extract(False)}
    next_day = [v for k, v in values.items() if "next day" in k.lower()]
    assert next_day and next_day[0].startswith("UNDEF"), \
        f"'the next day' should stay UNDEF-*, got {next_day}"
    monday = [v for k, v in values.items() if "monday" in k.lower()]
    assert monday and monday[0].startswith("UNDEF-day"), \
        f"bare 'Monday' should stay UNDEF-day-*, got {monday}"


def test_default_still_resolves():
    values = {t.text: t.value for t in _extract(True)}
    next_day = [v for k, v in values.items() if "next day" in k.lower()]
    # default narrative behavior: resolved from the last-mentioned date
    assert next_day and next_day[0] == "2023-10-08", f"expected 2023-10-08, got {next_day}"
