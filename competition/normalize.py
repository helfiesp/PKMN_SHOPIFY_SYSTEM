from __future__ import annotations

import re

# IMPORTANT:
# - detect_category/detect_brand should work on RAW (or pre-strip) strings too
# - normalize_name should REMOVE tokens that belong in brand/category
#   so you can match products across competitors

# NOTE: CATEGORY_RULES are ordered by priority.
# Put the *more specific* concepts first so they win.


TYPO_MAP = {
    # known common typos
    "jugde": "judge",
}

def _apply_typos(s: str) -> str:
    # word-boundary replacements
    for wrong, right in TYPO_MAP.items():
        s = re.sub(rf"\b{re.escape(wrong)}\b", right, s, flags=re.IGNORECASE)
    return s


CATEGORY_RULES: list[tuple[str, list[str]]] = [
    # Special groupings that should override generic "box" detection
    ("pokemon_center", [
        r"\bpokemon\s*center\b",
    ]),
    ("booster_bundle", [
        r"\bbooster\s*bundle\b",
        r"\bbundle\b\s*(?:\d+\s*)?\bbooster\b",  # e.g. "Bundle 6 Boosters"
    ]),
    ("mini_tin", [
        r"\bmini\s*tin(?:s)?\b",
    ]),

    ("elite_trainer_box", [
        r"\betb\b",
        r"\belite\s*trainer\s*box\b",
    ]),
    ("booster_box", [
        r"\bbooster\s*box\b",
        r"\bbooster\s*boks\b",
        r"\bboosterbokser\b",
        r"\bdisplay\b",
        r"\bdisplay\s*box\b",
    ]),
    ("1_pack_blister", [
        r"\b1\s*pack\s*blister\b",
        r"\bblister\s*pack\b",
        r"\bpack\s*blister\b",
        r"\bblister\b",
    ]),
    ("booster_pack", [
        r"\bbooster\s*pack\b",
        r"\bbooster\s*pakke\b",
        r"\bbooster\s*pakker\b",
        r"\bboosterpakker\b",
        r"\bbooster\s*[-–—]?\s*pakke\b",
        r"\bboosters?\b",  # some sites use plural english
        r"\bbooster\b",    # broad, but comes last so it won't steal bundle/box/etb
        r"\bpakke\b",
    ]),
    ("starter_deck", [
        r"\bstarter\b",
        r"\bstart\s*deck\b",
        r"\bstarter\s*deck\b",
        r"\bdeluxe\s*battle\s*deck\b",
        r"\bbattle\s*deck\b",
        r"\bdeck\b",
    ]),
    ("collection_box", [
        r"\bcollection\s*box\b",
        r"\bcollection\b",
    ]),
]

BRAND_RULES: list[tuple[str, list[str]]] = [
    ("pokemon", [r"\bpok[eé]mon\b", r"\bpokemon\b"]),
    ("one_piece", [
        r"\bone\s*piece\b",
        r"\bop\s*\d{1,2}\b",  # e.g. OP 01, OP 1, OP 14
    ]),
    ("lorcana", [r"\blorcana\b"]),
    ("mtg", [r"\bmagic\b", r"\bmtg\b"]),
]

# Tokens we want REMOVED from normalized_name, because they belong in brand/category
STRIP_PATTERNS = [
    # phrase-first stripping (so single-word strips don't break phrases)
    r"\bpokemon\s*center\b",

    # brand-ish
    r"\bpok[eé]mon\b",
    r"\bpokemon\b",
    r"\bone\s*piece\b",
    r"\blorcana\b",
    r"\bmagic\b",
    r"\bmtg\b",

    # language / condition tokens (do NOT belong in identity)
    r"\bjapansk\b",
    r"\bengelsk\b",
    r"\bnorsk\b",
    r"\btysk\b",
    r"\bfransk\b",
    r"\bitaliensk\b",
    r"\bspansk\b",
    r"\bkinesisk\b",
    r"\bkoreansk\b",
    r"\bjapanese\b",
    r"\benglish\b",
    r"\bnorwegian\b",
    r"\bgerman\b",
    r"\bfrench\b",
    r"\bitalian\b",
    r"\bspanish\b",
    r"\bchinese\b",
    r"\bkorean\b",
    r"\bjp\b",
    r"\ben\b",

    # quantity / per-person purchase limits
    r"\bmaks\b",
    r"\bmax\b",
    r"\bper\s*pers(?:on|\.|)\b",
    r"\bper\s*person\b",
    r"\bper\s*pers\.\b",
    r"\b\d+\s*per\s*pers(?:on|\.|)\b",

    # sales / meta tokens
    r"\bpre\s*order\b",
    r"\bpreorder\b",
    r"\bforh[aå]ndsbestilling\b",
    r"\bp[ée]r\s*order\b",
    r"\bpromo\b",
    r"\bpromokort\b",
    r"\bpromocard\b",
    r"\bspecial\s*set\b",
    r"\bspecial\b\s*set\b",

    # category-ish (common variants) — strip the *phrases*, not generic "box"
    r"\bmini\s*tin(?:s)?\b",
    r"\bbooster\s*bundle\b",

    r"\bbooster\s*boks\b",
    r"\bbooster\s*box\b",
    r"\bboosterbokser\b",
    r"\bbooster\s*pakke\b",
    r"\bbooster\s*[-–—]?\s*pakke\b",
    r"\bbooster\s*pack\b",
    r"\bboosterpakker\b",
    r"\bbooster\b",
    r"\bpakke\b",
    r"\bdisplay\b",

    r"\b1\s*pack\s*blister\b",
    r"\bblister\s*pack\b",
    r"\bpack\s*blister\b",
    r"\bblister\b",

    r"\betb\b",
    r"\belite\s*trainer\s*box\b",

    r"\bstarter\b",
    r"\bstart\s*deck\b",
    r"\bdeck\b",
    r"\bbattle\s*deck\b",
    r"\bdeluxe\s*battle\s*deck\b",

    # "collection" is usually meta; keep what matters (set name), drop it.
    r"\bcollection\s*box\b",
    r"\bcollection\b",
]

