"""Kobo API client that simulates device behavior."""

import hashlib
import json
import os
import uuid
from collections.abc import Generator
from datetime import datetime
from pathlib import Path

import requests

from .models import Collection, DeviceState, ReadingStatus, SyncedBook
from .sync_token import SyncToken


class KoboClient:
    """
    HTTP client that simulates a Kobo device communicating with Autocaliweb.

    Usage:
        client = KoboClient("https://myserver.com", "abc123-auth-token")
        client.sync()
        for book in client.state.books.values():
            print(book)
    """

    # Headers that a real Kobo device sends
    DEFAULT_HEADERS = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": "Kobo/8.11.24971 Android/12 (Build/RQ3A.211001.001; CPU/arm64-v8a; Screen/1920x1200; Touch/true)",
        "X-Kobo-Devicemodel": "Kobo Sage",
        "X-Kobo-Deviceos": "Android",
        "X-Kobo-Deviceosversion": "12",
    }

    def __init__(self, server_url: str, auth_token: str, device_id: str | None = None):
        """
        Initialize Kobo client.

        Args:
            server_url: Base URL of Autocaliweb server (e.g., "https://books.example.com")
            auth_token: The Kobo auth token from the user's profile
            device_id: Optional device ID (generates random if not provided)
        """
        self.server_url = server_url.rstrip('/')
        self.auth_token = auth_token
        self.device_id = device_id or str(uuid.uuid4())
        self.state = DeviceState(device_id=self.device_id)
        self.sync_token = SyncToken()
        self.session = requests.Session()
        self.session.headers.update(self.DEFAULT_HEADERS)
        self.session.headers["X-Kobo-Deviceid"] = self.device_id
        self.verbose = False
        self.max_sync_pages = int(os.environ.get("KOBOSIM_MAX_PAGES", "200"))

    @staticmethod
    def compute_profile_id(server_url: str, auth_token: str) -> str:
        raw = f"{server_url.rstrip('/')}|{auth_token}".encode("utf-8", errors="ignore")
        return hashlib.sha256(raw).hexdigest()[:12]

    @staticmethod
    def default_state_file(server_url: str, auth_token: str, state_dir: str | None = None) -> Path:
        base_dir = Path(state_dir or os.environ.get("KOBOSIM_STATE_DIR", "~/.kobosim")).expanduser()
        profile_id = KoboClient.compute_profile_id(server_url, auth_token)
        return base_dir / f"state_{profile_id}.json"

    def save_state(self, file_path: str | Path) -> Path:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "version": 1,
            "saved_at": datetime.now().isoformat(),
            "profile_id": self.compute_profile_id(self.server_url, self.auth_token),
            "server_url": self.server_url,
            "device_id": self.device_id,
            "sync_token": self.sync_token.to_header(),
            "device_state": self.state.to_dict(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)
        return path

    def load_state(self, file_path: str | Path, *, strict_profile: bool = True) -> bool:
        path = Path(file_path).expanduser()
        if not path.exists():
            return False

        with open(path, encoding="utf-8") as f:
            payload = json.load(f)

        if strict_profile:
            expected = self.compute_profile_id(self.server_url, self.auth_token)
            if payload.get("profile_id") and payload.get("profile_id") != expected:
                raise RuntimeError(
                    f"State file profile mismatch (expected {expected}, got {payload.get('profile_id')}). "
                    "This usually means you're pointing at a different server/token."
                )

        device_id = payload.get("device_id") or payload.get("device_state", {}).get("device_id")
        if device_id:
            self.device_id = str(device_id)
            self.session.headers["X-Kobo-Deviceid"] = self.device_id

        token_raw = payload.get("sync_token") or ""
        self.sync_token = SyncToken.from_header(token_raw)

        state_blob = payload.get("device_state") or {"device_id": self.device_id}
        self.state = DeviceState.from_dict(state_blob)
        if not self.state.device_id:
            self.state.device_id = self.device_id
        self.state.sync_token_raw = token_raw
        return True

    def _url(self, endpoint: str) -> str:
        """Build full URL with auth token."""
        # Autocaliweb expects: /kobo/<auth_token>/v1/...
        return f"{self.server_url}/kobo/{self.auth_token}{endpoint}"

    def _log(self, msg: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[KoboClient] {msg}")

    def sync(self, full_sync: bool = False) -> dict:
        """
        Perform library sync, just like a real Kobo device.

        Args:
            full_sync: If True, ignore sync token and do full sync

        Returns:
            Summary dict with counts of added/updated/removed items
        """
        if full_sync:
            self.sync_token = SyncToken()
            self.state.books.clear()
            self.state.collections.clear()

        stats = {
            "books_added": 0,
            "books_updated": 0,
            "books_removed": 0,
            "collections_added": 0,
            "collections_updated": 0,
            "collections_removed": 0,
            "continuation_count": 0,
        }

        # Follow continuation tokens until sync complete
        for response_data, new_token in self._sync_pages():
            stats["continuation_count"] += 1
            self._process_sync_response(response_data, stats)
            self.sync_token = new_token

        self.state.last_sync = datetime.now()
        self.state.sync_token_raw = self.sync_token.to_header()

        return stats

    def _sync_pages(self) -> Generator[tuple[list, SyncToken], None, None]:
        """Generator that yields sync response pages, following continuation."""
        seen = {}
        page_num = 0
        while True:
            page_num += 1
            if page_num > self.max_sync_pages:
                raise RuntimeError(
                    f"Exceeded max sync pages ({self.max_sync_pages}). "
                    "Likely continuation loop (server keeps responding with x-kobo-sync=continue)."
                )

            headers = {}
            if not self.sync_token.is_empty():
                headers["x-kobo-synctoken"] = self.sync_token.to_header()

            self._log("GET /v1/library/sync")
            response = self.session.get(self._url("/v1/library/sync"), headers=headers)
            response.raise_for_status()

            # Parse new sync token from response headers
            new_token_raw = response.headers.get("x-kobo-synctoken", "")
            new_token = SyncToken.from_header(new_token_raw)

            data = response.json()

            cont = response.headers.get("x-kobo-sync", "").lower() == "continue"
            if cont and not new_token_raw:
                raise RuntimeError(
                    "Server asked to continue (x-kobo-sync=continue) but did not provide x-kobo-synctoken. "
                    "A real device will typically retry and loop here."
                )

            sent_token = headers.get("x-kobo-synctoken", "")
            sig_ids = self._signature_ids(data)
            signature = ("continue" if cont else "done", sent_token[:64], new_token_raw[:64], tuple(sig_ids[:10]))
            seen[signature] = seen.get(signature, 0) + 1
            if cont and seen[signature] >= 3:
                raise RuntimeError(
                    "Detected repeated sync page (same token(s) + same first IDs) 3+ times. "
                    f"sent_token_prefix={sent_token[:16]} recv_token_prefix={new_token_raw[:16]} first_ids={sig_ids[:10]}"
                )

            # Debug: show raw response
            if self.verbose:
                if isinstance(data, list):
                    self._log(f"  Response: {len(data)} items")
                    for i, item in enumerate(data[:5]):  # Show first 5
                        keys = list(item.keys()) if isinstance(item, dict) else str(type(item))
                        self._log(f"    [{i}] keys: {keys}")
                    if len(data) > 5:
                        self._log(f"    ... and {len(data) - 5} more items")
                else:
                    self._log(f"  Response type: {type(data)}, content: {str(data)[:200]}")

            yield data, new_token

            # Check for continuation
            if "x-kobo-sync" not in response.headers:
                break
            if response.headers.get("x-kobo-sync", "").lower() != "continue":
                break

    @staticmethod
    def _signature_ids(items: object) -> list[str]:
        """Extract stable IDs from a sync page to detect repetition/loops."""
        if not isinstance(items, list):
            return []

        ids: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                if "NewEntitlement" in item or "ChangedEntitlement" in item or "DeletedEntitlement" in item:
                    ent = item.get("NewEntitlement") or item.get("ChangedEntitlement") or item.get("DeletedEntitlement")
                    book_ent = (ent or {}).get("BookEntitlement", {})
                    bid = book_ent.get("Id")
                    if bid:
                        ids.append(str(bid))
                        continue
                if "NewTag" in item or "ChangedTag" in item or "DeletedTag" in item:
                    tag = item.get("NewTag") or item.get("ChangedTag") or item.get("DeletedTag")
                    tid = ((tag or {}).get("Tag") or {}).get("Id")
                    if tid:
                        ids.append(str(tid))
                        continue
            except Exception:
                continue

        return ids

    def _process_sync_response(self, items: list, stats: dict):
        """Process a batch of sync items."""
        for item in items:
            if "NewEntitlement" in item:
                self._handle_new_entitlement(item["NewEntitlement"], stats)
            elif "ChangedEntitlement" in item:
                self._handle_changed_entitlement(item["ChangedEntitlement"], stats)
            elif "DeletedEntitlement" in item:
                self._handle_deleted_entitlement(item["DeletedEntitlement"], stats)
            elif "NewTag" in item:
                self._handle_new_tag(item["NewTag"], stats)
            elif "ChangedTag" in item:
                self._handle_changed_tag(item["ChangedTag"], stats)
            elif "DeletedTag" in item:
                self._handle_deleted_tag(item["DeletedTag"], stats)

    def _handle_new_entitlement(self, data: dict, stats: dict):
        """Handle NewEntitlement (new book)."""
        book = self._parse_book(data)
        if book:
            self.state.books[book.uuid] = book
            stats["books_added"] += 1
            self._log(f"  + Book: {book.title}")

    def _handle_changed_entitlement(self, data: dict, stats: dict):
        """Handle ChangedEntitlement (updated book)."""
        book = self._parse_book(data)
        if book:
            self.state.books[book.uuid] = book
            stats["books_updated"] += 1
            self._log(f"  ~ Book: {book.title}")

    def _handle_deleted_entitlement(self, data: dict, stats: dict):
        """Handle DeletedEntitlement (removed book)."""
        book_data = data.get("BookEntitlement", {})
        book_uuid = book_data.get("Id", "")
        if book_uuid and book_uuid in self.state.books:
            title = self.state.books[book_uuid].title
            del self.state.books[book_uuid]
            stats["books_removed"] += 1
            self._log(f"  - Book: {title}")

    def _handle_new_tag(self, data: dict, stats: dict):
        """Handle NewTag (new collection)."""
        collection = self._parse_collection(data)
        if collection:
            self.state.collections[collection.uuid] = collection
            stats["collections_added"] += 1
            self._log(f"  + Collection: {collection.name}")

    def _handle_changed_tag(self, data: dict, stats: dict):
        """Handle ChangedTag (updated collection)."""
        collection = self._parse_collection(data)
        if collection:
            self.state.collections[collection.uuid] = collection
            stats["collections_updated"] += 1
            self._log(f"  ~ Collection: {collection.name}")

    def _handle_deleted_tag(self, data: dict, stats: dict):
        """Handle DeletedTag (removed collection)."""
        tag_uuid = data.get("Tag", {}).get("Id", "")
        if tag_uuid and tag_uuid in self.state.collections:
            name = self.state.collections[tag_uuid].name
            del self.state.collections[tag_uuid]
            stats["collections_removed"] += 1
            self._log(f"  - Collection: {name}")

    def _parse_book(self, data: dict) -> SyncedBook | None:
        """Parse a book from entitlement data."""
        book_data = data.get("BookEntitlement", {})
        metadata = data.get("BookMetadata", {})

        book_uuid = book_data.get("Id", "")
        if not book_uuid:
            return None

        # Extract authors
        contributors = metadata.get("ContributorRoles", [])
        authors = [c.get("Name", "") for c in contributors if c.get("Role") == "Author"]

        # Extract download URLs
        download_urls = {}
        for link in metadata.get("DownloadUrls", []):
            fmt = link.get("Format", "").upper()
            url = link.get("Url", "")
            if fmt and url:
                download_urls[fmt] = url

        # Parse series info
        series = metadata.get("Series", {})
        series_name = series.get("Name") if series else None
        series_index = series.get("Number") if series else None

        return SyncedBook(
            uuid=book_uuid,
            title=metadata.get("Title", "Unknown"),
            authors=authors,
            series=series_name,
            series_index=series_index,
            publisher=metadata.get("Publisher", {}).get("Name"),
            description=metadata.get("Description"),
            language=metadata.get("Language"),
            cover_url=metadata.get("CoverImageUrl"),
            download_urls=download_urls,
            file_size=metadata.get("FileSize", 0),
        )

    def _parse_collection(self, data: dict) -> Collection | None:
        """Parse a collection from tag data."""
        tag_data = data.get("Tag", {})

        tag_uuid = tag_data.get("Id", "")
        if not tag_uuid:
            return None

        # Extract book UUIDs in this collection
        book_uuids = [item.get("RevisionId", "") for item in tag_data.get("Items", [])]
        book_uuids = [u for u in book_uuids if u]

        return Collection(
            uuid=tag_uuid,
            name=tag_data.get("Name", "Unknown"),
            book_uuids=book_uuids,
        )

    def get_book_metadata(self, book_uuid: str) -> dict | None:
        """Fetch full metadata for a specific book."""
        self._log(f"GET /v1/library/{book_uuid}/metadata")
        response = self.session.get(self._url(f"/v1/library/{book_uuid}/metadata"))
        if response.status_code == 200:
            return response.json()
        return None

    def get_reading_state(self, book_uuid: str) -> dict | None:
        """Get reading state for a book."""
        self._log(f"GET /v1/library/{book_uuid}/state")
        response = self.session.get(self._url(f"/v1/library/{book_uuid}/state"))
        if response.status_code == 200:
            return response.json()
        return None

    def update_reading_progress(self, book_uuid: str, progress: float, status: ReadingStatus = ReadingStatus.READING) -> bool:
        """
        Update reading progress for a book (simulates device sync-back).

        Args:
            book_uuid: The book UUID
            progress: Reading progress 0.0 to 1.0
            status: Reading status

        Returns:
            True if successful
        """
        # Build reading state payload matching Kobo format
        payload = {
            "CurrentBookmark": {
                "ProgressPercent": progress * 100,
                "ContentSourceProgressPercent": progress * 100,
            },
            "StatusInfo": {
                "Status": status.value,
            }
        }

        self._log(f"PUT /v1/library/{book_uuid}/state")
        response = self.session.put(
            self._url(f"/v1/library/{book_uuid}/state"),
            json=payload
        )

        if response.status_code == 200:
            # Update local state
            if book_uuid in self.state.books:
                self.state.books[book_uuid].reading_progress = progress
                self.state.books[book_uuid].reading_status = status
            return True
        return False

    def reset_sync(self):
        """Reset sync state (simulates device reset/re-register)."""
        self.sync_token = SyncToken()
        self.state.books.clear()
        self.state.collections.clear()
        self.state.last_sync = None
        self._log("Sync state reset")
