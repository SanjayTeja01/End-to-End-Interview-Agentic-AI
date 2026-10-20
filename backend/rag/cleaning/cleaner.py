"""Text cleaning for extracted documents and resumes."""
from __future__ import annotations

import re
import unicodedata


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", "")
    text = re.sub(r"[​-‏﻿]", "", text)  # zero-width chars
    text = re.sub(r"-\n(?=[a-z])", "", text)  # de-hyphenate line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Drop lines that are just page numbers
    text = "\n".join(l for l in text.split("\n") if not re.fullmatch(r"(page )?\d{1,3}( of \d{1,3})?", l.strip(), re.I))
    return text.strip()
