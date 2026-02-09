import os
import sqlite3
import threading
import time


def _env_truthy(name: str) -> bool:
    val = os.environ.get(name)
    if val is None:
        return False
    return str(val).strip().lower() in {"1", "true", "yes", "on"}


def _get_interval_seconds() -> float:
    # Prefer explicit Calibre DB watcher vars, but support historical/experimental names.
    raw = (
        os.environ.get("ACW_CALIBRE_DB_WATCH_INTERVAL")
        or os.environ.get("ACW_SHELFGEN_DB_WATCH_INTERVAL")
        or "60"
    )
    try:
        interval = float(raw)
    except (TypeError, ValueError):
        interval = 60.0
    return max(interval, 1.0)


def _get_metadata_db_path(config_calibre_dir: str | None) -> str | None:
    if not config_calibre_dir:
        return None

    calibre_dir = str(config_calibre_dir)
    if calibre_dir.lower().endswith("metadata.db"):
        return calibre_dir
    return os.path.join(calibre_dir, "metadata.db")


def _read_sqlite_data_version(db_path: str) -> int | None:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
        cur = conn.cursor()
        cur.execute("PRAGMA data_version")
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return int(row[0])
    except Exception:
        return None


def start_calibre_db_watcher(app) -> None:
    """Optionally start a watcher which reconnects when Calibre's DB changes.

    Disabled by default. Enable with one of:
    - ACW_CALIBRE_DB_WATCHER=true
    - ACW_SHELFGEN_DB_WATCHER=true (legacy/experimental alias)

    Control interval (seconds) with:
    - ACW_CALIBRE_DB_WATCH_INTERVAL
    - ACW_SHELFGEN_DB_WATCH_INTERVAL
    """

    enabled = _env_truthy("ACW_CALIBRE_DB_WATCHER") or _env_truthy(
        "ACW_SHELFGEN_DB_WATCHER"
    )
    if not enabled:
        return

    # Local imports to avoid import cycles during app bootstrap.
    from . import calibre_db, config, logger, ub

    log = logger.create()
    interval = _get_interval_seconds()

    metadata_db = _get_metadata_db_path(getattr(config, "config_calibre_dir", None))
    if not metadata_db:
        log.warning("[calibre-db-watcher] No Calibre DB path configured; watcher disabled")
        return

    # Track last observed data_version in this process.
    state = {"last": None}

    def loop() -> None:
        log.info(
            "[calibre-db-watcher] Enabled (interval=%ss, db=%s)", interval, metadata_db
        )
        while True:
            time.sleep(interval)

            current_version = _read_sqlite_data_version(metadata_db)
            if current_version is None:
                continue

            last = state["last"]
            if last is None:
                state["last"] = current_version
                continue

            if current_version == last:
                continue

            state["last"] = current_version
            try:
                with app.app_context():
                    calibre_db.reconnect_db(config, ub.app_DB_path)
                log.info(
                    "[calibre-db-watcher] Detected Calibre DB change (data_version %s→%s); reconnected",
                    last,
                    current_version,
                )
            except Exception as ex:
                # Next loop will retry on further changes.
                log.warning(
                    "[calibre-db-watcher] Reconnect failed after DB change (data_version %s→%s): %s",
                    last,
                    current_version,
                    ex,
                )

    t = threading.Thread(target=loop, name="acw-calibre-db-watcher", daemon=True)
    t.start()
