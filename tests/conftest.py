"""Shared pytest fixtures for host-independent plugin tests."""

from __future__ import annotations

import sys

import pytest
from fake_sd import install_fake_sd_modules

sys.dont_write_bytecode = True


@pytest.fixture(autouse=True)
def fake_sd_sdk() -> None:
    """Restore fake SD SDK modules before each test."""
    install_fake_sd_modules()
