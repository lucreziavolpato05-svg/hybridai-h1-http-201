"""Adapters between the refund chat and the SBB knowledge base.

The full KB (~1M statements) is far too large to re-derive per chat turn, so
the observed service (70-ist-daten-sbb.fx) is indexed once in Python, by trip
and by stop. Each measure() then loads a small program -- the schema and the
delay rules (00-core, 40-service, 46-refunds) plus only the trips that can
take part in the journey -- into a fresh, short-lived FrameX engine. The
delay itself is still derived by the rules in 46-refunds.fx; Python only
chooses which facts to load and formats the answer.

Trip pruning is sound for the rules in 46-refunds.fx: every planned or actual
connection boards a trip at the origin (direct, or first leg) and, with one
change, alights from a trip at the destination that shares a stop with the
first one. Time bounds mirror the rules' own limits (maxStartWait,
maxJourney) with the origin window.
"""
import json
import re
import threading
import time as _time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ontology.ids import fold_name
from ontology.service import timestamp
from runtime.client import Client
from runtime.source import CHUNK_BYTES, _program_chunks

DAY = "2026-11-07"
WINDOW = 30 * 60  # departures within ±30 min of the stated time count as "the passenger's train"
RULE_FILES = ["00-core.fx", "40-service.fx", "46-refunds.fx"]
SERVICE_FILE = "70-ist-daten-sbb.fx"
SPINE_FILE = "60-spine.fx"
DEFAULT_FILES = RULE_FILES + [SPINE_FILE, SERVICE_FILE]
START_WAIT = 3 * 3600  # refundSearch maxStartWait
JOURNEY = 4 * 3600  # refundSearch maxJourney
KEPT_CASES = 32  # small programs kept for explain_delay

_SUBJECT = re.compile(r"^([A-Za-z]\w*)")
_SLOT = re.compile(r"^(\w+)\[(\w+) -> (.*)\]\.\s*$")
_DESIGNATION = re.compile(r'^sp_(\d+)\[designation -> (".*")\]\.\s*$')
_EVENT_SLOTS = {"atStopPoint": 1, "scheduledDepartureEpoch": 2, "scheduledArrivalEpoch": 3,
                "departureEpoch": 4, "arrivalEpoch": 5, "stopSequence": 6,
                "rideSegment": 8, "cancelled": 9, "passThrough": 10}
# event record: [trip, stop, sdep, sarr, adep, aarr, seq, id, segment, cancelled, passThrough]
CHANGE_WAIT = 3600  # refundSearch maxChangeWait

