"""Persistent adapters for the SBB refund knowledge base."""
import json
import re
import shutil
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ontology.ids import fold_name
from ontology.service import timestamp
from runtime.session import Session

DAY = "2026-11-07"
WINDOW = 15 * 60  # departures within ±15 min of the stated time count as "the passenger's train"
DEFAULT_FILES = ["00-core.fx", "40-service.fx", "46-refunds.fx", "60-spine.fx", "70-ist-daten-sbb.fx"]

def _decode(value):
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value

def _clock(epoch):
    return datetime.fromtimestamp(int(epoch), ZoneInfo("Europe/Zurich")).strftime("%H:%M")

class RefundKB:
    def __init__(self, workspace=Path(__file__).resolve().parents[2] / "fx", files=None):
        workspace = Path(workspace)
        self.names = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))["spine"]["names"]
        self.lock = threading.Lock()
        self.counter = 0
        selected = set(files if files is not None else DEFAULT_FILES)
        class FilteredSession(Session):
            def _load(self):
                self.files = [path for path in self.files if path.name in selected]
                super()._load()
        self.session = FilteredSession(workspace)
        print(f"Refund KB loaded in {self.session.load_seconds:.1f}s")

    def _ask(self, query):
        return self.session.ask(query)[0].get("bindings", [])

    def _slot(self, obj, slot):
        return [_decode(r["V"]) for r in self._ask(f"?- {obj}[{slot} -> ?V].")]

    def station(self, name):
        key = fold_name(name)
        if key not in self.names:
            return {"status": "unknown"}
        number = self.names[key]
        if number is None:
            return {"status": "ambiguous"}
        stop = f"sp_{number}"
        with self.lock:
            names = self._slot(stop, "designation")
        return {"status": "found", "stop": stop, "designation": names[0] if names else name}

    def measure(self, origin, destination, date, time, choice=None):
        if date != DAY:
            return {"status": "outOfScope", "day": DAY}
        if not all(re.fullmatch(r"sp_\d+", s) for s in (origin, destination)):
            raise ValueError("invalid stop id")
        if not re.fullmatch(r"\d{2}:\d{2}", time) or (choice is not None and not re.fullmatch(r"\d{2}:\d{2}", choice)):
            raise ValueError("invalid time")
        stated = timestamp(f"{date}T{time}:00")
        if stated is None:
            raise ValueError("invalid time")
        with self.lock:
            self.counter += 1
            x, y = f"x_{self.counter}", f"y_{self.counter}"
            self.session.client.add(source=f'{x}:RefundCase[origin -> {origin}; destination -> {destination}; onDay -> "{DAY}"; windowFrom -> {stated-WINDOW}; windowTo -> {stated+WINDOW}; transferSeconds -> 300].')
            found = self._ask(f"?- {x}[offered(?E) -> ?A; plannedChanges(?E) -> ?C] AND ?E[scheduledDepartureEpoch -> ?D].")
            candidates = []
            for r in found:
                event = r["E"]
                trips = self._slot(event, "ofTrip")
                label = ""
                if trips:
                    label = " ".join(str(v[0]) for v in (self._slot(trips[0], "serviceCategory"), self._slot(trips[0], "lineText")) if v)
                row = {"departure": _clock(r["D"]), "arrival": _clock(r["A"]), "changes": int(r["C"])}
                if label: row["train"] = label
                candidates.append((int(r["D"]), event, row))
            candidates.sort(key=lambda item: (item[0], item[1]))
            # One row per planned departure: the same train can be offered via several events.
            unique = {}
            for item in candidates:
                unique.setdefault(item[2]["departure"], item)
            candidates = list(unique.values())
            if not candidates: return {"status": "noTrain"}
            selected = [c for c in candidates if c[2]["departure"] == choice] if choice else candidates
            if len(selected) != 1:
                return {"status": "ambiguous", "rows": [c[2] for c in candidates][:64]}
            _, event, row = selected[0]
            self.session.client.add(source=f"{y}:DelayCheck[checkOf -> {x}; plannedBoard -> {event}].")
            reasons = self._slot(y, "notMeasured")
            if reasons: return {"status": "notMeasured", "reason": reasons[0]}
            result = {"status": "measured", "caseId": y}
            for slot, output in [("delayMinutes", "delayMinutes"), ("plannedDeparture", "plannedDeparture"), ("plannedArrival", "plannedArrival"), ("actualArrival", "actualArrival"), ("plannedChanges", "plannedChanges"), ("actualChanges", "actualChanges")]:
                values = self._slot(y, slot)
                if not values: raise ValueError(f"missing KB value: {slot}")
                result[output] = _clock(values[0]) if slot in ("plannedDeparture", "plannedArrival", "actualArrival") else int(values[0])
            result["cancelled"] = True in self._slot(y, "planCancelled")
            if "train" in row: result["train"] = row["train"]
            return result

    def explain_delay(self, case_id):
        if not re.fullmatch(r"y_\d+", case_id): raise ValueError("invalid case id")
        with self.lock:
            try: return self.session.explain(f"{case_id}[delayMinutes -> M]")
            except Exception: return ""

def tools(kb):
    def station(p):
        if "name" not in p: raise ValueError("missing name")
        return kb.station(p["name"]), {"source": "KB spine"}
    def measure(p):
        if any(k not in p for k in ("origin", "destination", "date", "time")): raise ValueError("missing parameter")
        return kb.measure(p["origin"], p["destination"], p["date"], p["time"], p.get("choice")), {"source": "SBB data 2026-11-07"}
    return {"_station": station, "_measure": measure}
