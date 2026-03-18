#!/usr/bin/env bash



set -euo pipefail



cron || true



exec python -m app.main