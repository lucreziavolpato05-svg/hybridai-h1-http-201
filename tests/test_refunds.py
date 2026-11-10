"""Refund delay rules (46-refunds.fx): planned against actual arrival at the destination."""
from __future__ import annotations

import json

from ontology import service
from test_regression import DAY, client, load, stop  # noqa: F401  (client is a fixture)

ORIGIN, DESTINATION, VIA = 1, 2, 3


def late(trip, station, planned, actual, **extra):
    """A stop planned at one time that really happened at another."""
    row = stop(trip, station, planned, **extra)
    row["an_prognose"] = row["ab_prognose"] = f"{DAY}T{actual}:00"
    return row


def epoch(clock):
    return service.timestamp(f"{DAY}T{clock}:00")


def case(client, rows, around="08:00", window=30):
    from ontology.ids import Scope
    load(client, rows, Scope({ORIGIN, DESTINATION, VIA}))
    stated = epoch(around)
    client.add(source=f'x:RefundCase[origin -> sp_{ORIGIN}; destination -> sp_{DESTINATION}; '
                      f'onDay -> "{DAY}"; windowFrom -> {stated - window * 60}; '
                      f'windowTo -> {stated + window * 60}; transferSeconds -> 300].')


def departures(client):
    found = client.query("?- x[plannedArrival(?E) -> ?A; plannedChanges(?E) -> ?C] "
                         "AND ?E[scheduledDepartureEpoch -> ?D].")
    return sorted((int(r["D"]), int(r["A"]), int(r["C"])) for r in found.get("bindings", []))


def check(client, departure):
    found = client.query(f"?- x[plannedArrival(?E) -> ?A] AND ?E[scheduledDepartureEpoch -> {epoch(departure)}].")
    board = found["bindings"][0]["E"]
    client.add(source=f"y:DelayCheck[checkOf -> x; plannedBoard -> {board}].")


def value(client, slot):
    found = client.query(f"?- y[{slot} -> ?V].").get("bindings", [])
    return [json.loads(r["V"]) for r in found]


def test_a_late_direct_train_is_its_delay(client):
    case(client, [stop("ic", ORIGIN, "08:00"), late("ic", DESTINATION, "09:00", "10:05")])
    assert departures(client) == [(epoch("08:00"), epoch("09:00"), 0)]
    check(client, "08:00")
    assert value(client, "delayMinutes") == [65]
    assert value(client, "delayMeasured") == [True]


def test_a_missed_connection_counts_until_the_next_train_arrives(client):
    # Planned: change at VIA with 10 minutes. The first train is 15 minutes late,
    # so the passenger takes the next train an hour later.
    rows = [stop("a", ORIGIN, "08:00"), late("a", VIA, "08:30", "08:45"),
            stop("b", VIA, "08:40"), stop("b", DESTINATION, "09:10"),
            stop("c", VIA, "09:40"), stop("c", DESTINATION, "10:10")]
    case(client, rows)
    check(client, "08:00")
    assert value(client, "plannedArrival") == [epoch("09:10")]
    assert value(client, "actualArrival") == [epoch("10:10")]
    assert value(client, "delayMinutes") == [60]


def test_a_cancelled_train_is_replaced_by_the_next_one(client):
    rows = [dict(stop("ic", ORIGIN, "08:00"), faellt_aus_tf=True),
            dict(stop("ic", DESTINATION, "09:00"), faellt_aus_tf=True),
            stop("next", ORIGIN, "10:00"), stop("next", DESTINATION, "11:00")]
    case(client, rows)
    # The cancelled train was planned, so the passenger can name it.
    assert departures(client)[0][:2] == (epoch("08:00"), epoch("09:00"))
    check(client, "08:00")
    assert value(client, "planCancelled") == [True]
    assert value(client, "delayMinutes") == [120]
    assert value(client, "delayMeasured") == [True]


def test_arriving_on_time_is_no_delay(client):
    case(client, [stop("ic", ORIGIN, "08:00"), late("ic", DESTINATION, "09:00", "08:58")])
    check(client, "08:00")
    assert value(client, "delayMinutes") == [0]


def test_a_missing_actual_time_at_the_destination_is_not_measured(client):
    rows = [stop("ic", ORIGIN, "08:00"),
            dict(stop("ic", DESTINATION, "09:00"), an_prognose_status="PROGNOSE"),
            stop("next", ORIGIN, "09:00"), stop("next", DESTINATION, "10:00")]
    case(client, rows)
    check(client, "08:00")
    # The next train would suggest an hour's delay, but the plan's own arrival
    # is not on record: the rules refuse to guess upwards.
    assert value(client, "delayMeasured") == []
    assert value(client, "notMeasured") == ["the planned train's arrival at the destination has no recorded actual time"]


def test_departures_outside_the_window_are_not_offered(client):
    case(client, [stop("early", ORIGIN, "07:00"), stop("early", DESTINATION, "08:00"),
                  stop("ic", ORIGIN, "08:10"), stop("ic", DESTINATION, "09:10")])
    assert [d for d, _, _ in departures(client)] == [epoch("08:10")]


def test_a_departure_beaten_by_a_later_one_is_not_offered(client):
    # The 08:05 detour arrives after the 08:10 direct train: nobody plans it.
    case(client, [stop("slow", ORIGIN, "08:05"), stop("slow", VIA, "08:30"),
                  stop("back", VIA, "08:40"), stop("back", DESTINATION, "09:40"),
                  stop("ic", ORIGIN, "08:10"), stop("ic", DESTINATION, "09:10")])
    offered = client.query("?- x[offered(?E) -> ?A] AND ?E[scheduledDepartureEpoch -> ?D].")["bindings"]
    assert [int(r["D"]) for r in offered] == [epoch("08:10")]
