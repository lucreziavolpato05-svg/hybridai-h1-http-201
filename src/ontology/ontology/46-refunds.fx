// ====================================================================
// Delays at the destination: what was planned, what really ran
//
// A refund under Swiss passenger rights depends on the delay at the
// destination of the journey, not on the delay of one train: a late
// first train can cost the connection. Two requests, both from the host:
//
//   RefundCase   origin, destination, operating day and a window of
//                planned departure times around the time the passenger
//                names. The rules derive the planned connections.
//   DelayCheck   one planned boarding event of a case: the passenger's
//                train. The rules derive what really happened from it.
//
//   PlannedConnection  scheduled times; cancelled trains count, they were
//                      planned. Direct, or with one change when the
//                      boarded train does not reach the destination.
//   ActualLeg          REAL times only, as in 40-service.fx: the ways the
//                      passenger could really have travelled, boarding at
//                      the origin no earlier than the planned departure.
//   delay              earliest actual arrival - planned arrival.
//
// Whether a delay earns a refund is not decided here: the chat's rules
// (pipeline/programs/refund.fx) hold the passenger-rights policy.
// ====================================================================

// No change waits longer than an hour; the passenger boards at most three
// hours after the planned departure; a journey takes at most four hours.
refundSearch[maxChangeWait -> 3600; maxStartWait -> 10800; maxJourney -> 14400].

RefundCase { origin: StopPoint, destination: StopPoint, onDay: String,
             windowFrom: Integer, windowTo: Integer, transferSeconds: Integer }.
declare required RefundCase origin.
declare required RefundCase destination.
declare required RefundCase onDay.
declare required RefundCase windowFrom.
declare required RefundCase windowTo.
declare required RefundCase transferSeconds.

DelayCheck { checkOf: RefundCase, plannedBoard: StopEvent }.
declare required DelayCheck checkOf.
declare required DelayCheck plannedBoard.

// --------------------------------------------------------------------
// Planned connections (the timetable)
// --------------------------------------------------------------------
PlannedConnection { connOf: RefundCase, connBoard: StopEvent, connAlight: StopEvent,
                    connDeparture: Integer, connArrival: Integer,
                    connChanges: Integer, connVia: StopPoint }.
closed class PlannedConnection.
closed slot connOf. closed slot connBoard. closed slot connAlight.
closed slot connDeparture. closed slot connArrival. closed slot connChanges.

pc0(?X, ?E, ?F):PlannedConnection[connOf -> ?X; connBoard -> ?E; connAlight -> ?F;
        connDeparture -> ?D; connArrival -> ?A; connChanges -> 0]
    <- ?X:RefundCase[origin -> ?O; destination -> ?S; onDay -> ?Day; windowFrom -> ?Lo; windowTo -> ?Hi]
    AND ?E[atStopPoint -> ?O] AND ?E[passThrough -> false]
    AND ?E[scheduledDepartureEpoch -> ?D] AND ?D >= ?Lo AND ?D <= ?Hi
    AND ?E[ofTrip -> ?T] AND ?T[observedOn -> ?Day] AND ?E[stopSequence -> ?I]
    AND ?F[ofTrip -> ?T] AND ?F[atStopPoint -> ?S] AND ?F[passThrough -> false]
    AND ?F[stopSequence -> ?J] AND ?I < ?J AND ?F[scheduledArrivalEpoch -> ?A].

// The same conditions without the class: a change is searched only from a
// train that does not reach the destination itself, and that test must
// read a completed stratum, not PlannedConnection, which it helps derive.
closed method directFrom/1.
?X[directFrom(?E) -> true]
    <- ?X:RefundCase[origin -> ?O; destination -> ?S; onDay -> ?Day; windowFrom -> ?Lo; windowTo -> ?Hi]
    AND ?E[atStopPoint -> ?O] AND ?E[passThrough -> false]
    AND ?E[scheduledDepartureEpoch -> ?D] AND ?D >= ?Lo AND ?D <= ?Hi
    AND ?E[ofTrip -> ?T] AND ?T[observedOn -> ?Day] AND ?E[stopSequence -> ?I]
    AND ?F[ofTrip -> ?T] AND ?F[atStopPoint -> ?S] AND ?F[passThrough -> false]
    AND ?F[stopSequence -> ?J] AND ?I < ?J AND ?F[scheduledArrivalEpoch -> ?A].

