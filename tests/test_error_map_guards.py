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


# --- K5: "a year ago" keeps its offset semantics when unanchored ---

def test_a_year_ago_keeps_refunit(monkeypatch=None):
    eng_kw = dict(doc_type="narrative", resolve_with_dct=False, context_resolution=False)
    values = [t.value for t in _extract("A year ago the factory closed", **eng_kw)]
    assert any(v.startswith("UNDEF-REFUNIT-year-MINUS-1") for v in values), values


# --- K2: PM timestamps keep their seconds ---

def test_pm_timestamp_keeps_seconds():
    values = [t.value for t in _extract("It was logged at 10:54:31 PM exactly")]
    assert any(v.endswith("T22:54:31") for v in values), values


# --- K7: Victorian comma-year ("November, 1844") must be inside the span ---

def test_month_comma_year():
    timexes = _extract("It happened in November, 1844. Many wept.")
    assert any(t.value == "1844-11" for t in timexes), [(t.text, t.value) for t in timexes]


def test_day_of_month_comma_year():
    timexes = _extract("Dated the 17th of April, 1862, at noon")
    assert any(t.value == "1862-04-17" for t in timexes), [(t.text, t.value) for t in timexes]


# --- K8: masthead 'Daily <Proper>' must not be a daily SET ---

def test_daily_masthead_not_set():
    timexes = _extract("The Daily Stormer published the article")
    assert not any(t.timex_type == "SET" for t in timexes), \
        [(t.text, t.timex_type, t.value) for t in timexes]


def test_plain_daily_still_set():
    timexes = _extract("The medication is taken daily with food")
    assert any(t.timex_type == "SET" and t.value == "XXXX-XX-XX" for t in timexes), \
        [(t.text, t.timex_type, t.value) for t in timexes]


# --- B1: frequency adverbs (recall gap: 'hourly'/'nightly'/'yearly'/'quarterly'
#         were labeled as negatives) ---

def test_frequency_adverbs_detected():
    cases = {"hourly": "XXXX-XX-XXTXX", "nightly": "XXXX-XX-XX",
             "yearly": "XXXX", "quarterly": "P3M"}
    for word, expected in cases.items():
        vals = [t.value for t in _extract(f"The report runs {word} without fail")]
        assert expected in vals, f"{word}: expected {expected}, got {vals}"

def test_annually_still_works():
    vals = [t.value for t in _extract("It is published annually in June")]
    assert "XXXX" in vals, vals
