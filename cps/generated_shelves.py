# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
import uuid

from flask_babel import gettext as _
from sqlalchemy.sql.expression import and_, or_, text

from . import calibre_db, config, db


@dataclass(frozen=True)
class GeneratedShelf:
    source: str
    value: str
    name: str

    is_generated: bool = True
    is_public: int = 0

    @property
    def id(self) -> str:
        # Used in templates for data attributes. Must be stable and unique.
        return f"generated:{self.source}:{self.value}"

    @property
    def uuid(self) -> str:
        # Used by Kobo sync as the Tag Id. Must be stable across requests.
        return generated_shelf_uuid(self.source, self.value)


def generated_shelf_uuid(source: str, value: str) -> str:
    # Use UUIDv5 so the same (source,value) yields the same uuid.
    # Kobo Tag IDs are UUID-shaped strings.
    stable_key = f"autocaliweb:generated-shelf:{(source or '').strip()}:{(value or '').strip()}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))


def _parse_selector(selector: str) -> tuple[str | None, int | None]:
    selector = (selector or "").strip()
    if not selector:
        return None, None
    if selector.startswith("cc:"):
        try:
            return "cc", int(selector.split(":", 1)[1])
        except (TypeError, ValueError):
            return None, None
    return selector, None


def list_generated_shelves(max_items: int = 500) -> list[GeneratedShelf]:
    selector, cc_id = _parse_selector(getattr(config, "config_generate_shelves_from_calibre_column", ""))
    if not selector:
        return []

    try:
        if selector == "tags":
            rows = (
                calibre_db.session.query(db.Tags.name)
                .select_from(db.Tags)
                .join(db.Tags.books)
                .filter(calibre_db.common_filters())
                .distinct()
                .order_by(db.Tags.name)
                .limit(max_items)
                .all()
            )
            return [GeneratedShelf(source="tags", value=r[0], name=r[0]) for r in rows if r and r[0]]

        if selector == "authors":
            rows = (
                calibre_db.session.query(db.Authors.name)
                .select_from(db.Authors)
                .join(db.Authors.books)
                .filter(calibre_db.common_filters())
                .distinct()
                .order_by(db.Authors.name)
                .limit(max_items)
                .all()
            )
            return [GeneratedShelf(source="authors", value=r[0], name=r[0]) for r in rows if r and r[0]]

        if selector == "publishers":
            rows = (
                calibre_db.session.query(db.Publishers.name)
                .select_from(db.Publishers)
                .join(db.Publishers.books)
                .filter(calibre_db.common_filters())
                .distinct()
                .order_by(db.Publishers.name)
                .limit(max_items)
                .all()
            )
            return [GeneratedShelf(source="publishers", value=r[0], name=r[0]) for r in rows if r and r[0]]

        if selector == "languages":
            rows = (
                calibre_db.session.query(db.Languages.lang_code)
                .select_from(db.Languages)
                .join(db.Languages.books)
                .filter(calibre_db.common_filters())
                .distinct()
                .order_by(db.Languages.lang_code)
                .limit(max_items)
                .all()
            )
            # Languages are stored as lang codes; display name may be derived in UI elsewhere.
            return [GeneratedShelf(source="languages", value=r[0], name=r[0]) for r in rows if r and r[0]]

        if selector == "cc" and cc_id:
            cc_class = db.cc_classes.get(cc_id)
            if cc_class is None:
                return []
            rel = getattr(db.Books, f"custom_column_{cc_id}", None)
            if rel is None:
                return []

            rows = (
                calibre_db.session.query(cc_class.value)
                .select_from(db.Books)
                .join(rel)
                .filter(calibre_db.common_filters())
                .distinct()
                .order_by(cc_class.value)
                .limit(max_items)
                .all()
            )
            return [GeneratedShelf(source=f"cc:{cc_id}", value=r[0], name=r[0]) for r in rows if r and r[0]]

    except Exception:
        # Fail closed: no generated shelves if anything goes wrong.
        return []

    return []


def generated_shelf_filter(source: str, value: str):
    """Return a SQLAlchemy filter for selecting books in the generated shelf."""
    source = (source or "").strip()
    value = (value or "").strip()
    if not source or not value:
        return None

    if source == "tags":
        return db.Books.tags.any(db.Tags.name == value)
    if source == "authors":
        return db.Books.authors.any(db.Authors.name == value)
    if source == "publishers":
        return db.Books.publishers.any(db.Publishers.name == value)
    if source == "languages":
        return db.Books.languages.any(db.Languages.lang_code == value)

    if source.startswith("cc:"):
        try:
            cc_id = int(source.split(":", 1)[1])
        except (TypeError, ValueError):
            return None

        cc_class = db.cc_classes.get(cc_id)
        if not cc_class:
            return None

        rel = getattr(db.Books, f"custom_column_{cc_id}", None)
        if not rel:
            return None

        return rel.any(cc_class.value == value)

    return None


def generated_shelf_badge_text(source: str) -> str:
    source = (source or "").strip()
    response = _("Auto-generated shelf")

    if source == "tags":
        return _("Auto-generated shelf from Tags")
    if source == "authors":
        return _("Auto-generated shelf from Authors")
    if source == "publishers":
        return _("Auto-generated shelf from Publishers")
    if source == "languages":
        return _("Auto-generated shelf from Languages")
    if source.startswith("cc:"):
        return _("Auto-generated shelf from Calibre Column")
    return response