// Stops from which a planned train still reaches the destination within
// the journey bound. Starting from the destination keeps the change join
// to the trains that matter.
?X[plannedFeeds(?V) -> ?H] <- ?X:RefundCase[destination -> ?S; onDay -> ?Day; windowFrom -> ?Lo; windowTo -> ?Hi]
    AND refundSearch[maxJourney -> ?MJ] AND ?Last := ?Hi + ?MJ
    AND ?F[atStopPoint -> ?S] AND ?F[passThrough -> false]
    AND ?F[scheduledArrivalEpoch -> ?A] AND ?A >= ?Lo AND ?A <= ?Last
    AND ?F[ofTrip -> ?T] AND ?T[observedOn -> ?Day] AND ?F[stopSequence -> ?J]
    AND ?H[ofTrip -> ?T] AND ?H[passThrough -> false] AND ?H[stopSequence -> ?K] AND ?K < ?J
    AND ?H[atStopPoint -> ?V].

pc1(?X, ?E, ?G, ?H, ?F):PlannedConnection[connOf -> ?X; connBoard -> ?E; connAlight -> ?F;
        connDeparture -> ?D; connArrival -> ?A; connChanges -> 1; connVia -> ?V]
    <- ?X:RefundCase[origin -> ?O; destination -> ?S; onDay -> ?Day; windowFrom -> ?Lo;
        windowTo -> ?Hi; transferSeconds -> ?TS]
    AND ?E[atStopPoint -> ?O] AND ?E[passThrough -> false]
    AND ?E[scheduledDepartureEpoch -> ?D] AND ?D >= ?Lo AND ?D <= ?Hi
    AND ?E[ofTrip -> ?T1] AND ?T1[observedOn -> ?Day]
    AND NOT ?X[directFrom(?E) -> true] AND ?E[stopSequence -> ?I]
    AND ?G[ofTrip -> ?T1] AND ?G[passThrough -> false] AND ?G[stopSequence -> ?I2] AND ?I < ?I2
    AND ?G[atStopPoint -> ?V] AND ?V != ?S AND ?V != ?O AND ?G[scheduledArrivalEpoch -> ?GA]
    AND ?Ready := ?GA + ?TS AND refundSearch[maxChangeWait -> ?W] AND ?Latest := ?GA + ?W
    AND ?X[plannedFeeds(?V) -> ?H] AND ?H[scheduledDepartureEpoch -> ?HD]
    AND ?HD >= ?Ready AND ?HD <= ?Latest
    AND ?H[ofTrip -> ?T2] AND ?T1 != ?T2 AND ?H[stopSequence -> ?K]
    AND ?F[ofTrip -> ?T2] AND ?F[atStopPoint -> ?S] AND ?F[passThrough -> false]
    AND ?F[stopSequence -> ?J] AND ?K < ?J AND ?F[scheduledArrivalEpoch -> ?A].

// Per boarding event: the earliest planned arrival, and the fewest changes
// that reach it. These are the departures the chat offers the passenger.
?X[plannedArrival(?E) -> ?M] <- ?C:PlannedConnection[connOf -> ?X; connBoard -> ?E]
    AND ?M := min{?A | ?K:PlannedConnection[connOf -> ?X; connBoard -> ?E; connArrival -> ?A]}.
?X[plannedChanges(?E) -> ?N] <- ?X[plannedArrival(?E) -> ?A]
    AND ?N := min{?C | ?K:PlannedConnection[connOf -> ?X; connBoard -> ?E; connArrival -> ?A;
                                            connChanges -> ?C]}.

// A departure no passenger would plan is not offered: one that a departure
// leaving no earlier beats by arriving earlier (a train the other way and
// back, a slow detour). Measuring against it would only flatter the delay.
closed method outrunBoard/1.
?X[outrunBoard(?E) -> true] <- ?X[plannedArrival(?E) -> ?A] AND ?E[scheduledDepartureEpoch -> ?D]
    AND ?X[plannedArrival(?E2) -> ?A2] AND ?E2[scheduledDepartureEpoch -> ?D2]
    AND ?D2 >= ?D AND ?A2 < ?A.
?X[offered(?E) -> ?A] <- ?X[plannedArrival(?E) -> ?A] AND NOT ?X[outrunBoard(?E) -> true].

