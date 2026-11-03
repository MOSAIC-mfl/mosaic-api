"""Text folding: the one rule for comparing what people type with what the catalogue holds.

Used for word search, for filter values and for ids in URLs, so "PERU", "Perú" and "peru" are the
same, and "CC BY 4.0", "cc-by-4.0" and "CC-BY-4.0" are the same.

* case-insensitive (``casefold``: also handles ß -> ss);
* accent-insensitive (NFKD, combining marks removed; ø, æ, œ, đ, ł, þ transliterated);
* any run of spaces, punctuation or symbols is one separator;
* letters of any script are kept (non-Latin titles stay searchable).

The website applies the same rule to the static export; see docs/architecture.md, section 3.
"""

from __future__ import annotations

import re
import unicodedata

_EXTRA = str.maketrans({"ø": "o", "æ": "ae", "œ": "oe", "đ": "d", "ł": "l", "þ": "th", "ı": "i"})
_SEPARATORS = re.compile(r"[\W_]+", re.UNICODE)


def fold(text: str) -> str:
    """Normalized words separated by single spaces: 'Côte d’Ivoire – 2021' -> 'cote d ivoire 2021'."""
    s = unicodedata.normalize("NFKD", text.casefold())
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).translate(_EXTRA)
    return _SEPARATORS.sub(" ", s).strip()


def key(value: str) -> str:
    """Comparison key for codes and ids: 'CC BY 4.0' -> 'cc-by-4-0', 'PER-PCL' -> 'per-pcl'."""
    return fold(value).replace(" ", "-")
