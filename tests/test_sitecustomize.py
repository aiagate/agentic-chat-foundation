"""Tests for project-wide Python startup behavior."""

from __future__ import annotations

import importlib
import os
import tempfile

import pytest

import sitecustomize


def test_sitecustomize_normalizes_wsl_tempdir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WSL-inherited Windows temp paths should be rewritten to `/tmp`."""

    monkeypatch.setenv("TMPDIR", "/mnt/c/Users/Dorothy/AppData/Local/Temp")
    monkeypatch.setenv("TMP", "/mnt/c/Users/Dorothy/AppData/Local/Temp")
    monkeypatch.setenv("TEMP", "/mnt/c/Users/Dorothy/AppData/Local/Temp")
    tempfile.tempdir = None

    importlib.reload(sitecustomize)

    assert os.environ["TMPDIR"] == "/tmp"
    assert os.environ["TMP"] == "/tmp"
    assert os.environ["TEMP"] == "/tmp"
    assert tempfile.gettempdir() == "/tmp"
