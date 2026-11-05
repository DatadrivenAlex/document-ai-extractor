"""Shared fixtures. The suite stays offline: opening a socket fails the test."""

from __future__ import annotations

import socket

import pytest


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def guard(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network is disabled in the test suite")

    monkeypatch.setattr(socket, "create_connection", guard)
