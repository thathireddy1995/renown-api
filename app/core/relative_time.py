"""Relative date labels matching staff warehouse UI strings."""

from datetime import datetime, timezone


def relative_received_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    now = datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    delta = now.date() - when.date()
    t = when.strftime("%H:%M")
    if delta.days == 0:
        return f"Today {t}"
    if delta.days == 1:
        return "Yesterday"
    return f"{delta.days}d ago"
