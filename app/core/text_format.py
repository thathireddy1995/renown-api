"""Shared string formatting for catalog / API responses."""


def title_case_name(value: str | None) -> str:
    """Title-case each word: ``RAYBAN AVIATOR`` → ``Rayban Aviator``.

    Hyphenated tokens are title-cased per segment (``blue-light`` → ``Blue-Light``).
    """
    if value is None:
        return ""
    text = " ".join(value.strip().split())
    if not text:
        return ""

    def _cap_piece(piece: str) -> str:
        if not piece:
            return piece
        return piece[0].upper() + piece[1:].lower()

    words: list[str] = []
    for word in text.split(" "):
        words.append("-".join(_cap_piece(p) for p in word.split("-")))
    return " ".join(words)
