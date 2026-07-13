"""Fix 5 (error map F12/5a/5b/5d): 12-hour clock bugs, comma-BC, year false positives."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from heideltime_engine import HeidelTimeEngine
from tests.test_token_boundaries import create_mock_sentence, RESOURCES_DIR


def _extract(text, **kw):
    eng = HeidelTimeEngine(language_dir=os.path.join(RESOURCES_DIR, "english"),
                           use_pos=False, **kw)
    return eng.extract(text, sentences=[create_mock_sentence(text)])


# --- 5a: 12-hour clock ---

def test_1240pm_is_hour_12():
    values = [t.value for t in _extract("The vote closed at 12:40pm on the dot")]
    assert any("T12:40" in v for v in values), values
    assert not any("T24" in v for v in values), values


def test_1201am_is_hour_00():
    values = [t.value for t in _extract("It began at 12:01 AM sharp")]
    assert any("T00:01" in v for v in values), values


def test_130pm_unchanged():
    values = [t.value for t in _extract("Lunch is at 1:30pm today")]
    assert any("T13:30" in v for v in values), values


# --- 5b: comma-thousands BC must not become year 0 ---

def test_comma_bc_not_year_zero():
    values = [t.value for t in _extract("The site dates to 1,000 BC according to digs")]
    assert not any(v.startswith("BC0000") for v in values), values


# --- 5d: year false positives ---

def test_windows_version_not_year():
    timexes = _extract("Upgrade to Windows 1709 before October")
    assert not any(t.timex_type == "DATE" and t.value == "1709" for t in timexes), \
        [(t.text, t.value) for t in timexes]


def test_pound_price_not_year():
    timexes = _extract("The engine sold for £1903 at auction")
    assert not any(t.timex_type == "DATE" and t.value == "1903" for t in timexes), \
        [(t.text, t.value) for t in timexes]


def test_1430_gmt_is_time_not_year():
    timexes = _extract("The strike began at 1430 GMT near the port")
    assert not any(t.timex_type == "DATE" and t.value == "1430" for t in timexes), \
        [(t.text, t.timex_type, t.value) for t in timexes]


def test_plain_year_still_detected():
    timexes = _extract("The treaty was signed in 1903 in Paris")
    assert any(t.timex_type == "DATE" and t.value == "1903" for t in timexes), \
        [(t.text, t.value) for t in timexes]
