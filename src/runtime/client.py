"""The framex-core client, extended with the commands this template needs.

`framex.Client` from framex-core is a slim transport. It has no helpers for
the staged bulk load that Session uses to stream the knowledge base, and it
records every request in its transcript. Recording the load would keep a
second copy of the whole program in memory, so this subclass adds a
`retain_transcript` switch and the missing command wrappers.
"""

from __future__ import annotations

import framex


class Client(framex.Client):
    """A running `framex serve` process.

    retain_transcript  keep sent requests for `transcript` and `save_replay`.
                       Set False for large loads; it can be switched back on.
    """

    def __init__(self, binary="framex", *, retain_transcript=True, **kwargs):
        super().__init__(binary, **kwargs)
        self.retain_transcript = bool(retain_transcript)

    def request(self, command, *, _record=None, **fields):
        """Send one command and return its `result`. Raises FrameXError if refused."""
        record = self.retain_transcript if _record is None else _record
        if record:
            return super().request(command, **fields)
        kept, kept_bytes = len(self._transcript), self._transcript_bytes
        try:
            return super().request(command, **fields)
        finally:
            # The base class always records; drop what it appended for this request.
            del self._transcript[kept:]
            self._transcript_bytes = kept_bytes

    # --- staged bulk loading --------------------------------------------

    def load_begin(self, **limits):
        """Open a staged bulk load. Optional max_rounds/max_facts/max_matches/max_proofs."""
        return self.request("load_begin", **limits)

    def load_chunk(self, source, *, file=None, record=None):
        """Stage one piece. Nothing is published and no inference runs yet."""
        fields = {"source": source}
        if file is not None:
            fields["file"] = file
        return self.request("load_chunk", _record=record, **fields)

    def load_commit(self):
        """Build the staged program once and publish it, or fail and change nothing."""
        return self.request("load_commit")

    def load_abort(self):
        """Discard staged work. Aborting with nothing staged is not an error."""
        return self.request("load_abort")

    # --- inspection -----------------------------------------------------

    def stats(self):
        return self.request("stats")

    def schema(self):
        return self.request("schema")

    def modules(self):
        return self.request("modules")
