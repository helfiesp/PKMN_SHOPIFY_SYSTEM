from __future__ import annotations

import re

def parse_price_ore(raw: str | None) -> int:
    """
    Parse a price string into øre (int).

    Handles common Norwegian + Shopify formats:
      "999"            -> 99900
      "999,00"         -> 99900
      "999,00 kr"      -> 99900
      "1.299,00 kr"    -> 129900
      "1299.00"        -> 129900
      "1.299"          -> 129900
      "NOK 1 299,00"   -> 129900
    """
    if not raw:
        return 0

    s = raw.replace("\xa0", " ").strip()
    s = s.replace("NOK", "").replace("nok", "")
    s = s.replace("kr", "").replace("Kr", "").strip()

    # keep only digits and separators
    s = re.sub(r"[^0-9,\.]", "", s)
    if not s:
        return 0

    # When both comma and dot present, the LAST one is the decimal separator
    if "," in s and "." in s:
        comma_pos = s.rfind(",")
        dot_pos = s.rfind(".")
        
        if dot_pos > comma_pos:
            # dot is last = dot is decimal separator (e.g., "1,299.00")
            s = s.replace(",", "")  # drop thousands (comma)
            whole, frac = (s.split(".", 1) + [""])[:2]
        else:
            # comma is last = comma is decimal separator (e.g., "1.299,00")
            s = s.replace(".", "")  # drop thousands (dot)
            whole, frac = (s.split(",", 1) + [""])[:2]
        
        whole = whole or "0"
        frac = (frac or "00")
        if len(frac) == 1:
            frac += "0"
        frac = frac[:2]
        try:
            return int(whole) * 100 + int(frac)
        except Exception:
            digits = "".join(ch for ch in s if ch.isdigit())
            return int(digits) if digits else 0
    
    # comma as decimal separator (Norwegian) - only comma present
    if "," in s:
        s = s.replace(".", "")  # drop thousands
        whole, frac = (s.split(",", 1) + [""])[:2]
        whole = whole or "0"
        frac = (frac or "00")
        if len(frac) == 1:
            frac += "0"
        frac = frac[:2]
        try:
            return int(whole) * 100 + int(frac)
        except Exception:
            digits = "".join(ch for ch in s if ch.isdigit())
            return int(digits) if digits else 0

    # dot can be decimal separator OR thousands separator
    if "." in s:
        left, right = s.rsplit(".", 1)
        if len(right) == 2:  # looks like decimals
            left = left.replace(".", "")
            try:
                return int(left) * 100 + int(right)
            except Exception:
                pass
        # otherwise treat as thousands separators
        s = s.replace(".", "")

    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return 0

    # whole NOK
    return int(digits) * 100


def format_ore(ore: int | None) -> str:
    """Format øre as Norwegian-style string: 129900 -> '1.299,00'."""
    if ore is None:
        return "0,00"
    nok = ore // 100
    frac = ore % 100
    nok_str = f"{nok:,}".replace(",", ".")
    return f"{nok_str},{frac:02d}"
