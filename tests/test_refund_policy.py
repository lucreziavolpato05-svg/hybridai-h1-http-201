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


# Minimum payout: the amount is rounded to the cent (half up), then compared with CHF 5.
@pytest.mark.parametrize("delay,price,amount,paid", [
    (70, 20.00, 5.00, True),    # exactly CHF 5.00
    (70, 19.98, 5.00, True),    # 4.995 rounds to 5.00: paid (team decision)
    (70, 19.96, 4.99, False),   # 4.99: just under, not paid out
    (130, 10.00, 5.00, True),
    (130, 9.99, 5.00, True),    # 4.995 -> 5.00
    (130, 9.97, 4.99, False),   # 4.985 -> 4.99
    (70, 10.70, 2.68, False),   # 2.675: float round() would give 2.67
])
def test_minimum_payout_boundary(delay, price, amount, paid):
    v = decide(delay, price)
    assert v["amountChf"] == amount and v["paidOut"] is paid
    assert v["minPayoutChf"] == 5.0


def test_no_refund_is_never_paid_out():
    v = decide(59, 1000)
    assert v["status"] == "notEntitled" and v["paidOut"] is False and v["thresholdMin"] == 60
