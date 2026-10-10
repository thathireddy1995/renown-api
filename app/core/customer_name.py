"""Customer display names shared by the store counter and website sign-in."""

from __future__ import annotations

import re

_PLACEHOLDER = re.compile(r"^Customer \d{4}$")


def placeholder_name(phone: str) -> str:
    """Name used when a store creates a customer before the real name is known."""
    return f"Customer {phone[-4:]}"


def has_real_name(name: str | None) -> bool:
    text = (name or "").strip()
    return bool(text) and not _PLACEHOLDER.match(text)
