#!/bin/bash
# Daily US market prices, release dates and exchange rate for the Pokémon TCG
# alert. Run by Hermes cron in --no-agent mode (no LLM).
# Installed copy lives at ~/.hermes/scripts/pokemon-market-sync.sh; this is the source.
set -u
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
unset VIRTUAL_ENV PYTHONPATH PYTHONHOME PYTHONNOUSERSITE
cd /Users/tomklimovski/clawd/tcg-scraper || exit 1
exec /usr/bin/python3 -m pipeline.run market-sync
