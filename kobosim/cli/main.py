#!/usr/bin/env python3
"""
Kobo Device Simulator CLI

Interactive command-line tool that simulates a Kobo device syncing with Autocaliweb.
Useful for testing sync behavior without needing a physical device.

Usage:
    # From the autocaliweb repo root:
    python -m kobosim.cli.main --server https://myserver.com --token abc123

    # If installed via `pip install -e ./kobosim` (or running from inside `kobosim/`):
    python -m cli.main --server https://myserver.com --token abc123

    # Or with config file
    python -m kobosim.cli.main --config ~/.kobosim.json
"""

import argparse
import cmd
import json
import os
import sys
from pathlib import Path

try:
    # When installed via `pip install -e ./kobosim` (project packages: cli/core)
    from core import KoboClient
except ImportError:  # pragma: no cover
    # When running from the autocaliweb repo root (`python -m kobosim.cli.main`)
    from kobosim.core import KoboClient


class KoboSimCLI(cmd.Cmd):
    """Interactive Kobo device simulator shell."""

    intro = """
╔═══════════════════════════════════════════════════════════════╗
║                 Kobo Device Simulator v1.0                    ║
║                                                               ║
║       Type 'help' for commands, 'sync' to sync library        ║
╚═══════════════════════════════════════════════════════════════╝
"""
    prompt = "kobo> "

    def __init__(
        self,
        client: KoboClient,
        *,
        auto_state_file: str | None = None,
        auto_persist: bool = True,
    ):
        super().__init__()
        self.client = client
        self.client.verbose = True
        self.auto_state_file = auto_state_file
        self.auto_persist = auto_persist

    def do_sync(self, arg):
        """Sync library with server. Use 'sync full' for full resync."""
        full = arg.strip().lower() == "full"
        if full:
            print("Performing full sync (ignoring sync token)...")
        else:
            print("Performing incremental sync...")

        try:
            stats = self.client.sync(full_sync=full)
            print("\n✓ Sync complete!")
            print(f"  Books: +{stats['books_added']} ~{stats['books_updated']} -{stats['books_removed']}")
            print(f"  Collections: +{stats['collections_added']} ~{stats['collections_updated']} -{stats['collections_removed']}")
            print(f"  API calls: {stats['continuation_count']}")

            if self.auto_persist and self.auto_state_file:
                path = self.client.save_state(self.auto_state_file)
                print(f"  State saved: {path}")
        except Exception as e:
            print(f"✗ Sync failed: {e}")

    def do_books(self, arg):
        """List all synced books. Use 'books <search>' to filter."""
        search = arg.strip().lower()
        books = list(self.client.state.books.values())

        if search:
            books = [b for b in books if search in b.title.lower() or
                     any(search in a.lower() for a in b.authors)]

        if not books:
            print("No books found.")
            return

        print(f"\n{'='*70}")
        print(f"{'Title':<40} {'Author':<25} {'Status':<10}")
        print(f"{'='*70}")

        for book in sorted(books, key=lambda b: b.title.lower()):
            title = book.title[:38] + ".." if len(book.title) > 40 else book.title
            author = ", ".join(book.authors)[:23] + ".." if len(", ".join(book.authors)) > 25 else ", ".join(book.authors)
            status = f"{int(book.reading_progress * 100)}%" if book.reading_progress > 0 else book.reading_status.value
            print(f"{title:<40} {author:<25} {status:<10}")

        print(f"\nTotal: {len(books)} books")

    def do_collections(self, arg):
        """List all collections/shelves."""
        collections = list(self.client.state.collections.values())

        if not collections:
            print("No collections synced.")
            return

        print(f"\n{'Collection':<40} {'Books':<10}")
        print(f"{'='*50}")

        for col in sorted(collections, key=lambda c: c.name.lower()):
            print(f"{col.name:<40} {len(col.book_uuids):<10}")

        print(f"\nTotal: {len(collections)} collections")

    def do_collection(self, arg):
        """Show books in a specific collection. Usage: collection <name>"""
        name = arg.strip().lower()
        if not name:
            print("Usage: collection <name>")
            return

        # Find matching collection
        collection = None
        for col in self.client.state.collections.values():
            if name in col.name.lower():
                collection = col
                break

        if not collection:
            print(f"Collection '{arg}' not found.")
            return

        print(f"\nCollection: {collection.name}")
        print(f"{'='*50}")

        for book_uuid in collection.book_uuids:
            book = self.client.state.books.get(book_uuid)
            if book:
                print(f"  • {book.title}")
            else:
                print(f"  • [Unknown: {book_uuid[:8]}...]")

        print(f"\nTotal: {len(collection.book_uuids)} books")

    def do_book(self, arg):
        """Show details for a specific book. Usage: book <title>"""
        # Strip quotes and whitespace
        search = arg.strip().strip('"\'').lower()
        if not search:
            print("Usage: book <title>")
            return

        # Find all matching books
        matches = []
        for b in self.client.state.books.values():
            if search in b.title.lower():
                matches.append(b)

        if not matches:
            print(f"No books matching '{search}' found.")
            return

        if len(matches) > 1:
            print(f"\nFound {len(matches)} books matching '{search}':")
            print(f"{'='*70}")
            for b in matches[:20]:  # Limit to 20 results
                print(f"  • {b.title}")
            if len(matches) > 20:
                print(f"  ... and {len(matches) - 20} more")
            print("\nBe more specific, or showing first match:")

        book = matches[0]

        print(f"\n{'='*50}")
        print(f"Title:       {book.title}")
        print(f"Authors:     {', '.join(book.authors) or 'Unknown'}")
        if book.series:
            print(f"Series:      {book.series} #{book.series_index}")
        print(f"Publisher:   {book.publisher or 'Unknown'}")
        print(f"Language:    {book.language or 'Unknown'}")
        print(f"UUID:        {book.uuid}")
        print(f"Status:      {book.reading_status.value}")
        print(f"Progress:    {int(book.reading_progress * 100)}%")
        print(f"Formats:     {', '.join(book.download_urls.keys()) or 'None'}")
        print(f"{'='*50}")

    def do_status(self, arg):
        """Show device status and sync state."""
        state = self.client.state
        print(f"\n{state.summary()}")
        print(f"Sync Token Empty: {self.client.sync_token.is_empty()}")
        print(f"Server: {self.client.server_url}")

    def do_reset(self, arg):
        """Reset device state (clear all books/collections, reset sync token)."""
        confirm = input("This will clear all synced data. Continue? [y/N] ")
        if confirm.lower() == 'y':
            self.client.reset_sync()
            print("✓ Device state reset.")
        else:
            print("Cancelled.")

    def do_verbose(self, arg):
        """Toggle verbose mode for API calls."""
        self.client.verbose = not self.client.verbose
        print(f"Verbose mode: {'ON' if self.client.verbose else 'OFF'}")

    def do_token(self, arg):
        """Show current sync token (base64 encoded)."""
        if self.client.sync_token.is_empty():
            print("Sync token is empty (will do full sync).")
        else:
            print(f"Sync Token: {self.client.sync_token.to_header()[:50]}...")
            print(f"  books_last_modified: {self.client.sync_token.books_last_modified}")
            print(f"  books_last_created: {self.client.sync_token.books_last_created}")
            print(f"  tags_last_modified: {self.client.sync_token.tags_last_modified}")

    def do_raw(self, arg):
        """Fetch raw sync response and display JSON. Usage: raw [limit]"""
        limit = int(arg.strip()) if arg.strip().isdigit() else 5

        print("Fetching raw sync response...")
        url = self.client._url("/v1/library/sync")
        response = self.client.session.get(url)

        print(f"Status: {response.status_code}")
        print(f"Headers: x-kobo-sync={response.headers.get('x-kobo-sync', 'N/A')}")
        print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
        print()

        try:
            data = response.json()
            if isinstance(data, list):
                print(f"Response contains {len(data)} items:")
                for i, item in enumerate(data[:limit]):
                    print(f"\n--- Item {i} ---")
                    print(json.dumps(item, indent=2, default=str)[:500])
                if len(data) > limit:
                    print(f"\n... and {len(data) - limit} more items (use 'raw N' to see more)")
            else:
                print(json.dumps(data, indent=2, default=str)[:1000])
        except Exception as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Raw response: {response.text[:500]}")

    def do_debug(self, arg):
        """Debug: show first 5 book titles stored in state."""
        books = list(self.client.state.books.values())
        print(f"\nStored books: {len(books)}")
        print("First 5 titles (repr):")
        for b in books[:5]:
            print(f"  repr: {repr(b.title)}")
            print(f"  lower: {repr(b.title.lower())}")
        if arg.strip():
            search = arg.strip().lower()
            print(f"\nSearching for: {repr(search)}")
            for b in books[:20]:
                if search in b.title.lower():
                    print(f"  MATCH: {b.title}")
                else:
                    # Check character by character
                    if any(c in b.title.lower() for c in search.split()):
                        print(f"  PARTIAL: {b.title}")

    def do_save(self, arg):
        """Save device state to file. Usage: save [filename]"""
        filename = arg.strip() or self.auto_state_file or "kobosim_state.json"
        try:
            path = self.client.save_state(filename)
            print(f"✓ State saved to {path}")
        except Exception as e:
            print(f"✗ Save failed: {e}")

    def do_load(self, arg):
        """Load device state from file. Usage: load [filename]"""
        filename = arg.strip() or self.auto_state_file or "kobosim_state.json"
        try:
            loaded = self.client.load_state(filename)
            if loaded:
                print(f"✓ State loaded from {filename}")
            else:
                print(f"No state file found at {filename}")
        except Exception as e:
            print(f"✗ Load failed: {e}")

    def do_exit(self, arg):
        """Exit the simulator."""
        print("Goodbye!")
        return True

    do_quit = do_exit
    do_q = do_exit


