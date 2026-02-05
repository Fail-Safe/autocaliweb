import json
import os
import sys

from .constants import BASE_DIR


def load_dependencies(optional=False):
    """
    Return installed dependency versions using runtime metadata only.

    Autocaliweb uses `pyproject.toml` + `uv.lock` as the canonical dependency
    source, but this checker intentionally does not parse lockfiles. Instead, it
    verifies what's actually installed in the current environment.

    NOTE: This function is only meaningful for frozen builds, where we ship a
    recorded dependency snapshot in `.pip_installed`.
    """
    _ = optional
    deps = []

    # Frozen builds keep their own dependency snapshot.
    if getattr(sys, "frozen", False):
        pip_installed = os.path.join(BASE_DIR, ".pip_installed")
        if os.path.exists(pip_installed):
            with open(pip_installed) as f:
                exe_deps = json.loads("".join(f.readlines()))
            for name, ver in exe_deps.items():
                deps.append([ver, name, None, None, None, None])
        return deps

    return deps


def dependency_check(optional=False):
    """
    Legacy version-range checking previously validated installed packages against a
    compiled requirements lock. Autocaliweb now relies on `uv sync --locked` to ensure
    the runtime environment matches the pinned resolution in `uv.lock`.

    Keep API behavior stable: return an empty list (no mismatches) rather than
    failing due to a missing legacy lockfile.
    """
    _ = optional
    return []
