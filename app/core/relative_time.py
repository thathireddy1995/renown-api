"""Relative date labels matching staff warehouse UI strings."""

from datetime import datetime

from app.core.ist import as_ist, now as ist_now


def relative_received_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    current = ist_now()
    local = as_ist(when)
    delta = current.date() - local.date()
    t = local.strftime("%H:%M")
    if delta.days == 0:
        return f"Today {t}"
    if delta.days == 1:
        return "Yesterday"
    return f"{delta.days}d ago"