def main():
    parser = argparse.ArgumentParser(
        description="Kobo Device Simulator - Test Autocaliweb sync without a physical device"
    )
    parser.add_argument("--server", "-s", help="Server URL (e.g., https://books.example.com)")
    parser.add_argument("--token", "-t", help="Kobo auth token from user profile")
    parser.add_argument("--config", "-c", help="Config file path (JSON with server/token)")
    parser.add_argument("--device-id", "-d", help="Device ID (generates random if not set)")
    parser.add_argument("--sync", action="store_true", help="Immediately sync and exit (non-interactive)")
    parser.add_argument("--full-sync", action="store_true", help="Force full sync")
    parser.add_argument("--json", action="store_true", help="Output JSON (for scripting)")
    parser.add_argument(
        "--state-file",
        help="State file path (defaults to per-server/token file under ~/.kobosim)",
    )
    parser.add_argument(
        "--state-dir",
        help="Base directory for auto-generated state files (default: ~/.kobosim)",
    )
    parser.add_argument(
        "--no-auto-state",
        action="store_true",
        help="Disable auto-load/auto-save of device state",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Max sync continuation pages before aborting (default: 200)",
    )

    args = parser.parse_args()

    server_url = args.server
    auth_token = args.token

    # Load from config file if provided
    if args.config:
        config_path = Path(args.config).expanduser()
        if config_path.exists():
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
                server_url = server_url or config.get("server")
                auth_token = auth_token or config.get("token")

    # Check for env vars
    server_url = server_url or os.environ.get("KOBOSIM_SERVER")
    auth_token = auth_token or os.environ.get("KOBOSIM_TOKEN")

    if not server_url or not auth_token:
        print("Error: Server URL and auth token required.")
        print("Provide via --server/--token, --config file, or KOBOSIM_SERVER/KOBOSIM_TOKEN env vars.")
        sys.exit(1)

    # Create client
    client = KoboClient(server_url, auth_token, device_id=args.device_id)

    if args.max_pages:
        client.max_sync_pages = int(args.max_pages)

    auto_state_file = None
    if not args.no_auto_state:
        auto_state_file = args.state_file
        if not auto_state_file:
            auto_state_file = str(client.default_state_file(server_url, auth_token, state_dir=args.state_dir))

        try:
            loaded = client.load_state(auto_state_file)
            if loaded and not args.json:
                print(f"✓ Loaded state: {auto_state_file}")
        except Exception as e:
            if not args.json:
                print(f"✗ Failed to load state ({auto_state_file}): {e}")

    # Non-interactive mode
    if args.sync:
        client.verbose = not args.json
        try:
            stats = client.sync(full_sync=args.full_sync)
            if not args.no_auto_state and auto_state_file:
                client.save_state(auto_state_file)
            if args.json:
                output = {
                    "success": True,
                    "stats": stats,
                    "books": len(client.state.books),
                    "collections": len(client.state.collections),
                    "state_file": auto_state_file,
                }
                print(json.dumps(output, indent=2))
            else:
                print(f"\n✓ Sync complete: {len(client.state.books)} books, {len(client.state.collections)} collections")
        except Exception as e:
            if args.json:
                print(json.dumps({"success": False, "error": str(e)}))
            else:
                print(f"✗ Sync failed: {e}")
            sys.exit(1)
        return

    # Interactive mode
    cli = KoboSimCLI(client, auto_state_file=auto_state_file, auto_persist=not args.no_auto_state)
    try:
        cli.cmdloop()
    except KeyboardInterrupt:
        print("\nGoodbye!")


if __name__ == "__main__":
    main()
