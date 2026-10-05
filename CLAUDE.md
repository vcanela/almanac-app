# Almanac

A personal recall trainer for geography and general knowledge, used by Victor on his iPhone as a home screen web app. The aim is to rebuild the memory he had in high school (every capital, including US and Mexican state capitals), for fun and without pressure.

## Design principles
- **Calm, not compulsive.** No streaks, badges, timers, notifications, or counts of missed days. A skipped week quietly reshuffles. Do not add gamification without asking.
- **Recall, not recognition.** Prompt, think, reveal, self-grade (missed / shaky / knew it). No multiple choice.
- **Context makes it stick.** Every card carries a one-line curiosity note on the reveal side.
- **Honest progress.** The only progress shown is "N of M settled" per deck.

## Structure
No build step, no dependencies. A handful of static files rather than one, because offline use on iPhone needs a manifest, icons and a service worker.

- `index.html`: the whole app (HTML, CSS, JS inline).
- `sw.js`: service worker. Network first for the app's own files (4 s timeout, then the stored copy), with `cache: 'no-cache'` to bypass GitHub Pages' 10-minute `max-age`; cache first for Google Fonts. Updates appear on the next launch. Bump `CACHE` only to force a clean cache.
- iOS suspends home screen apps rather than closing them, so `index.html` reloads itself when brought back after more than an hour (never mid-round).
- `manifest.webmanifest`, `icons/`: home screen install. Icons are drawn by `tools/make-icons.py` (Pillow).
- `decks/index.json`: list of deck ids to load. Adding a deck means adding a file and its id here; no app code changes.
- `decks/<id>.json`: one deck.

## Deck format
```json
{
  "id": "us-states",
  "title": "US state capitals",
  "subtitle": "All 50 states",
  "promptLabel": "Capital of",
  "reversible": true,
  "reverseLabel": "Capital of which state",
  "context": "United States",
  "about": "Shown on the deck's browse page.",
  "cards": [
    { "id": "us-ca", "prompt": "California", "answer": "Sacramento", "note": "..." }
  ]
}
```
Optional card fields: `label` and `reverseLabel` (override the deck's), `context` (the small line under the prompt), `group` (browse page heading), `noReverse`. World cards use the older `subregion`, which serves as both context and group.

- Card `id`s must be stable forever: progress is keyed by them. Prefixes: `w-` world (ISO alpha-2), `us-` (USPS), `mx-` (ISO 3166-2:MX), `el-` elements (symbol), `gm-` Greek myths, `ds-` discoveries, `wo-` name origins.
- Card order in the file is the order new cards are introduced, so neighbours are grouped.
- The small line under the prompt is `card.context`, else `card.subregion`, else `deck.context`, else the deck title. It disambiguates (Georgia the country vs the state).
- Notes: one durable, verified fact, 12 to 25 words, no stale statistics, no em or en dashes.
- Facts are checked against English Wikipedia before they go in.

## Scheduling (Leitner boxes)
- Intervals by box, in days: `[0, 1, 3, 7, 16, 35, 75, 150]`. Box 4 and above (16+ days) counts as settled.
- Knew it: up one box. First sighting and knew it: straight to box 3 (already known).
- Shaky: down one box, minimum 1. Missed: box 1, and the card returns a few cards later in the same round (practice only, no further state change).
- A round is capped (default 15): due cards first, most overdue first, then up to 5 new cards round-robin across active decks. Backlog never shows as a number. "Another round" is always available if anything is due or unseen.
- Days are local calendar days.

## Reverse direction
- In a `reversible` deck each card also has a reversed twin, id `<id>~r`, with its own schedule: the answer becomes the prompt under `reverseLabel`.
- A reversed card unlocks once its forward card reaches box 2 (known at least once).
- No reversed card when one side contains the other (Durango, Monaco, Indianapolis), or when `noReverse` is set.
- The two directions of one item never share a round.
- Per-deck switch on the browse page, stored in `settings.revOff`. Home shows a "Reverse: N of M settled" line once any reversed card has been seen.

## Storage
- `localStorage` key `almanac.v1`: `{ v, cards: { id: { b, d, n, l } }, settings: { size, fresh, notes, off, revOff } }`. `b` box, `d` due day, `n` times graded, `l` last day. `off` lists decks excluded from rounds; `revOff` decks with reverse switched off.
- An iOS home screen app has storage separate from Safari, hence Settings has export and import.

## Local testing
`fetch` does not work from `file://`; serve the folder (e.g. `python3 -m http.server 8642`).

## Deployment
GitHub repo `vcanela/almanac-app`, GitHub Pages from `main`. All paths are relative so the app works under `/almanac-app/`.
