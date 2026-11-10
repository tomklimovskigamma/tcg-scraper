---
name: pokemon-stock
description: Answer questions about Pokémon TCG stock, prices and market trends from the tracked Australian stores (Target, Kmart, Big W), and send qwen on a web research "quest". Use when someone asks what Pokémon cards are in stock, where to buy a product, what something costs, whether a set is rising or falling, when a set releases, what sold out or restocked, or asks to "send qwen", "quest", "go find out" or "research" something about Pokémon TCG.
---

# Pokémon TCG stock and market

A scraper on this machine checks Target, Kmart and Big W every 5 minutes
(7am to 7pm Melbourne time) and keeps a history of everything it sees. A daily
feed adds US market prices and set release dates. All of it is in one SQLite
database that you query through a read-only tool. JB Hi-Fi is not currently
readable, so it has no data.

## Answering questions

Run these from `/Users/tomklimovski/clawd/tcg-scraper` with the system Python:

```bash
cd /Users/tomklimovski/clawd/tcg-scraper
/usr/bin/python3 -m pipeline.ask summary                  # start here: stock by store, best value, hot sets, new sets
/usr/bin/python3 -m pipeline.ask stock                    # everything in stock now, with market comparison
/usr/bin/python3 -m pipeline.ask stock "elite trainer"    # in stock, title contains the text
/usr/bin/python3 -m pipeline.ask stock --store "Big W"
/usr/bin/python3 -m pipeline.ask product "pitch black"    # every matching product, in or out of stock, with its history
/usr/bin/python3 -m pipeline.ask set "pitch black"        # release date, US market price by product type, trend, where on shelves
/usr/bin/python3 -m pipeline.ask market                   # all sets and product types with price and 30-day trend
/usr/bin/python3 -m pipeline.ask events --days 7          # arrivals, sell-outs and price changes
/usr/bin/python3 -m pipeline.ask quests                   # earlier quests and their answers
/usr/bin/python3 -m pipeline.ask schema                   # table definitions
/usr/bin/python3 -m pipeline.ask sql "SELECT ..."         # any read-only query; add --json for raw rows
```

The tool cannot change anything. Do not edit files in that folder or write to
`data/history.db` by any other means.

## Rules for answers

- **Shelf prices are Australian dollars from the store page.** Quote them as facts, with the store and the link.
- **"US market" prices are US TCGplayer prices converted to Australian dollars.** Always say so. They are a guide, not what something resells for in Australia.
- **Never predict a restock.** You can say what is in stock now, what a store did in the past (from `product` or `events`), and a set's release date. Nobody publishes delivery schedules.
- **History is short.** Tracking started on 10 November 2026; say so when someone asks about earlier dates or long-term patterns.
- **Stock can change within minutes.** Give the time of the last scan from `summary` when it matters.
- Keep answers short. Discord does not render tables; use bullet points.
- This is not financial advice; do not tell people something is a good investment.

## Sending qwen on a quest

For questions the database cannot answer (news, release rumours, other
retailers, product contents, opinions from the wider web), hand the question
to qwen, a local model that researches on the web:

```bash
cd /Users/tomklimovski/clawd/tcg-scraper
/usr/bin/python3 -m pipeline.quest "the question, in full" --asker "name of the person who asked"
```

- The command returns at once. qwen posts its answer in the channel itself,
  usually within a few minutes (longer when the model server is busy). Tell
  the person that the quest has started; do not wait for it or answer the
  question yourself in the meantime.
- If the command prints that qwen is busy or the daily limit is reached, pass
  that message on and stop. Do not retry in a loop.
- One quest at a time, ten per 24 hours. Only use it for Pokémon TCG topics,
  and only when someone asks for research or the database clearly cannot answer.
- Check the database first: many questions ("is X in stock", "what does Y cost
  at Kmart", "is Z rising") need no quest.