def _pre_normalize(s: str) -> str:
    """Normalize spelling variants BEFORE detection/stripping."""
    if not s:
        return ""
    s = s.strip().lower()
    s = _apply_typos(s)

    # normalize common spelling variants
    s = s.replace("pokémon", "pokemon")
    s = s.replace("booster boks", "booster box")
    s = s.replace("boosterbokser", "booster box")
    s = s.replace("booster pakke", "booster pack")
    s = s.replace("boosterpakker", "booster pack")

    # normalize common plural/singular forms
    s = s.replace("mini tins", "mini tin")
    s = s.replace("mini-tins", "mini tin")

    # normalize "pre-order" spelling
    s = s.replace("pre-order", "preorder")

    # common separators / punctuation -> spaces
    s = re.sub(r"[-–—:,_+/\\]", " ", s)

    # remove parenthesis blocks
    s = re.sub(r"\s*\([^)]*\)\s*", " ", s)

    # collapse spaces
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_category(name_or_normalized: str) -> str | None:
    s = _pre_normalize(name_or_normalized or "")
    for cat, patterns in CATEGORY_RULES:
        for p in patterns:
            if re.search(p, s, flags=re.IGNORECASE):
                return cat
    return None


def detect_brand(name_or_normalized: str) -> str | None:
    s = _pre_normalize(name_or_normalized or "")
    for brand, patterns in BRAND_RULES:
        for p in patterns:
            if re.search(p, s, flags=re.IGNORECASE):
                return brand
    return None


# -----------------
# Language detection
# -----------------
LANGUAGE_RULES: list[tuple[str, list[str]]] = [
    ("ja", [
        r"\bjapansk\b",
        r"\bjapanese\b",
        r"\bjpn\b",
        r"\bjp\b",
    ]),
    ("zh", [
        r"\bkinesisk\b",
        r"\bchinese\b",
        r"\bcn\b",
    ]),
    ("ko", [
        r"\bkoreansk\b",
        r"\bkorean\b",
    ]),
    ("en", [
        r"\bengelsk\b",
        r"\benglish\b",
        r"\ben\b",
    ]),
]


def detect_language(name_or_normalized: str) -> str:
    """Return a short language code: en (default), ja, zh, ko."""
    s = _pre_normalize(name_or_normalized or "")
    for lang, patterns in LANGUAGE_RULES:
        for p in patterns:
            if re.search(p, s, flags=re.IGNORECASE):
                return lang
    return "en"


def normalize_name(name: str) -> str:
    """
    Return a normalized name intended for cross-site matching.
    Removes:
      - brand tokens (pokemon, one piece, ...)
      - category tokens (booster box/pack/bundle, mini tin, etb, display, ...)
      - language + sales/meta tokens (japansk/engelsk, preorder, promo, ...)
      - purchase limits ("maks 2 per person", etc.)
    Keeps the unique product identity (set name etc).
    """
    if not name:
        return ""

    s = _pre_normalize(name)

    # Strip tokens that should live in brand/category fields
    for pat in STRIP_PATTERNS:
        s = re.sub(pat, " ", s, flags=re.IGNORECASE)

    # Final cleanup
    s = re.sub(r"[^a-z0-9\s]", " ", s)   # conservative: keep letters/numbers
    s = re.sub(r"\s+", " ", s).strip()

    return s
