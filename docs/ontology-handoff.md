# Ontology Handoff for the Reference Queries

The canonical ontology is [ontology.fx](../ontology.fx). It implements the
classes and rules from the handwritten ontology and is intentionally open-world.
The API layer must emit the base facts below. Rules should not be used to guess
missing source records. DiDok, WiFi, and platform adapters now share the
`station_<full UIC/BPUIC>` identity. All eight adapters are now integrated. See
[verification.md](verification.md) for current coverage and validation, and
[README](../README.md) for current commands. DiDok owns canonical designation;
the legacy name alias is opt-in, and the source-name conflict is resolved.

## Dataset-to-fact mapping

| SBB dataset | Required base facts | Queries |
| --- | --- | --- |
| Service Points (Didok) | `station_<didok>:StopPoint`, `designation`, `inCanton`, `servesMode` | 1.3, 2.1, 2.4, 2.5, 3.1, 3.5 |
| Wifi@Station | `station_<didok>[hasWifi -> true]` | 1.1, 1.7, 2.1 |
| Stop: platform length (body) | `platform_<fid>:Platform`, `atStopPoint`, `platformNumber`, `platformLength` | 1.2, 2.2 |
| Stop: waiting rooms | `waitinghall_<id>:WaitingHall`, `atStopPoint`, `status` | 1.3, 2.4, 2.5 |
| Target/Actual Comparison | `StopEvent`, `atStopPoint`, `category`, `cancelled`, `passesThrough`, `nextStop` | 1.4, 1.6, 1.7, 3.3, 3.4 |
| Ein- und Aussteigende an Bahnhöfen | `observedFrequency(<year>)` | 1.5, 2.6, 3.2 |
| Line (Operation Points) | `line_<label>:Line`, `label`, `servedByLine` | 2.6, 3.1 |
| SBB route network | route/line labels used to complete line identity mappings | 3.1 |

## Exact fact shapes

```text
station_8509000:StopPoint.
station_8509000[designation -> "Chur"].
station_8509000[inCanton -> canton_gr].
station_8509000[servesMode -> mode_train].

platform_1:Platform.
platform_1[atStopPoint -> station_8503000].
platform_1[platformNumber -> "10/11"].
platform_1[platformLength -> 425.0].

waitinghall_1:WaitingHall.
waitinghall_1[atStopPoint -> station_8503000].
waitinghall_1[status -> "BESTEHEND"].

station_8509000[observedFrequency("2024") -> 28500.0].
line_900:Line.
line_900[label -> "900"].
station_8509000[servedByLine -> line_900].

event_1:StopEvent.
event_1[atStopPoint -> station_8507000].
event_1[category -> "IC"].
event_1[cancelled -> false].
event_1[passesThrough -> false].
event_1[nextStop -> event_2].
```

Object references must be unquoted. Quote names, categories, statuses, and
platform numbers. Passenger counts and platform lengths are numeric values.
The final acceptance contract uses string years: `observedFrequency("2024")`.
Integration tests confirm that `2024` and `"2024"` are distinct values and
must match the query's type. Use full UIC/BPUIC for `station_...`; do not key joins
on display names or short DiDok numbers.

The current `perron` emitter uses `station`, `number`, and `structuralLengthM`.
`ontology.fx` includes aliases for those fields, so the platform query already
works with that emitter. New datasets should emit the canonical names above.

## Query coverage

- Level 1: direct WiFi, platform, waiting-hall, event-category, passenger-count,
  and non-stop lookups.
- Level 2: WiFi/canton, long-platform, sector-board, waiting-hall status, and
  line/passenger-count joins.
- Level 3: junction, historical passenger comparison, long-distance non-stop
  destinations, TGV service, and train/tram interchange.

Query 1.7 is deliberately expected to remain `unknown`: under open-world
reasoning, a missing WiFi record does not prove `hasWifi -> false`.

The previous-day event dataset is time-dependent. Every event fact should carry
its operating date or snapshot metadata so results can be compared fairly with
the reference answers from 27 September 2026.
