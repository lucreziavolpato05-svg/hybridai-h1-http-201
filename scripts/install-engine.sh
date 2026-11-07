#!/bin/sh
# Build the FrameX engine from framex-core and install it into .venv/bin.
#
# The Python package (a client only) and the Rust engine must come from the
# same commit, so the rev is read from the framex source in pyproject.toml.
# Requires Rust (https://rustup.rs). Run `uv sync` first.
#
#   sh scripts/install-engine.sh
set -eu

root=$(cd "$(dirname "$0")/.." && pwd)
repo=https://gitlab.com/ds-unisg/framex-core

rev=$(sed -n 's/^framex = {.*rev = "\([0-9a-f]*\)".*/\1/p' "$root/pyproject.toml")
if [ -z "$rev" ]; then
    echo "error: no framex rev found in pyproject.toml [tool.uv.sources]" >&2
    exit 1
fi
if ! command -v cargo >/dev/null 2>&1; then
    echo "error: cargo not found; install Rust from https://rustup.rs" >&2
    exit 1
fi
if [ ! -d "$root/.venv" ]; then
    echo "error: $root/.venv does not exist; run 'uv sync' first" >&2
    exit 1
fi

echo "Building FrameX engine $rev into $root/.venv/bin"
cargo install --locked --force --git "$repo" --rev "$rev" --root "$root/.venv" framex
"$root/.venv/bin/framex" --version
