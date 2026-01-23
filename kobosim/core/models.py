"""Data models for Kobo device simulation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def _dt_to_iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return None


def _dt_from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class ReadingStatus(Enum):
    NOT_STARTED = "ReadyToRead"
    READING = "Reading"
    FINISHED = "Finished"


@dataclass
class SyncedBook:
    """Represents a book synced to the device."""
    uuid: str
    title: str
    authors: list[str] = field(default_factory=list)
    series: str | None = None
    series_index: float | None = None
    publisher: str | None = None
    description: str | None = None
    language: str | None = None
    cover_url: str | None = None
    download_urls: dict[str, str] = field(default_factory=dict)  # format -> url
    file_size: int = 0
    last_modified: datetime | None = None
    reading_status: ReadingStatus = ReadingStatus.NOT_STARTED
    reading_progress: float = 0.0  # 0.0 to 1.0
    is_archived: bool = False

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "title": self.title,
            "authors": list(self.authors or []),
            "series": self.series,
            "series_index": self.series_index,
            "publisher": self.publisher,
            "description": self.description,
            "language": self.language,
            "cover_url": self.cover_url,
            "download_urls": dict(self.download_urls or {}),
            "file_size": int(self.file_size or 0),
            "last_modified": _dt_to_iso(self.last_modified),
            "reading_status": self.reading_status.value,
            "reading_progress": float(self.reading_progress or 0.0),
            "is_archived": bool(self.is_archived),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SyncedBook":
        status_val = (data.get("reading_status") or ReadingStatus.NOT_STARTED.value)
        try:
            status = ReadingStatus(status_val)
        except Exception:
            status = ReadingStatus.NOT_STARTED

        return cls(
            uuid=str(data.get("uuid") or ""),
            title=str(data.get("title") or "Unknown"),
            authors=list(data.get("authors") or []),
            series=data.get("series"),
            series_index=data.get("series_index"),
            publisher=data.get("publisher"),
            description=data.get("description"),
            language=data.get("language"),
            cover_url=data.get("cover_url"),
            download_urls=dict(data.get("download_urls") or {}),
            file_size=int(data.get("file_size") or 0),
            last_modified=_dt_from_iso(data.get("last_modified")),
            reading_status=status,
            reading_progress=float(data.get("reading_progress") or 0.0),
            is_archived=bool(data.get("is_archived")),
        )

    def __str__(self) -> str:
        authors_str = ", ".join(self.authors) if self.authors else "Unknown"
        status = f"[{self.reading_status.value}]"
        if self.reading_progress > 0:
            status = f"[{int(self.reading_progress * 100)}%]"
        series_str = f" ({self.series} #{self.series_index})" if self.series else ""
        return f"{self.title}{series_str} by {authors_str} {status}"


@dataclass
class Collection:
    """Represents a collection/tag on the device."""
    uuid: str
    name: str
    book_uuids: list[str] = field(default_factory=list)
    last_modified: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "uuid": self.uuid,
            "name": self.name,
            "book_uuids": list(self.book_uuids or []),
            "last_modified": _dt_to_iso(self.last_modified),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Collection":
        return cls(
            uuid=str(data.get("uuid") or ""),
            name=str(data.get("name") or "Unknown"),
            book_uuids=list(data.get("book_uuids") or []),
            last_modified=_dt_from_iso(data.get("last_modified")),
        )

    def __str__(self) -> str:
        return f"{self.name} ({len(self.book_uuids)} books)"


@dataclass
class DeviceState:
    """Represents the current state of a simulated Kobo device."""
    device_id: str
    books: dict[str, SyncedBook] = field(default_factory=dict)  # uuid -> book
    collections: dict[str, Collection] = field(default_factory=dict)  # uuid -> collection
    last_sync: datetime | None = None
    sync_token_raw: str | None = None

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "books": {uuid: book.to_dict() for uuid, book in (self.books or {}).items()},
            "collections": {uuid: col.to_dict() for uuid, col in (self.collections or {}).items()},
            "last_sync": _dt_to_iso(self.last_sync),
            "sync_token_raw": self.sync_token_raw,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DeviceState":
        device_id = str(data.get("device_id") or "")
        state = cls(device_id=device_id)
        state.last_sync = _dt_from_iso(data.get("last_sync"))
        state.sync_token_raw = data.get("sync_token_raw")

        books = {}
        for uuid, book_data in (data.get("books") or {}).items():
            try:
                book_obj = SyncedBook.from_dict(book_data or {})
                if not book_obj.uuid:
                    book_obj.uuid = str(uuid)
                books[str(book_obj.uuid)] = book_obj
            except Exception:
                continue
        state.books = books

        cols = {}
        for uuid, col_data in (data.get("collections") or {}).items():
            try:
                col_obj = Collection.from_dict(col_data or {})
                if not col_obj.uuid:
                    col_obj.uuid = str(uuid)
                cols[str(col_obj.uuid)] = col_obj
            except Exception:
                continue
        state.collections = cols
        return state

    @property
    def book_count(self) -> int:
        return len(self.books)

    @property
    def collection_count(self) -> int:
        return len(self.collections)

    def get_books_in_collection(self, collection_uuid: str) -> list[SyncedBook]:
        """Get all books in a specific collection."""
        collection = self.collections.get(collection_uuid)
        if not collection:
            return []
        return [self.books[uuid] for uuid in collection.book_uuids if uuid in self.books]

    def summary(self) -> str:
        """Return a summary of device state."""
        lines = [
            f"Device ID: {self.device_id}",
            f"Books: {self.book_count}",
            f"Collections: {self.collection_count}",
            f"Last Sync: {self.last_sync.isoformat() if self.last_sync else 'Never'}",
        ]
        return "\n".join(lines)
