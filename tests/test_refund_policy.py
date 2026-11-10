import pytest
from refund.policy import decide, policy_tool

@pytest.mark.parametrize("delay,percent", [(45,0),(59,0),(60,25),(70,25),(119,25),(120,50),(130,50)])
def test_boundaries(delay, percent):
    assert decide(delay, 80)["percent"] == percent

def test_payout():
    assert decide(70, 12)["paidOut"] is False
    assert decide(130, 80)["amountChf"] == 40
    assert decide(130, 80)["paidOut"] is True

@pytest.mark.parametrize("price", [0, -1, "abc"])
def test_invalid(price):
    with pytest.raises(ValueError): policy_tool({"delayMinutes": 70, "price": price})
