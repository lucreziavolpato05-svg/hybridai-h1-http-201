"""Download SBB Explore records and cache complete, request-specific snapshots."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_BASE = "https://data.sbb.ch/api/explore/v2.1/catalog/datasets"
DATASET_ID = "perron"
DEFAULT_RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "raw"
PAGE_SIZE = 100


def _page(payload: object) -> tuple[int, list[dict]]:
    if not isinstance(payload, dict):
        raise ValueError("SBB response must be a JSON object")
    total, records = payload.get("total_count"), payload.get("results")
    if type(total) is not int or total < 0 or not isinstance(records, list):
        raise ValueError("SBB response needs total_count and results")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError("SBB results must contain record objects")
    return total, records


def fetch_records(
    *, limit: int | None = None, raw_dir: Path = DEFAULT_RAW_DIR,
    refresh: bool = False, timeout: float = 30,
) -> list[dict]:
    """Backward-compatible platform download, including its existing cache path."""
    return fetch_dataset_records(DATASET_ID, order_by="fid", limit=limit,
                                 raw_dir=raw_dir, refresh=refresh, timeout=timeout)


def fetch_dataset_records(
    dataset_id: str, *, order_by: str | None = None, where: str | None = None,
    limit: int | None = None, raw_dir: Path = DEFAULT_RAW_DIR,
    refresh: bool = False, timeout: float = 30,
) -> list[dict]:
    """Reuse a complete snapshot unless refresh=True; retain untouched fields.

    Limited downloads have separate cache files so a sample can never masquerade
    as a full dataset. A failed refresh leaves the previous snapshot intact.
    """
    if not isinstance(dataset_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]+", dataset_id):
        raise ValueError("dataset_id must be an SBB dataset slug")
    for name, value in (("order_by", order_by), ("where", where)):
        if value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{name} must be a non-empty string or None")
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a non-negative integer or None")
    if limit == 0:
        return []
    endpoint = f"{API_BASE}/{dataset_id}/records"
    options = {"order_by": order_by, "where": where}
    legacy_platform = dataset_id == DATASET_ID and options == {"order_by": "fid", "where": None}
    suffix = "" if legacy_platform else "_" + sha256(json.dumps(options, sort_keys=True).encode()).hexdigest()[:16]
    cache_name = ("all" if limit is None else f"limit_{limit}") + suffix + ".json"
    cache_path = Path(raw_dir) / dataset_id / cache_name
    if cache_path.exists() and not refresh:
        try:
            snapshot = json.loads(cache_path.read_text(encoding="utf-8"))
            total, records = _page(snapshot)
            if snapshot.get("source_url") != endpoint or snapshot.get("requested_limit") != limit:
                raise ValueError("cache request does not match")
            cached_options = snapshot.get("options", {"order_by": "fid", "where": None} if legacy_platform else None)
            if cached_options != options:
                raise ValueError("cache filter or ordering does not match")
            if len(records) != (total if limit is None else min(total, limit)):
                raise ValueError("incomplete cached snapshot")
            return records
        except (ValueError, OSError) as exc:
            raise ValueError(f"Invalid cache {cache_path}; use --refresh: {exc}") from exc

    records: list[dict] = []
    total_count = None
    while total_count is None or len(records) < min(total_count, limit if limit is not None else total_count):
        page_size = PAGE_SIZE if limit is None else min(PAGE_SIZE, limit - len(records))
        if len(records) + page_size > 10_000:
            raise ValueError("Dataset exceeds the Explore records window; use the SBB exports API")
        parameters = {"limit": page_size, "offset": len(records)}
        parameters.update({name: value for name, value in options.items() if value is not None})
        query = urlencode(parameters)
        request = Request(f"{endpoint}?{query}", headers={
            "Accept": "application/json", "User-Agent": "sbb-framex-ingestion/1.0",
        })
        try:
            with urlopen(request, timeout=timeout) as response:
                total, page = _page(json.load(response))
        except (URLError, OSError, ValueError) as exc:
            raise RuntimeError(f"SBB {dataset_id} download failed at offset {len(records)}: {exc}") from exc
        if total_count is not None and total != total_count:
            raise RuntimeError("SBB record count changed during download; retry with --refresh")
        total_count = total
        if len(page) > page_size or len(records) + len(page) > total:
            raise ValueError("SBB returned more records than requested or advertised")
        if not page and len(records) < total:
            raise RuntimeError("SBB returned an incomplete dataset; snapshot was not cached")
        records.extend(page)

    snapshot = {
        "dataset_id": dataset_id, "source_url": endpoint, "options": options,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "requested_limit": limit, "total_count": total_count, "results": records,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.write("\n")
        os.replace(temporary, cache_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return records
