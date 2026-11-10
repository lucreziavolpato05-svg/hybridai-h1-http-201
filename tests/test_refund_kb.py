import shutil
import time

import pytest
from refund.kb import RefundKB, DAY, tools

SG, ZH = "sp_8506302", "sp_8503000"

@pytest.fixture(scope="module")
def kb():
    if not shutil.which("framex"):
        pytest.skip("framex engine not installed")
    started = time.perf_counter()
    instance = RefundKB()
    print(f"init {time.perf_counter() - started:.1f}s")
    yield instance
    instance.close()

def test_stations(kb):
    assert kb.station("St. Gallen")["stop"] == SG
    assert kb.station("St. Gallen")["designation"] == "St. Gallen"
    assert kb.station("zürich hb")["stop"] == ZH
    assert kb.station("Atlantis")["status"] == "unknown"

def test_other_day_is_out_of_scope(kb):
    assert kb.measure(SG, ZH, "2026-11-08", "08:00")["status"] == "outOfScope"

def test_window_offers_trains_and_a_choice_measures_one(kb):
    started = time.perf_counter()
    result = kb.measure(SG, ZH, DAY, "08:00")
    print(f"offer {time.perf_counter() - started:.1f}s", result)
    assert result["status"] == "ambiguous"
    rows = {(r["departure"], r.get("train")) for r in result["rows"]}
    assert {("07:58", "IC IC5"), ("08:07", "IC IC1")} <= rows
    assert all({"departure", "arrival", "changes"} <= set(r) for r in result["rows"])
    started = time.perf_counter()
    chosen = kb.measure(SG, ZH, DAY, "08:00", "07:58")
    print(f"measure {time.perf_counter() - started:.1f}s", chosen)
    assert chosen["status"] == "measured"
    assert isinstance(chosen["delayMinutes"], int)
    assert chosen["plannedDeparture"] == "07:58" and chosen["train"] == "IC IC5"
    assert chosen["caseId"].startswith("y_")

def test_choice_with_train_text_and_unmatched_choice(kb):
    chosen = kb.measure(SG, ZH, DAY, "08:00", "08:07 ic1")
    assert chosen["status"] == "measured" and chosen["train"] == "IC IC1"
    again = kb.measure(SG, ZH, DAY, "08:00", "09:59")
    assert again["status"] == "ambiguous" and len(again["rows"]) >= 2

def test_tools_adapters(kb):
    adapters = tools(kb)
    assert set(adapters) == {"_station", "_measure"}
    found, _ = adapters["_station"]({"name": "Zürich HB"})
    assert found["stop"] == ZH
    measured, _ = adapters["_measure"]({"origin": SG, "destination": ZH, "date": DAY, "time": "11:29", "choice": "11:29 EC"})
    assert measured["status"] == "measured" and measured["delayMinutes"] >= 15
