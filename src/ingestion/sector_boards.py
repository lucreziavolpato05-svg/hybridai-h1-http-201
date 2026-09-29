"""Physical sector-board signs, using their source FID and customer track label."""

from dataclasses import dataclass

from .emiter import property_fact
from .normalizer import code
from .values import report_skips, source_uic, text

DATASET_ID = "sektortafel"


@dataclass(frozen=True)
class SectorBoard:
    fid: str
    uic: str
    track: str | None
    front: str | None


def normalize_record(record: dict) -> SectorBoard:
    fid = code(record.get("fid"), "fid")
    if fid is None:
        raise ValueError("Missing sector-board FID")
    return SectorBoard(fid, source_uic(record.get("bpuic")), text(record.get("kundengleisnummer")),
                       text(record.get("sektor_vorderseite")))


def normalize_records(records: list[dict]) -> list[SectorBoard]:
    boards, conflicts, errors = {}, set(), []
    for index, record in enumerate(records):
        try:
            board = normalize_record(record)
            if board.fid in boards and boards[board.fid] != board:
                conflicts.add(board.fid)
                raise ValueError(f"Conflicting sector board {board.fid}; omitted")
            boards[board.fid] = board
        except ValueError as exc:
            errors.append(f"row {index}: {exc}")
    report_skips(DATASET_ID, errors)
    return [board for fid, board in boards.items() if fid not in conflicts]


def emit_records(boards: list[SectorBoard]) -> str:
    facts = []
    for board in boards:
        subject = f"sectorboard_{board.fid}"
        facts.extend([f"{subject}:SectorBoard.", f"{subject}[atStopPoint -> station_{board.uic}]."])
        for name, value in (("trackNumber", board.track), ("sectorFront", board.front)):
            if value is not None:
                facts.append(property_fact(subject, name, value))
    return "\n".join(facts) + ("\n" if facts else "")
