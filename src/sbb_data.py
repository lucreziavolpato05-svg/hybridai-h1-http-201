"""Compatibility entry point for the structured SBB ingestion pipeline."""

from ingestion.pipeline import build_framex, main

__all__ = ["build_framex"]


if __name__ == "__main__":
    raise SystemExit(main())