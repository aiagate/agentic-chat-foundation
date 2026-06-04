"""Project-wide Python startup tweaks.

This repository is exercised from a WSL workspace mounted on `/mnt/c`, while
the default Windows temp path leaks into Python's temporary directory
resolution. Pytest capture depends on a stable temp directory, so normalize it
to `/tmp` when the interpreter starts in that environment.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def _should_force_posix_tempdir(current_tempdir: str) -> bool:
    """Return whether the process should ignore the inherited temp path."""

    return current_tempdir.startswith("/mnt/")


def _configure_tempdir() -> None:
    """Point Python's temp directory at `/tmp` when WSL inherits Windows temp."""

    if os.name == "nt":
        return

    linux_tempdir = Path("/tmp")
    if not linux_tempdir.is_dir():
        return

    current_tempdir = tempfile.gettempdir()
    if not _should_force_posix_tempdir(current_tempdir):
        return

    tempdir = str(linux_tempdir)
    os.environ["TMPDIR"] = tempdir
    os.environ["TMP"] = tempdir
    os.environ["TEMP"] = tempdir
    tempfile.tempdir = tempdir


_configure_tempdir()
