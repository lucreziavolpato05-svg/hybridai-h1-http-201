import shutil
import pytest
from refund.kb import RefundKB, DAY

@pytest.fixture(scope="module")
def kb():
    if not shutil.which("framex"):
        pytest.skip("framex engine not installed")
    instance = RefundKB()
    yield instance
    instance.session.close()

def test_stations(kb):
    assert kb.station("St. Gallen")["stop"] == "sp_8506302"
    assert kb.station("zürich hb")["stop"] == "sp_8503000"
    assert kb.station("Atlantis")["status"] == "unknown"

def test_journey(kb):
    assert kb.measure("sp_8506302", "sp_8503000", "2026-11-08", "08:00")["status"] == "outOfScope"
    result = kb.measure("sp_8506302", "sp_8503000", DAY, "08:00")
    print(result)
    assert result["status"] in ("ambiguous", "measured", "notMeasured")
    if result["status"] == "ambiguous":
        selected = kb.measure("sp_8506302", "sp_8503000", DAY, "08:00", result["rows"][0]["departure"])
        print(selected)
        assert selected["status"] in ("ambiguous", "measured", "notMeasured")
