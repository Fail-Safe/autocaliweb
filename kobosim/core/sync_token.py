"""SyncToken handling - mirrors the server's SyncToken logic."""

import base64
import json
from dataclasses import dataclass
from datetime import datetime

# Must match server's SyncToken version format
SYNC_TOKEN_VERSION = "1-1-0"
EPOCH = datetime(1970, 1, 1)


def to_epoch_timestamp(dt: datetime) -> float:
    """Convert datetime to epoch timestamp (seconds since 1970-01-01)."""
    if dt == datetime.min:
        return 0.0
    return (dt - EPOCH).total_seconds()


def from_epoch_timestamp(ts: float) -> datetime:
    """Convert epoch timestamp to datetime."""
    if ts <= 0:
        return datetime.min
    try:
        return datetime.utcfromtimestamp(ts)
    except (OSError, OverflowError, ValueError):
        return datetime.min


@dataclass
class SyncToken:
    """
    Client-side SyncToken that mirrors the server implementation.

    The server uses this to track sync progress. The device must send
    the token back on subsequent requests to enable incremental sync.
    """
    raw_kobo_store_token: str = ""
    books_last_modified: datetime = datetime.min
    books_last_created: datetime = datetime.min
    archive_last_modified: datetime = datetime.min
    reading_state_last_modified: datetime = datetime.min
    tags_last_modified: datetime = datetime.min

    def to_header(self) -> str:
        """Encode token for x-kobo-synctoken header."""
        data = {
            "version": SYNC_TOKEN_VERSION,
            "data": {
                "raw_kobo_store_token": self.raw_kobo_store_token,
                "books_last_modified": to_epoch_timestamp(self.books_last_modified),
                "books_last_created": to_epoch_timestamp(self.books_last_created),
                "archive_last_modified": to_epoch_timestamp(self.archive_last_modified),
                "reading_state_last_modified": to_epoch_timestamp(self.reading_state_last_modified),
                "tags_last_modified": to_epoch_timestamp(self.tags_last_modified),
            }
        }
        return base64.b64encode(json.dumps(data).encode('utf-8')).decode('utf-8')

    @classmethod
    def from_header(cls, header_value: str) -> "SyncToken":
        """Decode token from x-kobo-synctoken header."""
        if not header_value:
            return cls()

        try:
            # Handle padding
            padded = header_value + "=" * (-len(header_value) % 4)
            json_str = base64.b64decode(padded).decode('utf-8')
            data = json.loads(json_str)

            # Check version is compatible
            version = data.get("version", "")
            if not version or version < "1-0-0":
                return cls()

            inner = data.get("data", {})

            return cls(
                raw_kobo_store_token=inner.get("raw_kobo_store_token", ""),
                books_last_modified=from_epoch_timestamp(inner.get("books_last_modified", 0)),
                books_last_created=from_epoch_timestamp(inner.get("books_last_created", 0)),
                archive_last_modified=from_epoch_timestamp(inner.get("archive_last_modified", 0)),
                reading_state_last_modified=from_epoch_timestamp(inner.get("reading_state_last_modified", 0)),
                tags_last_modified=from_epoch_timestamp(inner.get("tags_last_modified", 0)),
            )
        except Exception:
            return cls()

    def is_empty(self) -> bool:
        """Check if this is a fresh/empty token."""
        return (
            self.books_last_modified == datetime.min
            and self.books_last_created == datetime.min
            and self.reading_state_last_modified == datetime.min
        )
