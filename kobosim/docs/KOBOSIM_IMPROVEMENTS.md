# KoboSim Improvements

KoboSim exists to reproduce Kobo device sync behavior against Autocaliweb and make server-side bugs easier to diagnose.

## What’s already implemented

- Persistent device state (books/collections + sync token) with a per-server/token default state file under `~/.kobosim/`.
- Continuation loop diagnostics:
  - Aborts if `x-kobo-sync: continue` is returned without `x-kobo-synctoken`.
  - Aborts if the same page appears to repeat (same token(s) + same first item IDs) multiple times.
  - Aborts after `--max-pages` pages (default 200).

## How to use

From the autocaliweb repo root:

- Interactive: `python -m kobosim.cli.main --server URL --token TOKEN`
- One-shot: `python -m kobosim.cli.main --server URL --token TOKEN --sync`
- Cap continuation: `python -m kobosim.cli.main --server URL --token TOKEN --sync --max-pages 50`
- Control state:
  - Default state file is auto-derived (per server/token)
  - Override: `--state-file ./state.json`
  - Disable: `--no-auto-state`

## Roadmap (next ideas)

- Better “real device” headers and request sequencing (some endpoints are called in a specific order).
- More realistic retry/backoff (Kobo devices tend to retry aggressively, sometimes with delays).
- More robust page signature heuristics (e.g., include counts/types, not just IDs).
- Add an option to dump a structured trace file (requests + response headers + token diffs) for sharing in bug reports.
- Add a tiny test harness that replays a recorded sync session.
