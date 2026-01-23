# Kobo Device Simulator

A testing tool that simulates a Kobo e-reader syncing with Autocaliweb. Useful for testing sync behavior without tying up a physical device.

## Quick Start

```bash
# From the autocaliweb repo root
python -m kobosim.cli.main --server https://your-server.com --token YOUR_AUTH_TOKEN

# Shortcut (equivalent to running the CLI module)
python -m kobosim --server https://your-server.com --token YOUR_AUTH_TOKEN

# Or (from inside the kobosim/ directory)
cd kobosim
python -m cli.main --server https://your-server.com --token YOUR_AUTH_TOKEN

# Or install the local tool and run the console script
./kobosim/setup.sh
kobosim --server https://your-server.com --token YOUR_AUTH_TOKEN
```

## Development Notes

See [kobosim/docs/KOBOSIM_IMPROVEMENTS.md](kobosim/docs/KOBOSIM_IMPROVEMENTS.md) for roadmap + testing tips.

## Getting Your Auth Token

1. Log into Autocaliweb
2. Go to your profile
3. Under "Kobo Sync Token", click "Create/Show"
4. Copy the token from the URL (the part after `/kobo/` and before `/v1/`)

## CLI Commands

Once in the interactive shell:

| Command             | Description                      |
| ------------------- | -------------------------------- |
| `sync`              | Incremental sync with server     |
| `sync full`         | Full resync (ignores sync token) |
| `books`             | List all synced books            |
| `books <search>`    | Search books by title/author     |
| `collections`       | List all collections             |
| `collection <name>` | Show books in a collection       |
| `book <title>`      | Show book details                |
| `status`            | Show device/sync status          |
| `token`             | Show current sync token          |
| `reset`             | Clear device state               |
| `save [file]`       | Save state to JSON               |
| `load [file]`       | Load state from JSON             |
| `verbose`           | Toggle API call logging          |
| `exit`              | Quit                             |

### Persistent State (Auto-load / Auto-save)

By default, KoboSim automatically loads/saves device state (including sync token) to a per-server/token file under `~/.kobosim/`.

This makes successive runs behave more like a real device (incremental sync with continuation tokens).

## Non-Interactive Mode

For scripting/CI:

```bash
# Sync and output JSON
python -m kobosim.cli.main --server URL --token TOKEN --sync --json

# Full sync
python -m kobosim.cli.main --server URL --token TOKEN --sync --full-sync

# Override where state is stored
python -m kobosim.cli.main --server URL --token TOKEN --sync --state-file ./state.json

# Disable automatic state persistence
python -m kobosim.cli.main --server URL --token TOKEN --sync --no-auto-state
```

### Continuation Loop Diagnostics

KoboSim now aborts with a clear error if the server appears to be stuck in a continuation loop (for example, repeating the same page), or if the server responds with `x-kobo-sync: continue` but fails to send `x-kobo-synctoken`.

You can cap continuation pages explicitly:

```bash
python -m kobosim.cli.main --server URL --token TOKEN --sync --max-pages 50
```

## Config File

Create `~/.kobosim.json`:

```json
{
  "server": "https://your-server.com",
  "token": "your-auth-token"
}
```

Then just run:

```bash
python -m kobosim.cli.main --config ~/.kobosim.json
```

## Environment Variables

```bash
export KOBOSIM_SERVER="https://your-server.com"
export KOBOSIM_TOKEN="your-auth-token"
export KOBOSIM_STATE_DIR="$HOME/.kobosim"   # optional
export KOBOSIM_MAX_PAGES="200"             # optional
python -m kobosim.cli.main
```

## Programmatic Usage

```python
from kobosim.core import KoboClient

# Create client
client = KoboClient("https://your-server.com", "auth-token")
client.verbose = True

# Sync library
stats = client.sync()
print(f"Synced {stats['books_added']} new books")

# List books
for book in client.state.books.values():
    print(f"{book.title} by {', '.join(book.authors)}")

# List collections
for collection in client.state.collections.values():
    print(f"{collection.name}: {len(collection.book_uuids)} books")

# Simulate reading progress update
client.update_reading_progress(book_uuid, progress=0.5)
```

## Architecture

```
kobosim/
├── core/           # Shared components
│   ├── client.py   # API client (KoboClient)
│   ├── models.py   # Data models (Book, Collection, etc.)
│   └── sync_token.py  # SyncToken handling
├── cli/            # Command-line interface
│   └── main.py     # Interactive shell
└── gui/            # Future: graphical interface
```

## Future Enhancements

- [ ] GUI with visual device mockup
- [ ] Reading progress simulation
- [ ] Multiple device profiles
- [ ] Sync comparison (before/after)
- [ ] Export sync logs for debugging
- [ ] pytest fixtures for automated testing