def _decode(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value

def _clock(epoch):
    return datetime.fromtimestamp(int(epoch), ZoneInfo("Europe/Zurich")).strftime("%H:%M")

def _load(client, program):
    """Staged load: a single `load` request is capped at 1 MiB."""
    client.load_begin()
    for chunk in _program_chunks(program.splitlines(), limit=CHUNK_BYTES):
        client.load_chunk("\n".join(chunk), record=False)
    client.load_commit()

def _within(value, low, high):
    return value is not None and low <= value <= high

class RefundKB:
    def __init__(self, workspace=Path(__file__).resolve().parents[2] / "fx", files=None):
        started = _time.perf_counter()
        workspace = Path(workspace)
        selected = list(files if files is not None else DEFAULT_FILES)
        self.names = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))["spine"]["names"]
        self.rules = "\n".join((workspace / name).read_text(encoding="utf-8") for name in RULE_FILES if name in selected)
        self.lock = threading.Lock()
        self.counter = 0
        self.cases = OrderedDict()  # case id -> (program, delay minutes)
        self.timings = []  # seconds per engine run, for diagnostics
        self.designations = {}
        if SPINE_FILE in selected:
            with open(workspace / SPINE_FILE, encoding="utf-8") as handle:
                for line in handle:
                    if line.startswith("sp_") and "[designation ->" in line:
                        m = _DESIGNATION.match(line)
                        if m: self.designations.setdefault(int(m.group(1)), _decode(m.group(2)))
        self.trip_lines, self.trip_info, self.events = {}, {}, {}
        self.events_at, self.trip_events, self.event_lines = {}, {}, {}
        if SERVICE_FILE in selected:
            self._index(workspace / SERVICE_FILE)
        self.load_seconds = _time.perf_counter() - started
        print(f"Refund KB indexed in {self.load_seconds:.1f}s ({len(self.trip_info)} trips, {len(self.events)} stop events)")

    # --- index ---------------------------------------------------------

    def _index(self, path):
        trip_lines, event_lines, owner, current = {}, {}, {}, None
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                if not line.startswith(("trip_", "ev_", "segment_")):
                    continue
                line = line.rstrip("\n")
                subject = _SUBJECT.match(line).group(1)
                if subject.startswith("trip_"):
                    if line.endswith(":Trip."):
                        current = subject
                    trip = subject
                else:
                    trip = owner.get(subject, current)
                m = _SLOT.match(line)
                if m:
                    _, slot, value = m.groups()
                    if slot == "ofTrip" and not subject.startswith("trip_"):
                        trip = owner[subject] = value
                    if subject.startswith("trip_"):
                        if slot in ("serviceCategory", "lineText"):
                            self.trip_info.setdefault(subject, {})[slot] = _decode(value)
                    elif subject.startswith("ev_"):
                        event = self.events.setdefault(subject, [trip, None, None, None, None, None, None, subject, None, None, None])
                        if slot == "ofTrip":
                            event[0] = value
                        elif slot in _EVENT_SLOTS:
                            index = _EVENT_SLOTS[slot]
                            event[index] = value if index in (1, 8) else (value == "true") if index > 8 else int(value)
                if subject.startswith("ev_"):
                    event_lines.setdefault(subject, []).append(line)
                elif trip is not None:
                    trip_lines.setdefault(trip, []).append(line)
        self.trip_lines = {trip: "\n".join(chunk) for trip, chunk in trip_lines.items()}
        self.event_lines = {event: "\n".join(chunk) for event, chunk in event_lines.items()}
        for record in self.events.values():
            trip, stop = record[0], record[1]
            if stop is None or trip is None: continue
            self.trip_info.setdefault(trip, {})
            self.events_at.setdefault(stop, []).append(record)
            self.trip_events.setdefault(trip, []).append(record)

    def _label(self, trip):
        info = self.trip_info.get(trip, {})
        return " ".join(str(info[k]) for k in ("serviceCategory", "lineText") if info.get(k))

    def _select(self, origin, destination, plan=None, real=None, board=None, until=None):
        """The trips and stop events the joins in 46-refunds.fx can use.

        plan  (low, high): planned connections of a RefundCase window
              (pc0/pc1, plannedFeeds); with `board` only those of that
              event: plannedArrival(E) is a minimum over E's own connections.
        real  planned departure D0 of a DelayCheck: actual legs (actualBoard
              within maxStartWait, al0/al1, actualFeeds).
        A superset, mirroring the rules' own bounds: a first trip leaves the
        origin; it reaches the destination later, or reaches a stop V from
        which a second trip leaves within maxChangeWait of that arrival and
        then reaches the destination within the journey bound. Only events
        at the origin, the destination and such change stops can join, so
        only those are loaded. A train that connects to nothing derives no
        connection and is left out.
        """
        # until: the earliest actual arrival is at most this (see _first_arrival);
        # a leg boarding or arriving later cannot change the minimum.
        start_until = real + START_WAIT if real is not None else None
        end_until = real + START_WAIT + JOURNEY if real is not None else None
        if until is not None and real is not None:
            start_until, end_until = min(start_until, until), min(end_until, until)
        def leaves(sdep, adep, ev):
            return bool(plan and (ev == board if board else _within(sdep, plan[0], plan[1]))) or bool(real is not None and _within(adep, real, start_until))
        def arrives(sarr, aarr):
            return bool(plan and _within(sarr, plan[0], plan[1] + JOURNEY)) or bool(real is not None and _within(aarr, real, end_until))
        def changes(sarr, aarr, sdep, adep):
            return bool(plan and sarr is not None and _within(sdep, sarr, sarr + CHANGE_WAIT)) or \
                bool(real is not None and aarr is not None and _within(adep, aarr, aarr + CHANGE_WAIT))
        first = {}  # trip -> sequence number of its first stop at the origin
        for trip, _stop, sdep, _sarr, adep, _aarr, seq, ev, *_x in self._events_at(origin):
            if seq is None: continue
            if leaves(sdep, adep, ev):
                first[trip] = min(seq, first.get(trip, seq))
        last = {}  # trip -> its last stop sequence at the destination
        for trip, _stop, _sdep, sarr, _adep, aarr, seq, _ev, *_x in self._events_at(destination):
            if seq is not None and arrives(sarr, aarr):
                last[trip] = max(seq, last.get(trip, seq))
        departures = {}  # change stop -> [(trip, planned departure, actual departure)]
        for trip, end in last.items():
            for _t, stop, sdep, _sarr, adep, _aarr, k, _ev, *_x in self.trip_events[trip]:
                if k is not None and k < end and stop not in (origin, destination):
                    departures.setdefault(stop, []).append((trip, sdep, adep))
        trips, stops = set(), {origin, destination}
        for trip, start in first.items():
            if trip in last and last[trip] > start:
                trips.add(trip)
            for _t, stop, _sdep, sarr, _adep, aarr, seq, _ev, *_x in self.trip_events[trip]:
                if seq is None or seq <= start or stop not in departures: continue
                for second, sdep, adep in departures[stop]:
                    if second != trip and changes(sarr, aarr, sdep, adep):
                        trips.update((trip, second))
                        stops.add(stop)
        events = [e[7] for t in sorted(trips) for e in self.trip_events[t] if e[1] in stops]
        return sorted(trips), events

    def _first_arrival(self, origin, destination, real):
        """An upper bound on the earliest actual arrival: the earliest direct
        REAL leg (al0's conditions: reported stops on one ride segment)."""
        best = None
        for trip, _stop, _sdep, _sarr, adep, _aarr, seq, _ev, segment, cancelled, passing in self._events_at(origin):
            if cancelled is not False or passing is not False or segment is None or seq is None or not _within(adep, real, real + START_WAIT):
                continue
            for _t, stop, _a, _b, _c, aarr, k, _e, seg, can, pas in self.trip_events[trip]:
                if stop == destination and seg == segment and can is False and pas is False and k is not None and k > seq and aarr is not None:
                    best = aarr if best is None else min(best, aarr)
        return best

    def _events_at(self, stop):
        return self.events_at.get(stop, [])

    def _program(self, trips, events, extra):
        stops = {self.events[e][1] for e in events}
        spine = [f"{stop}:StopPoint. {stop}[bpuic -> {stop[3:]}]." for stop in sorted(stops) if int(stop[3:]) in self.designations]
        return "\n".join([self.rules, "\n".join(spine), "\n".join(self.trip_lines[t] for t in trips if t in self.trip_lines),
                          "\n".join(self.event_lines[e] for e in events), extra]) + "\n"

    # --- public API ----------------------------------------------------

    def station(self, name):
        key = fold_name(name)
        if key not in self.names:
            return {"status": "unknown"}
        number = self.names[key]
        if number is None:
            return {"status": "ambiguous"}
        return {"status": "found", "stop": f"sp_{number}", "designation": self.designations.get(int(number), name)}

    def measure(self, origin, destination, date, time, choice=None):
        if date != DAY:
            return {"status": "outOfScope", "day": DAY}
        if not all(re.fullmatch(r"sp_\d+", s) for s in (origin, destination)):
            raise ValueError("invalid stop id")
        wanted = None
        if choice is not None:
            m = re.fullmatch(r"\s*(\d{2}:\d{2})(?:\s+(.*\S))?\s*", str(choice))
            if not m: raise ValueError("invalid time")
            wanted = (m.group(1), (m.group(2) or "").lower())
        if not re.fullmatch(r"\d{2}:\d{2}", time):
            raise ValueError("invalid time")
        stated = timestamp(f"{date}T{time}:00")
        if stated is None:
            raise ValueError("invalid time")
        low, high = stated - WINDOW, stated + WINDOW
        with self.lock:
            self.counter += 1
            x, y = f"x_{self.counter}", f"y_{self.counter}"
        case = (f'{x}:RefundCase[origin -> {origin}; destination -> {destination}; onDay -> "{DAY}"; '
                f'windowFrom -> {low}; windowTo -> {high}; transferSeconds -> 300].')
        started = _time.perf_counter()
        try:
            # 1) The departures the rules offer for the window (planned times only).
            trips, events = self._select(origin, destination, plan=(low, high))
            if not trips:
                return {"status": "noTrain"}
            found = self._run(self._program(trips, events, case),
                              f"?- {x}[offered(?E) -> ?A; plannedChanges(?E) -> ?C] AND ?E[scheduledDepartureEpoch -> ?D].")
            candidates, seen = [], set()
            for r in sorted(found, key=lambda r: (int(r["D"]), int(r["A"]), r["E"])):
                event = r["E"]
                row = {"departure": _clock(r["D"]), "arrival": _clock(r["A"]), "changes": int(r["C"])}
                label = self._label(self.events[event][0] if event in self.events else None)
                if label: row["train"] = label
                change = ", 1 change" if row["changes"] else ""
                row["label"] = f'{row["departure"]} {label or "train"} (arrives {row["arrival"]}{change})'
                key = (row["departure"], row["arrival"], row.get("train"), row["changes"])
                if key in seen: continue
                seen.add(key)
                candidates.append((event, row))
            if not candidates:
                return {"status": "noTrain"}
            # Each offered row gets a unique choice key: the departure, or departure + train
            # when two trains leave in the same minute (so the passenger can tell them apart).
            per_minute = {}
            for _, row in candidates:
                per_minute[row["departure"]] = per_minute.get(row["departure"], 0) + 1
            for _, row in candidates:
                dep = row["departure"]
                row["key"] = dep if per_minute[dep] == 1 else f'{dep} {row.get("train", "")}'.strip()
            if wanted:
                selected = [c for c in candidates if c[1]["departure"] == wanted[0]
                            and (not wanted[1] or wanted[1] == c[1].get("train", "").lower())]
                if not selected and wanted[1]:
                    selected = [c for c in candidates if c[1]["departure"] == wanted[0]
                                and wanted[1] in c[1].get("train", "").lower()]
                if not selected:
                    return {"status": "ambiguous", "rows": [c[1] for c in candidates][:64]}
            else:
                selected = candidates
            if len(selected) != 1:
                return {"status": "ambiguous", "rows": [c[1] for c in selected][:64]}
            event, row = selected[0]
            # 2) The passenger's train: its planned connections and what really ran.
            real = self.events[event][2]
            trips, events = self._select(origin, destination, plan=(low, high), real=real, board=event,
                                         until=self._first_arrival(origin, destination, real))
            check = f"{y}:DelayCheck[checkOf -> {x}; plannedBoard -> {event}]."
            program = self._program(trips, events, case + "\n" + check)
            slots = ("notMeasured", "delayMinutes", "plannedDeparture", "plannedArrival", "actualArrival", "actualChanges", "planCancelled")
            values = self._run(program, *[f"?- {y}[{name} -> ?V]." for name in slots])
            values = dict(zip(slots, ([_decode(b["V"]) for b in found] for found in values)))
            if values["notMeasured"]:
                return {"status": "notMeasured", "reason": values["notMeasured"][0]}
            result = {"status": "measured", "caseId": y}
            for name in slots[1:-1]:
                if not values[name]: raise ValueError(f"missing KB value: {name}")
                result[name] = _clock(values[name][0]) if name in ("plannedDeparture", "plannedArrival", "actualArrival") else int(values[name][0])
            result["plannedChanges"] = row["changes"]  # x[plannedChanges(E)]: the rules keep it per case
            result["cancelled"] = True in values["planCancelled"]
            if "train" in row: result["train"] = row["train"]
            with self.lock:
                self.cases[y] = (program, result["delayMinutes"])
                while len(self.cases) > KEPT_CASES: self.cases.popitem(last=False)
            return result
        finally:
            self._timed(started)

    def _run(self, program, *queries):
        with Client(request_timeout=300, retain_transcript=False) as client:
            _load(client, program)
            answers = [client.query(q).get("bindings", []) for q in queries]
        return answers[0] if len(queries) == 1 else answers

    def _timed(self, started):
        with self.lock:
            self.timings.append(_time.perf_counter() - started)

    def explain_delay(self, case_id):
        if not re.fullmatch(r"y_\d+", case_id): raise ValueError("invalid case id")
        with self.lock:
            kept = self.cases.get(case_id)
        if kept is None:
            return ""
        program, minutes = kept
        try:
            with Client(request_timeout=300, retain_transcript=False) as client:
                _load(client, program)
                return client.explain(f"{case_id}[delayMinutes -> {minutes}]")
        except Exception:
            return ""

    def close(self):
        """Nothing persistent to close: every engine is short-lived."""

def tools(kb):
    def station(p):
        if "name" not in p: raise ValueError("missing name")
        return kb.station(p["name"]), {"source": "KB spine"}
    def measure(p):
        if any(k not in p for k in ("origin", "destination", "date", "time")): raise ValueError("missing parameter")
        return kb.measure(p["origin"], p["destination"], p["date"], p["time"], p.get("choice")), {"source": "SBB data 2026-11-07"}
    return {"_station": station, "_measure": measure}
