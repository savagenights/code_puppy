"""Terminal tab title: context + activity, visible while scrolled up.

The tab is a narrow surface, so the context summary rides it in
round-off estimate form (``12k/262k tok(5%)`` instead of
``12.2k/262.1k tokens (5%)``) — the short shape keeps the whole status
(``context * activity``) visible without the terminal truncating it.

The bottom bar is pinned only against the app's own writes (DECSTBM
scroll region). When the user wheels up into terminal scrollback, the
terminal shifts the entire visible buffer — bar included — and no escape
sequence exists to draw into a viewport the app does not own. The tab
title is the one status surface the terminal never scrolls away, so the
context summary and stream activity ride it too. In Windows Terminal the
tab shows the title, which doubles as a "you are scrolled up" indicator.

* OSC 2 (window/tab title), BEL-terminated — honored by Windows
  Terminal, iTerm2, GNOME Terminal, Konsole, kitty, WezTerm; ignored
  harmlessly elsewhere (legacy conhost).
* TTY-only: piped stdout (CI, ``-p`` headless) never sees an escape.
* Deduped: the escape is written only when the composed string changes,
  so high-frequency callers (per-delta ``StreamStatus.paint``) are a
  lock + string compare.
* Gated by the ``tab_title`` config key (default on; ``tab_title =
  false`` in puppy.cfg disables it).
* :func:`reset` restores the plain program name on exit (atexit) so a
  stale "Working" never lingers on the tab after quit.
"""

from __future__ import annotations

import atexit
import logging
import re
import sys
import threading

logger = logging.getLogger(__name__)

#: Title written when nothing is known, and restored on exit.
TITLE_DEFAULT = "code-puppy"

#: Control characters never survive into a tab title.
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")

#: Scale steps for the round-off counts, largest first.
_SCALE_UNITS = ((10**12, "T"), (10**9, "B"), (10**6, "M"), (10**3, "k"))

#: Carry map when a rounded value overflows 999 (e.g. 999.5k -> 1M).
_SUFFIX_NEXT = {"k": "M", "M": "B", "B": "T"}

#: Leading shape of ``spinner.format_context_info`` output. The optional
#: Codex usage suffix is dropped for the tab (narrow surface).
_CONTEXT_RE = re.compile(
    r"^(?P<used>\d+(?:\.\d+)?[kM]?)/(?P<cap>\d+(?:\.\d+)?[kM]?) tokens \((?P<pct>\d+)%\)"
)

_lock = threading.Lock()
_context = ""
_activity = ""
_enabled: bool | None = None  # resolved once, lazily (see _resolve_enabled)
_wrote = False
_last = ""  # last composed string actually written to the stream


def _resolve_enabled() -> bool:
    """Lazy one-shot gate: real TTY + ``tab_title`` config (default on)."""
    global _enabled
    if _enabled is not None:
        return _enabled
    try:
        out = sys.__stdout__ or sys.stdout
        if out is None or not out.isatty():
            _enabled = False
        else:
            from code_puppy.config import get_truthy_bool_value

            _enabled = get_truthy_bool_value("tab_title", True)
    except Exception:
        _enabled = False
    return _enabled


def _stream():
    """The original TTY stream (bypasses in-test/in-app sys.stdout swaps).

    Mirrors the bottom bar, which paints on ``sys.__stdout__`` — gate and
    write path must agree on which stream owns the terminal.
    """
    try:
        out = sys.__stdout__ or sys.stdout
        if out is not None and out.isatty():
            return out
    except Exception:
        pass
    return None


def _estimate_count(n: int) -> str:
    """Round-off scale: 999 -> '999', 12200 -> '12k', 999500 -> '1M', 2.5e6 -> '3M'.

    Half-up rounding (2.5M -> 3M, never banker's 2M); overflow carries
    into the next suffix instead of producing '1000k'.
    """
    n = abs(int(n))
    for threshold, suffix in _SCALE_UNITS:
        if n >= threshold:
            value = int(n / threshold + 0.5)
            if value < 1000:
                return f"{value}{suffix}"
            bigger = _SUFFIX_NEXT.get(suffix)
            return f"{int(value / 1000 + 0.5)}{bigger}" if bigger else str(n)
    return str(n)


def _parse_count(text: str) -> int:
    """'12.2k' -> 12200, '500' -> 500, '1.5M' -> 1_500_000."""
    multiplier = 1
    if text[-1] in "kM":
        multiplier = 1_000 if text[-1] == "k" else 1_000_000
        text = text[:-1]
    return int(round(float(text) * multiplier))


def estimate_context(info: str) -> str:
    """Compress a full context summary into the short tab form.

    ``'12.2k/262.1k tokens (5%) ...'`` -> ``'12k/262k tok(5%)'``. Anything
    that doesn't start with the known summary shape passes through
    unchanged (loading lines, custom statuses, sub-agent strings).
    """
    match = _CONTEXT_RE.match(info)
    if not match:
        return info
    used = _estimate_count(_parse_count(match["used"]))
    cap = _estimate_count(_parse_count(match["cap"]))
    return f"{used}/{cap} tok({match['pct']}%)"


def _compose() -> str:
    """``context * activity``, or the default name when neither is known."""
    if _context and _activity:
        return f"{_context} * {_activity}"
    return _context or _activity or TITLE_DEFAULT


def _write(title: str) -> None:
    global _wrote, _last
    text = _CONTROL_RE.sub("", title)
    if text == _last:
        return
    _last = text  # one attempt per distinct string, even if the write fails
    payload = ("\x1b]2;" + text + "\x07").encode("utf-8", "replace")
    out = _stream()
    if out is None:
        return
    try:
        out.buffer.write(payload)
        out.buffer.flush()
        _wrote = True
    except Exception:
        try:  # exotic stdout without a binary buffer
            out.write(payload.decode("utf-8", "replace"))
            out.flush()
            _wrote = True
        except Exception:
            logger.debug("tab title write failed", exc_info=True)


def set_context(info: str) -> None:
    """Cache the token-context summary and refresh the title.

    Called from ``spinner.update_spinner_context`` — the same choke point
    the bottom bar's status row uses, including its sub-agent guard. The
    summary is compressed to the round-off estimate form before caching,
    so the tab never shows the wide ``tokens`` spelling.
    """
    global _context
    with _lock:
        if not _resolve_enabled():
            return
        info = _CONTROL_RE.sub("", info or "").strip()
        info = estimate_context(info)
        if info == _context:
            return
        _context = info
        _write(_compose())


def set_activity(activity: str) -> None:
    """Cache the stream activity and refresh the title.

    Called from ``StreamStatus.paint`` on every stream event; the dedupe
    in :func:`_write` keeps the real escape writes rare (activity changes
    a few times per run, not per delta).
    """
    global _activity
    with _lock:
        if not _resolve_enabled():
            return
        activity = _CONTROL_RE.sub("", activity or "").strip()
        if activity == _activity:
            return
        _activity = activity
        _write(_compose())


def reset() -> None:
    """Restore the default title. No-op if we never wrote one.

    Registered with :mod:`atexit`; also safe to call directly (tests,
    shutdown paths). Idempotent.
    """
    global _context, _activity, _wrote
    with _lock:
        if not _wrote:
            return
        _context = ""
        _activity = ""
        _wrote = False
        _write(TITLE_DEFAULT)


def _reset_for_tests() -> None:
    """Clear all module state (gate, cache, dedupe, written flag)."""
    global _context, _activity, _enabled, _wrote, _last
    with _lock:
        _context = ""
        _activity = ""
        _enabled = None
        _wrote = False
        _last = ""


atexit.register(reset)
