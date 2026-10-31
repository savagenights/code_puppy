"""Tests for the OSC 2 terminal-tab-title stopgap (messaging/tab_title.py).

Covers the gate (TTY + config), composition, dedupe, control-char
sanitization, and the exit reset — the exact failure modes that would
make this feature noisy or permanently stale.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from code_puppy.messaging import tab_title


class _FakeStream:
    """Captures writes exactly the way the module emits them (binary)."""

    def __init__(self, tty: bool = True) -> None:
        self._tty = tty
        self.buffer = _FakeBuffer()

    def isatty(self) -> bool:
        return self._tty

    def write(self, text: str) -> int:
        self.buffer.data += text.encode("utf-8", "replace")
        return len(text)

    def flush(self) -> None:
        pass

    def all_titles(self) -> list[str]:
        """Every OSC 2 payload in write order (empty prefix excluded)."""
        out = []
        for frame in self.buffer.data.split(b"\x1b]2;"):
            if not frame or frame == b"":
                continue
            payload = frame.split(b"\x07", 1)[0]
            out.append(payload.decode("utf-8", "replace"))
        return out


class _FakeBuffer:
    def __init__(self) -> None:
        self.data = b""

    def write(self, payload: bytes) -> int:
        self.data += payload
        return len(payload)

    def flush(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    tab_title._reset_for_tests()
    yield
    tab_title._reset_for_tests()


def _patch_tty(monkeypatch, tty: bool = True) -> _FakeStream:
    fake = _FakeStream(tty=tty)
    monkeypatch.setattr("sys.__stdout__", fake, raising=False)
    # The enablement gate reads sys.stdout (module code path); the write
    # path reads sys.__stdout__ — point both at the fake.
    monkeypatch.setattr("sys.stdout", fake, raising=False)
    return fake


def _patch_config(monkeypatch, enabled: bool = True) -> None:
    monkeypatch.setattr(
        "code_puppy.config.get_truthy_bool_value",
        lambda key, default=True: enabled,
    )


def test_non_tty_is_a_noop(monkeypatch):
    fake = _patch_tty(monkeypatch, tty=False)
    _patch_config(monkeypatch, enabled=True)
    tab_title.set_context("120/500 tokens (24%)")
    tab_title.set_activity("Working")
    assert fake.buffer.data == b""


def test_config_off_is_a_noop(monkeypatch):
    fake = _patch_tty(monkeypatch, tty=True)
    _patch_config(monkeypatch, enabled=False)
    tab_title.set_context("120/500 tokens (24%)")
    tab_title.set_activity("Working")
    assert fake.buffer.data == b""


def test_compose_and_dedupe(monkeypatch):
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_context("45.9k/262.1k tokens (17%)")
    assert fake.all_titles() == ["46k/262k tok(17%)"]

    tab_title.set_activity("Working")
    assert fake.all_titles() == [
        "46k/262k tok(17%)",
        "46k/262k tok(17%) * Working",
    ]

    # Identical activity again — paint() calls this per stream delta.
    tab_title.set_activity("Working")
    assert len(fake.all_titles()) == 2

    tab_title.set_activity("Idle")
    assert fake.all_titles()[-1] == "46k/262k tok(17%) * Idle"


def test_context_only_and_activity_only(monkeypatch):
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_activity("Thinking")
    assert fake.all_titles() == ["Thinking"]
    tab_title.set_context("120/500 tokens (24%)")
    assert fake.all_titles()[-1] == "120/500 tok(24%) * Thinking"


def test_set_context_estimates_and_dedupes(monkeypatch):
    """Estimation happens before the dedupe compare: same full summary twice
    writes one title, in the short form."""
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_context("12.2k/262.1k tokens (5%)")
    tab_title.set_context("12.2k/262.1k tokens (5%)")
    assert fake.all_titles() == ["12k/262k tok(5%)"]


def test_estimate_context_shapes():
    est = tab_title.estimate_context
    # k-scale, round-off (no decimals survive).
    assert est("12.2k/262.1k tokens (5%)") == "12k/262k tok(5%)"
    assert est("45.9k/262.1k tokens (17%)") == "46k/262k tok(17%)"
    # Below 1k stays plain; 1000 becomes 1k.
    assert est("120/500 tokens (24%)") == "120/500 tok(24%)"
    assert est("999/1000 tokens (99%)") == "999/1k tok(99%)"
    # M-scale with round-up.
    assert est("1.5M/2M tokens (75%)") == "2M/2M tok(75%)"
    # The Codex usage suffix rides the full string but not the tab.
    assert est("12.2k/262.1k tokens (5%) \u00b7 Codex 5h 66% remaining") == (
        "12k/262k tok(5%)"
    )
    # Unknown shapes pass through untouched (loading lines, custom status).
    assert est("Loading context\u2026") == "Loading context\u2026"
    assert est("") == ""


def test_estimate_count_round_off():
    est = tab_title._estimate_count
    assert est(0) == "0"
    assert est(999) == "999"
    assert est(1000) == "1k"
    assert est(12200) == "12k"
    assert est(999_500) == "1M"  # carry, not "1000k"
    assert est(1_234_567) == "1M"
    assert est(2_500_000) == "3M"  # half-up, never banker's rounding
    assert est(999_500_000) == "1B"  # carry into B
    assert est(1_500_000_000) == "2B"
    assert est(2_000_000_000_000) == "2T"


def test_control_chars_are_stripped(monkeypatch):
    """ESC and friends never survive; leftover literals are ours to live with."""
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_context("120/500 \x1b[31mtokens")
    titles = fake.all_titles()
    assert titles == ["120/500 [31mtokens"]
    assert all(ord(ch) > 0x1F for t in titles for ch in t)


def test_reset_restores_default_once(monkeypatch):
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_context("120/500 tokens (24%)")
    tab_title.set_activity("Working")

    tab_title.reset()
    assert fake.all_titles()[-1] == "code-puppy"

    # Second reset: nothing new was written since, so no new escape.
    before = len(fake.all_titles())
    tab_title.reset()
    assert len(fake.all_titles()) == before


def test_reset_without_writes_is_a_noop(monkeypatch):
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.reset()
    assert fake.buffer.data == b""


def test_blank_inputs_are_ignored(monkeypatch):
    fake = _patch_tty(monkeypatch)
    _patch_config(monkeypatch)
    tab_title.set_context("")
    tab_title.set_context("   ")
    tab_title.set_activity("")
    assert fake.buffer.data == b""
