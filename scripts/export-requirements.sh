#!/usr/bin/env bash
# Regenerate the root requirements.txt (used by Vercel) from uv.lock.
# Run after any backend dependency change (uv add/remove/lock, Dependabot PR).
# CI (.github/workflows/check-requirements.yml) fails if the committed file differs.

set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv export --package app --no-hashes --frozen --no-emit-workspace --no-dev -o requirements.txt
