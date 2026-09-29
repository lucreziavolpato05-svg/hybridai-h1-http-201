// SBB passenger-rail ontology and derived rules.
// The API ingestion layer provides base facts; this file owns semantics.

world open.

// Base classes supplied by the SBB datasets.
StopPoint { designation: String }.
Platform { platformNumber: String, platformLength: Float }.
SectorBoard { trackNumber: String, sectorFront: String }.
WaitingHall { status: String }.
Line { label: String }.
Canton {}.
Mode {}.
Journey {}.
StopEvent { category: String }.
LongDistanceCategory { label: String }.

// Compatibility with the initial ingestion sample.
?S:StopPoint <- ?S:Station.
?S[designation -> ?N] <- ?S:Station[name -> ?N].
// Compatibility with the platform ingestion field names.
?P[atStopPoint -> ?S] <- ?P:Platform[station -> ?S].
?P[platformNumber -> ?N] <- ?P:Platform[number -> ?N].
?P[platformLength -> ?L] <- ?P:Platform[structuralLengthM -> ?L].

// Derived classes.
LongPlatform extends Platform.
LongDistanceStation extends StopPoint.
Junction extends StopPoint.
Interchange extends StopPoint.
BusyStation extends StopPoint.
WellEquippedStation extends StopPoint.
BigHub extends StopPoint.

// Property characteristics and required fields.
declare functional designation.
declare functional hasWifi.
declare functional platformLength.
declare functional platformNumber.
declare functional inCanton.
declare functional cancelled.
declare functional passesThrough.
declare required StopPoint designation.
declare required Platform platformLength.

// A stop point owns the physical objects that point back to it.
?S[hasPlatform -> ?P] <- ?P:Platform[atStopPoint -> ?S].
?S[hasSectorBoard -> ?B] <- ?B:SectorBoard[atStopPoint -> ?S].

// Platform length is measured in metres.
?P:LongPlatform <- ?P:Platform[platformLength -> ?L] AND ?L > 320.
?S[hasLongPlatform -> true] <- ?S[hasPlatform -> ?P] AND ?P:LongPlatform.

// Waiting-hall status values are supplied by the SBB source dataset.
?S[hasWaitingHall -> true] <- ?F:WaitingHall[atStopPoint -> ?S; status -> "BESTEHEND"].
?S[hasPlannedWaitingHall -> true] <- ?F:WaitingHall[atStopPoint -> ?S; status -> "PROJEKTIERT NEU"].

// Daily passenger volume by year. The source supplies observedFrequency(year).
?S[busyIn(?Y) -> true] <- ?S[observedFrequency(?Y) -> ?V] AND ?V > 20000.
?S:BusyStation <- ?S[busyIn(?Y) -> true].

// An event is an actual stop only when it was neither cancelled nor a pass-through.
?E[actuallyStops -> true] <- ?E:StopEvent[cancelled -> false; passesThrough -> false].
?S[servedByCategory -> ?C] <- ?E:StopEvent[atStopPoint -> ?S; category -> ?C; actuallyStops -> true].

// Transport modes are asserted positively by the service-point dataset.
?S:Interchange <- ?S[servesMode -> mode_train] AND ?S[servesMode -> mode_tram].

// A junction has two distinct served lines.
?S:Junction <- ?S[servedByLine -> ?L1] AND ?S[servedByLine -> ?L2] AND ?L1 != ?L2.

// Long-distance categories are declared as LongDistanceCategory facts.
?S:LongDistanceStation <- ?S[servedByCategory -> ?C] AND ?K:LongDistanceCategory[label -> ?C].

// Positive evidence only: under open-world reasoning, missing facilities do not
// imply a negative fact.
?S:WellEquippedStation <- ?S[hasWifi -> true]
    AND ?S[hasWaitingHall -> true]
    AND ?S[hasSectorBoard -> ?B].

// Train-event chain. The ingestion layer supplies nextStop in time order.
?E1[nextActualStop -> ?E2] <- ?E1[nextStop -> ?E2] AND ?E2[actuallyStops -> true].
?E1[nextActualStop -> ?E3] <- ?E1[nextStop -> ?E2]
    AND ?E2[passesThrough -> true]
    AND ?E2[nextActualStop -> ?E3].

// A non-stop link connects two consecutive actual stop points.
?A[nonStopTo -> ?B] <- ?E1[atStopPoint -> ?A; actuallyStops -> true; nextActualStop -> ?E2]
    AND ?E2[atStopPoint -> ?B].
?A[nonStopToLongDistance -> ?B] <- ?A[nonStopTo -> ?B] AND ?B:LongDistanceStation.

// Two non-stop legs, intentionally bounded to one change.
?A[oneChangeTo -> ?C] <- ?A[nonStopTo -> ?B]
    AND ?B[nonStopTo -> ?C]
    AND ?A != ?C.

// A big hub combines the three derived characteristics.
?S:BigHub <- ?S:BusyStation AND ?S:Junction AND ?S:LongDistanceStation.