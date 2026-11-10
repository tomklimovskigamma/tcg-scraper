#!/bin/bash
# Weekly Pokémon TCG market chart. Run by Hermes cron in --no-agent mode (no LLM).
# Installed copy lives at ~/.hermes/scripts/pokemon-market-chart.sh; this is the source.
# The chart needs matplotlib, which only the Homebrew Python has on this machine.
set -u
export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin
unset VIRTUAL_ENV PYTHONPATH PYTHONHOME PYTHONNOUSERSITE
cd /Users/tomklimovski/clawd/tcg-scraper || exit 1
PY=$(ls /opt/homebrew/bin/python3.1[0-9] 2>/dev/null | sort -V | tail -1)
[ -n "$PY" ] || { echo "No Homebrew Python found for the chart" >&2; exit 1; }
exec "$PY" -m pipeline.run market-chart
