# Kobo Device Simulator
"""
A simulator for testing Kobo sync functionality with Autocaliweb.

This package provides both CLI and (future) GUI interfaces for simulating
a Kobo e-reader device, allowing developers to test sync behavior without
needing a physical device.

Usage:
    # CLI interactive mode
    python -m kobosim.cli.main --server https://myserver.com --token abc123

    # Programmatic usage
    from kobosim.core import KoboClient

    client = KoboClient("https://myserver.com", "auth-token")
    client.sync()

    for book in client.state.books.values():
        print(book.title)
"""

__version__ = "1.0.0"