// --------------------------------------------------------------------
// The passenger's plan
// --------------------------------------------------------------------
?Y[plannedDeparture -> ?D] <- ?Y:DelayCheck[plannedBoard -> ?E] AND ?E[scheduledDepartureEpoch -> ?D].
?Y[plannedArrival -> ?A] <- ?Y:DelayCheck[checkOf -> ?X; plannedBoard -> ?E] AND ?X[plannedArrival(?E) -> ?A].
?C:ChosenPlan <- ?Y:DelayCheck[checkOf -> ?X; plannedBoard -> ?E; plannedArrival -> ?A]
    AND ?C:PlannedConnection[connOf -> ?X; connBoard -> ?E; connArrival -> ?A].
?Y[plan -> ?C] <- ?Y:DelayCheck[checkOf -> ?X; plannedBoard -> ?E; plannedArrival -> ?A]
    AND ?C:ChosenPlan[connOf -> ?X; connBoard -> ?E].

// What became of the plan is on record when its arrival at the destination
// has a REAL time or was cancelled, or its train was cancelled at the
// origin. Without that, a later actual arrival could merely be a gap in
// the reports, and the delay is not measured (never guessed upwards).
closed slot planOnRecord.
?Y[planOnRecord -> true] <- ?Y[plan -> ?C] AND ?C[connAlight -> ?F] AND ?F[arrivalEpoch -> ?A].
?Y[planOnRecord -> true] <- ?Y[plan -> ?C] AND ?C[connAlight -> ?F] AND ?F[cancelled -> true].
?Y[planOnRecord -> true] <- ?Y:DelayCheck[plannedBoard -> ?E] AND ?E[cancelled -> true].
?Y[planCancelled -> true] <- ?Y[plan -> ?C] AND ?C[connAlight -> ?F] AND ?F[cancelled -> true].
?Y[planCancelled -> true] <- ?Y:DelayCheck[plannedBoard -> ?E] AND ?E[cancelled -> true].

// --------------------------------------------------------------------
// What really ran: actual legs from the planned departure on
// --------------------------------------------------------------------
?Y[actualBoard -> ?B] <- ?Y:DelayCheck[checkOf -> ?X; plannedDeparture -> ?D0]
    AND ?X:RefundCase[origin -> ?O; onDay -> ?Day]
    AND refundSearch[maxStartWait -> ?MW] AND ?Lim := ?D0 + ?MW
    AND ?B[atStopPoint -> ?O] AND ?B:ReportedStop AND ?B[departureEpoch -> ?D]
    AND ?D >= ?D0 AND ?D <= ?Lim AND ?B[ofTrip -> ?T] AND ?T[observedOn -> ?Day]
    AND ?B[rideSegment -> ?Seg].

?Y[actualFeeds(?V) -> ?H] <- ?Y:DelayCheck[checkOf -> ?X; plannedDeparture -> ?D0]
    AND ?X:RefundCase[destination -> ?S; onDay -> ?Day]
    AND refundSearch[maxStartWait -> ?MW; maxJourney -> ?MJ] AND ?Last := ?D0 + ?MW + ?MJ
    AND ?F[atStopPoint -> ?S] AND ?F:ReportedStop
    AND ?F[arrivalEpoch -> ?A] AND ?A >= ?D0 AND ?A <= ?Last
    AND ?F[rideSegment -> ?Seg] AND ?F[stopSequence -> ?J]
    AND ?F[ofTrip -> ?T] AND ?T[observedOn -> ?Day]
    AND ?H[rideSegment -> ?Seg] AND ?H:ReportedStop AND ?H[stopSequence -> ?K]
    AND ?K < ?J AND ?H[atStopPoint -> ?V].

ActualLeg { legCheck: DelayCheck, alBoard: StopEvent, alAlight: StopEvent,
            alDeparture: Integer, alArrival: Integer, alChanges: Integer, alVia: StopPoint }.
closed class ActualLeg.
closed slot legCheck. closed slot alBoard. closed slot alAlight.
closed slot alDeparture. closed slot alArrival. closed slot alChanges.

