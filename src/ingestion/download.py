"""Small standard-library client for the SBB Explore API."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://data.sbb.ch/api/explore/v2.1/catalog/datasets"
DEFAULT_PAGE_SIZE = 100


def fetch_records(
    dataset_id: str,
    fields: list[str],
    *,
    limit: int | None = None,
    where: str | None = None,
) -> list[dict]:
    """Fetch records and follow API pagination until the requested limit."""
    records: list[dict] = []
    offset = 0
    while limit is None or len(records) < limit:
        page_limit = min(DEFAULT_PAGE_SIZE, limit - len(records)) if limit else DEFAULT_PAGE_SIZE
        parameters = {"limit": page_limit, "offset": offset, "select": ",".join(fields)}
        if where:
            parameters["where"] = where
        query = urlencode(parameters)
        request = Request(
            f"{API_BASE}/{dataset_id}/records?{query}",
            headers={"Accept": "application/json", "User-Agent": "sbb-framex-hackathon/1.0"},
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.load(response)
        except (HTTPError, URLError) as error:
            raise RuntimeError(f"SBB API request failed: {dataset_id}: {error}") from error
        page = payload.get("results", [])
        records.extend(page)
        if len(page) < page_limit:
            break
        offset += len(page)
    return records[:limit] if limit else records