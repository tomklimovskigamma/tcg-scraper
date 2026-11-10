#!/bin/bash
# Pokémon TCG digest, run by Hermes cron in --no-agent mode (no LLM).
# Installed copy lives at ~/.hermes/scripts/pokemon-digest.sh; this is the source.
set -u
# Hermes runs jobs inside its own Python environment, where `python3` has no
# `requests`. The scrapers need the system Python (requests is in its user site).
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
unset VIRTUAL_ENV PYTHONPATH PYTHONHOME PYTHONNOUSERSITE
cd /Users/tomklimovski/clawd/tcg-scraper || exit 1
exec /usr/bin/python3 -m pipeline.run digest