al0(?Y, ?B, ?F):ActualLeg[legCheck -> ?Y; alBoard -> ?B; alAlight -> ?F;
        alDeparture -> ?D; alArrival -> ?A; alChanges -> 0]
    <- ?Y[actualBoard -> ?B] AND ?Y[checkOf -> ?X] AND ?X[destination -> ?S]
    AND ?B[rideSegment -> ?Seg] AND ?B[stopSequence -> ?I] AND ?B[departureEpoch -> ?D]
    AND ?F[rideSegment -> ?Seg] AND ?F[atStopPoint -> ?S] AND ?F:ReportedStop
    AND ?F[stopSequence -> ?J] AND ?I < ?J AND ?F[arrivalEpoch -> ?A].

al1(?Y, ?B, ?G, ?H, ?F):ActualLeg[legCheck -> ?Y; alBoard -> ?B; alAlight -> ?F;
        alDeparture -> ?D; alArrival -> ?A; alChanges -> 1; alVia -> ?V]
    <- ?Y[actualBoard -> ?B] AND ?Y[checkOf -> ?X]
    AND ?X[origin -> ?O; destination -> ?S; transferSeconds -> ?TS]
    AND ?B[rideSegment -> ?Seg1] AND ?B[stopSequence -> ?I]
    AND ?B[departureEpoch -> ?D] AND ?B[ofTrip -> ?T1]
    AND ?G[rideSegment -> ?Seg1] AND ?G:ReportedStop
    AND ?G[stopSequence -> ?I2] AND ?I < ?I2
    AND ?G[atStopPoint -> ?V] AND ?V != ?S AND ?V != ?O
    AND ?G[arrivalEpoch -> ?GA] AND ?Ready := ?GA + ?TS
    AND refundSearch[maxChangeWait -> ?W] AND ?Latest := ?GA + ?W
    AND ?Y[actualFeeds(?V) -> ?H] AND ?H[departureEpoch -> ?HD]
    AND ?HD >= ?Ready AND ?HD <= ?Latest
    AND ?H[ofTrip -> ?T2] AND ?T1 != ?T2
    AND ?H[rideSegment -> ?Seg2] AND ?H[stopSequence -> ?K]
    AND ?F[rideSegment -> ?Seg2] AND ?F[atStopPoint -> ?S] AND ?F:ReportedStop
    AND ?F[stopSequence -> ?J] AND ?K < ?J AND ?F[arrivalEpoch -> ?A].

closed slot hasActualArrival.
?Y[hasActualArrival -> true] <- ?L:ActualLeg[legCheck -> ?Y].
?Y[actualArrival -> ?M] <- ?L:ActualLeg[legCheck -> ?Y]
    AND ?M := min{?A | ?K:ActualLeg[legCheck -> ?Y; alArrival -> ?A]}.
// The way that arrives first, with the fewest changes, names the train.
?Y[actualChanges -> ?N] <- ?Y[actualArrival -> ?A]
    AND ?N := min{?C | ?K:ActualLeg[legCheck -> ?Y; alArrival -> ?A; alChanges -> ?C]}.
?L:FirstArrival <- ?L:ActualLeg[legCheck -> ?Y; alArrival -> ?A; alChanges -> ?C]
    AND ?Y[actualArrival -> ?A; actualChanges -> ?C].

// --------------------------------------------------------------------
// The delay at the destination, in whole minutes; arriving early is none
// --------------------------------------------------------------------
?Y[delaySeconds -> ?Dl] <- ?Y[plannedArrival -> ?P; actualArrival -> ?A] AND ?Dl := ?A - ?P.
?Y[delayMinutes -> ?M] <- ?Y[delaySeconds -> ?Dl] AND ?Dl >= 0 AND ?Q := ?Dl / 60 AND ?M := floor(?Q).
?Y[delayMinutes -> 0] <- ?Y[delaySeconds -> ?Dl] AND ?Dl < 0.
?Y[delayMeasured -> true] <- ?Y[delayMinutes -> ?M; planOnRecord -> true].

// Why a delay is not measured: stated positively, so an empty answer is
// never mistaken for "on time".
?Y[notMeasured -> "no actual arrival at the destination is recorded within three hours of the planned departure"]
    <- ?Y:DelayCheck AND NOT ?Y[hasActualArrival -> true].
?Y[notMeasured -> "the planned train's arrival at the destination has no recorded actual time"]
    <- ?Y:DelayCheck AND NOT ?Y[planOnRecord -> true].
