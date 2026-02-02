#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from math import ceil
from pathlib import Path
from typing import Any, Optional, Tuple

import requests

# =============================================================================
# Paths / data folder
# =============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TRANSLATIONS_FILE = DATA_DIR / "translations_ja_en.json"
MAPPINGS_FILE = DATA_DIR / "mappings_snkrdunk_to_shopify.json"
DEFAULT_RESULTS_FILE = DATA_DIR / "results.json"
RESULTS_FILE = Path(os.getenv("RESULTS_FILE", str(DEFAULT_RESULTS_FILE))).expanduser()
DEFAULT_SHOPIFY_SNAPSHOT = SCRIPT_DIR / "shopify" / "collection_444175384827_active_variants.json"
SHOPIFY_LOCAL_FILE = Path(os.getenv("SHOPIFY_SNAPSHOT_FILE", str(DEFAULT_SHOPIFY_SNAPSHOT))).expanduser()
# =============================================================================
# SNKRDUNK API
# =============================================================================
SNKRDUNK_API_URL = "https://snkrdunk.com/v1/apparel/market/category"
BASE_WEB = "https://snkrdunk.com"

PER_PAGE = 25
PAGES_TO_FETCH = [1, 2, 3, 4, 5, 6]

COMMON_PARAMS = {
    "perPage": PER_PAGE,
    "order": "popular",
    "apparelCategoryId": 14,
    "apparelSubCategoryId": 0,
    "brandId": "pokemon",
    "departmentName": "hobby",
}

SNKRDUNK_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://snkrdunk.com/",
}

# =============================================================================
# Google Translate (v2 REST)
# =============================================================================
GOOGLE_TRANSLATE_V2_URL = "https://translation.googleapis.com/language/translate/v2"
GOOGLE_API_KEY_ENV = "GOOGLE_TRANSLATE_API_KEY"

# =============================================================================
# FX rates (Frankfurter, no key)
# =============================================================================
FRANKFURTER_LATEST_URL = "https://api.frankfurter.dev/v1/latest"

# =============================================================================
# Pricing adjustments / business rules
# =============================================================================
SHIPPING_COST_JPY = 500  # flat per product
MIN_MARGIN = 0.20       # 20% minimum margin on net (ex VAT) price
VAT_RATE = 0.25         # 25% VAT to be included in final price
ROUND_UP_STEP_NOK = 25  # round up to nearest 25 NOK

# =============================================================================
# Filtering rules
# =============================================================================
DISREGARD_TYPE_EN = {"pack"}     # drop packs entirely (based on parsed type)
DISREGARD_BOX_IF_NO_SHRINK = True

# Extra safety filter:
# If English title contains "Pack" AND min_price_jpy <= 2000 -> disregard (these are usually cheap packs).
PACK_TITLE_MAX_JPY = 2000

# Filter out any items where translated title contains "[No Shrink Wrap]"
NO_SHRINK_WRAP_EN_TAG = "[no shrink wrap]"

NO_SHRINK_JA_RE = re.compile(r"シュリンク\s*なし")

QUOTED_NAME_RE = re.compile(r'^(?P<prefix>.+?)\s+"(?P<name>[^"]+)"\s+(?P<type>[^"]+?)\s*$')
SINGLE_QUOTED_NAME_RE = re.compile(r"^(?P<prefix>.+?)\s+'(?P<name>[^']+)'\s+(?P<type>[^']+?)\s*$")

SHOPIFY_MATCH_THRESHOLD = 0.62
PRICE_OK_BAND_NOK = 25

# =============================================================================
# Mapping persistence rules
# =============================================================================
# IMPORTANT: Once a mapping exists, we DO NOT modify it automatically.
# We only add mappings for NEW snkrdunk keys that do not exist yet.
# That way, any manual corrections persist.
AUTO_ADD_MISSING_MAPPINGS = True

@dataclass(frozen=True)
class ShopifyMatch:
    matched: bool
    confidence: Optional[float]
    product_id: Optional[str]
    product_title: Optional[str]
    handle: Optional[str]
    variant_id: Optional[str]
    variant_title: Optional[str]
    current_price_nok_inc_vat: Optional[float]
    compare_at_price_nok_inc_vat: Optional[float]
    inventory_quantity: Optional[int]
    available_for_sale: Optional[bool]
    recommended_price_nok_inc_vat: Optional[int]
    price_delta_nok: Optional[float]
    action: Optional[str]
    mapping_source: str  # "manual" or "auto" or "none"

@dataclass(frozen=True)
class Item:
    apparel_id: int
    name_ja: str
    name_en: Optional[str]
    series_en: Optional[str]
    type_en: Optional[str]
    name_en_short: Optional[str]
    shrink_wrap: bool
    price_text_jpy: str
    min_price_jpy: Optional[int]
    shipping_cost_jpy: int
    shipping_cost_nok: Optional[float]
    estimated_price_nok: Optional[float]
    estimated_price_nok_shipping: Optional[float]
    recommended_sale_price_nok_inc_vat: Optional[int]
    recommended_sale_price_nok_ex_vat: Optional[float]
    target_cost_basis_nok_ex_vat: Optional[float]
    shopify: ShopifyMatch
    link: str
    image: Optional[str]

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def load_kv_cache(path: Path) -> dict[str, str]:
    data = load_json(path)
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}

def save_kv_cache(path: Path, cache: dict[str, str]) -> None:
    atomic_write_json(path, cache)

def build_snkrdunk_key(series_en: Optional[str], name_short: Optional[str], type_en: Optional[str], shrink_wrap: bool) -> str:
    return f"{(series_en or '').strip()}|{(name_short or '').strip()}|{(type_en or '').strip()}|{str(shrink_wrap).lower()}"

def load_mapping_table(path: Path) -> dict[str, Any]:
    data = load_json(path)
    if not isinstance(data, dict):
        return {"version": 2, "generated_at_utc": None, "mappings": {}}
    mappings = data.get("mappings")
    if not isinstance(mappings, dict):
        mappings = {}
    return {"version": int(data.get("version", 2)), "generated_at_utc": data.get("generated_at_utc"), "mappings": mappings}

def save_mapping_table(path: Path, mapping_table: dict[str, Any]) -> None:
    mapping_table["version"] = 2
    mapping_table["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    mappings = mapping_table.get("mappings", {})
    cleaned: dict[str, Any] = {}
    for k, v in (mappings.items() if isinstance(mappings, dict) else []):
        if not isinstance(v, dict):
            continue
        cleaned[k] = {
            "product_id": v.get("product_id"),
            "handle": v.get("handle"),
            "notes": v.get("notes"),
            "disabled": bool(v.get("disabled", False)),
        }
    mapping_table["mappings"] = cleaned
    atomic_write_json(path, mapping_table)

def build_item_link(apparel_id: int) -> str:
    return f"{BASE_WEB}/apparels/{apparel_id}?slide=right"

def normalize_image(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return url if "?" in url else (url + "?size=m")

def get_google_api_key() -> str:
    key = os.getenv(GOOGLE_API_KEY_ENV, "").strip()
    if not key:
        raise SystemExit(
            f"ERROR: Missing Google Translate API key.\n"
            f"Set env var {GOOGLE_API_KEY_ENV}.\n\n"
            f'PowerShell:\n  setx {GOOGLE_API_KEY_ENV} "YOUR_KEY"\n\n'
            f"Then reopen your terminal."
        )
    return key

def translate_ja_to_en(
    text: str,
    session: requests.Session,
    api_key: str,
    cache: dict[str, str],
    cache_path: Path,
    save_every: int = 25,
) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if text in cache:
        return cache[text]

    payload = {"q": text, "source": "ja", "target": "en", "format": "text", "key": api_key}
    translated = ""
    for attempt in range(1, 4):
        try:
            r = session.post(GOOGLE_TRANSLATE_V2_URL, data=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            translated_raw = data.get("data", {}).get("translations", [{}])[0].get("translatedText", "")
            translated = html.unescape((translated_raw or "").strip())
            break
        except Exception:
            time.sleep(0.6 * attempt)

    cache[text] = translated
    if len(cache) % save_every == 0:
        save_kv_cache(cache_path, cache)
    time.sleep(0.15)
    return translated

def fetch_jpy_to_nok_rate(session: requests.Session) -> float:
    params = {"base": "JPY", "symbols": "NOK"}
    r = session.get(FRANKFURTER_LATEST_URL, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    rate = (data.get("rates", {}) or {}).get("NOK", None)
    if not isinstance(rate, (int, float)):
        raise RuntimeError(f"Unexpected FX response: {data}")
    return float(rate)

def parse_en_name_fields(name_en: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not name_en:
        return None, None, None
    s = name_en.strip()
    m = QUOTED_NAME_RE.match(s) or SINGLE_QUOTED_NAME_RE.match(s)
    if not m:
        return None, None, None
    series = m.group("prefix").strip().rstrip(" -–—:")
    name_short = m.group("name").strip()
    type_ = m.group("type").strip().rstrip(" -–—:")
    return (series or None), (type_ or None), (name_short or None)

def detect_shrink_wrap(name_ja: str) -> bool:
    return not bool(NO_SHRINK_JA_RE.search(name_ja or ""))

def extract_price_fields(a: dict[str, Any]) -> tuple[str, Optional[int]]:
    display_price = (a.get("displayPrice") or "").strip()
    min_price = a.get("minPrice", None)
    if display_price and display_price != "-":
        price_text = display_price + "〜"
    elif isinstance(min_price, int):
        price_text = f"¥{min_price:,}〜"
    else:
        price_text = "(no price)"
    return price_text, (min_price if isinstance(min_price, int) else None)

def extract_item(a: dict[str, Any]) -> tuple[int, str, str, Optional[str], Optional[int]]:
    apparel_id = int(a["id"])
    name_ja = (a.get("localizedName") or "").strip() or (a.get("name") or "").strip()
    price_text, min_price_jpy = extract_price_fields(a)
    pm = a.get("primaryMedia") or {}
    img = normalize_image(pm.get("imageUrl") or None)
    return apparel_id, name_ja, price_text, img, min_price_jpy

def fetch_snkrdunk_page(session: requests.Session, page_num: int) -> list[dict[str, Any]]:
    params = dict(COMMON_PARAMS)
    params["page"] = page_num
    r = session.get(SNKRDUNK_API_URL, params=params, headers=SNKRDUNK_HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    apparels = data.get("apparels", [])
    return [x for x in apparels if isinstance(x, dict) and "id" in x]

def round_up_to_step(value: float, step: int) -> int:
    return int(ceil(value / step) * step) if step > 0 else int(ceil(value))

def compute_recommended_prices(cost_basis_nok_ex_vat: Optional[float]) -> tuple[Optional[float], Optional[int]]:
    if cost_basis_nok_ex_vat is None:
        return None, None
    required_net = cost_basis_nok_ex_vat / (1.0 - MIN_MARGIN)
    required_gross = required_net * (1.0 + VAT_RATE)
    rounded_gross = round_up_to_step(required_gross, ROUND_UP_STEP_NOK)
    net_from_rounded = round(rounded_gross / (1.0 + VAT_RATE), 2)
    return net_from_rounded, rounded_gross

def should_disregard_item(type_en: Optional[str], shrink_wrap: bool) -> bool:
    t = (type_en or "").strip().lower()
    if t in DISREGARD_TYPE_EN:
        return True
    if DISREGARD_BOX_IF_NO_SHRINK and t == "box" and not shrink_wrap:
        return True
    return False

def should_disregard_pack_by_title_and_price(name_en: Optional[str], min_price_jpy: Optional[int]) -> bool:
    if not name_en or not isinstance(min_price_jpy, int):
        return False
    if min_price_jpy > PACK_TITLE_MAX_JPY:
        return False
    return bool(re.search(r"\bpack\b", name_en.lower()))

def should_disregard_no_shrink_wrap_tag(name_en: Optional[str]) -> bool:
    if not name_en:
        return False
    return NO_SHRINK_WRAP_EN_TAG in name_en.strip().lower()

def normalize_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"[\[\]\(\)\{\}]", " ", s)
    s = re.sub(r"[^a-z0-9\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def similarity(a: str, b: str) -> float:
    a_n = normalize_text(a)
    b_n = normalize_text(b)
    if not a_n or not b_n:
        return 0.0
    return SequenceMatcher(None, a_n, b_n).ratio()

def load_shopify_products(path: Path) -> list[dict[str, Any]]:
    data = load_json(path)
    if not isinstance(data, dict):
        return []
    products = data.get("products", [])
    if not isinstance(products, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for p in products:
        if not isinstance(p, dict):
            continue
        if (p.get("status") or "").upper() != "ACTIVE":
            continue
        variants = p.get("variants", [])
        if not isinstance(variants, list) or not variants:
            continue
        cleaned.append(p)
    return cleaned

def find_shopify_product(shopify_products: list[dict[str, Any]], product_id: Optional[str], handle: Optional[str]) -> Optional[dict[str, Any]]:
    for p in shopify_products:
        pid = str(p.get("product_id") or "")
        h = str(p.get("handle") or "")
        if product_id and pid == product_id:
            return p
        if handle and h == handle:
            return p
    return None

def auto_shopify_match(series_en: Optional[str], type_en: Optional[str], name_short: Optional[str], shopify_products: list[dict[str, Any]]) -> tuple[Optional[dict[str, Any]], float]:
    if not shopify_products or not (series_en or name_short):
        return None, 0.0
    candidates: list[str] = []
    if series_en and name_short and type_en:
        candidates += [
            f"{name_short} {type_en} {series_en}",
            f"{series_en} {name_short} {type_en}",
            f"{name_short} {type_en}",
            f"{name_short}",
        ]
    elif series_en:
        candidates.append(series_en)
    elif name_short:
        candidates.append(name_short)

    best_p = None
    best_score = 0.0
    for p in shopify_products:
        title = str(p.get("title") or "")
        handle = str(p.get("handle") or "")
        score = 0.0
        for c in candidates:
            score = max(score, similarity(c, title), similarity(c, handle))
        if score > best_score:
            best_score = score
            best_p = p
    return best_p, best_score

def parse_primary_variant(p: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """
    Primary variant for pricing/matching.
    After you split products into Type=Booster Box/Booster Pack, the first variant
    is not guaranteed to be the box. We therefore prefer the 'Booster Box' variant.
    """
    if not p:
        return None
    variants = p.get("variants", [])
    if not isinstance(variants, list) or not variants:
        return None

    for v in variants:
        if str((v or {}).get("variant_title") or "").strip().lower() == "booster box":
            return v
    return variants[0]

    for v in variants:
        if str((v or {}).get("variant_title") or "").strip().lower() == "booster box":
            return v

    return variants[0]

def parse_variant_pricing(v: Optional[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[int], Optional[bool], Optional[str], Optional[str]]:
    if not v:
        return None, None, None, None, None, None
    price = None
    compare_at = None
    try:
        if v.get("price") is not None:
            price = float(v["price"])
    except Exception:
        price = None
    try:
        if v.get("compare_at_price") is not None:
            compare_at = float(v["compare_at_price"])
    except Exception:
        compare_at = None
    inv = v.get("inventory_quantity")
    inv_i = int(inv) if isinstance(inv, int) else None
    afs = v.get("available_for_sale")
    afs_b = bool(afs) if isinstance(afs, bool) else None
    return price, compare_at, inv_i, afs_b, v.get("variant_id"), v.get("variant_title")

def decide_action(current_price: Optional[float], recommended: Optional[int]) -> tuple[Optional[float], str]:
    if current_price is None or recommended is None:
        return None, "unknown"
    delta = round(current_price - float(recommended), 2)
    if abs(delta) <= PRICE_OK_BAND_NOK:
        return delta, "ok"
    if delta < 0:
        return delta, "increase"
    return delta, "decrease"

def main() -> int:
    api_key = get_google_api_key()

    translations = load_kv_cache(TRANSLATIONS_FILE)
    mapping_table = load_mapping_table(MAPPINGS_FILE)
    mappings: dict[str, Any] = mapping_table.get("mappings", {}) if isinstance(mapping_table.get("mappings"), dict) else {}
    mapping_changed = False
    translations_changed = False

    if not SHOPIFY_LOCAL_FILE.exists():
        print(f"ERROR: Shopify snapshot missing: {SHOPIFY_LOCAL_FILE}")
        print("Run: python shopify_fetch_collection.py")
        return 1

    shopify_products = load_shopify_products(SHOPIFY_LOCAL_FILE)
    if not shopify_products:
        print(f"WARNING: Could not load Shopify products from: {SHOPIFY_LOCAL_FILE}")

    skipped_pack = 0
    skipped_pack_title_price = 0
    skipped_no_shrink_box = 0
    skipped_no_shrink_wrap_tag = 0
    kept = 0

    all_items_by_link: dict[str, Item] = {}

    with requests.Session() as s:
        fx_jpy_to_nok = fetch_jpy_to_nok_rate(s)
        shipping_cost_nok = round(SHIPPING_COST_JPY * fx_jpy_to_nok, 2)
        print(f"FX JPY->NOK rate (NOK per 1 JPY): {fx_jpy_to_nok:.6f}")

        for page_num in PAGES_TO_FETCH:
            print(f"\n=== SNKRDUNK API PAGE {page_num} ===")
            apparels = fetch_snkrdunk_page(s, page_num)
            print(f"Found {len(apparels)} items")

            for a in apparels:
                apparel_id, name_ja, price_text, img, min_price_jpy = extract_item(a)
                link = build_item_link(apparel_id)

                shrink_wrap = detect_shrink_wrap(name_ja)

                before_len = len(translations)
                name_en_full = translate_ja_to_en(
                    name_ja, s, api_key, translations, TRANSLATIONS_FILE, save_every=25
                ).strip()
                if len(translations) != before_len:
                    translations_changed = True

                name_en = name_en_full or None

                # Filter out "[No Shrink Wrap]" in translated title
                if should_disregard_no_shrink_wrap_tag(name_en):
                    skipped_no_shrink_wrap_tag += 1
                    continue

                series_en, type_en, name_short = parse_en_name_fields(name_en)

                # Existing filter (type_en-based)
                if should_disregard_item(type_en, shrink_wrap):
                    t = (type_en or "").strip().lower()
                    if t == "pack":
                        skipped_pack += 1
                    elif t == "box" and not shrink_wrap:
                        skipped_no_shrink_box += 1
                    continue

                # Extra filter (title contains "Pack" + cheap)
                if should_disregard_pack_by_title_and_price(name_en, min_price_jpy):
                    skipped_pack_title_price += 1
                    continue

                estimated_nok = None
                estimated_nok_shipping = None
                cost_basis_nok_ex_vat = None
                if isinstance(min_price_jpy, int):
                    estimated_nok = round(min_price_jpy * fx_jpy_to_nok, 2)
                    estimated_nok_shipping = round((min_price_jpy + SHIPPING_COST_JPY) * fx_jpy_to_nok, 2)
                    cost_basis_nok_ex_vat = estimated_nok_shipping

                rec_net, rec_gross = compute_recommended_prices(cost_basis_nok_ex_vat)

                # ============================
                # Mapping: strictly persistent
                # ============================
                snk_key = build_snkrdunk_key(series_en, name_short, type_en, shrink_wrap)
                mapping_entry = mappings.get(snk_key)

                mapped_product_id = None
                mapped_handle = None
                mapping_disabled = False
                if isinstance(mapping_entry, dict):
                    mapping_disabled = bool(mapping_entry.get("disabled", False))
                    mapped_product_id = mapping_entry.get("product_id")
                    mapped_handle = mapping_entry.get("handle")

                # Determine Shopify product using mapping if present, otherwise auto-match (but DO NOT write back unless NEW)
                match_source = "none"
                shopify_product: Optional[dict[str, Any]] = None
                confidence = 0.0

                if mapping_disabled:
                    match_source = "manual"
                    shopify_product = None
                    confidence = 0.0
                elif mapped_product_id or mapped_handle:
                    match_source = "manual"
                    shopify_product = find_shopify_product(shopify_products, mapped_product_id, mapped_handle)
                    confidence = 1.0 if shopify_product is not None else 0.0
                else:
                    match_source = "auto"
                    shopify_product, confidence = auto_shopify_match(series_en, type_en, name_short, shopify_products)

                    # ONLY ADD mapping when it's missing; NEVER modify an existing key
                    if AUTO_ADD_MISSING_MAPPINGS and snk_key not in mappings:
                        mappings[snk_key] = {
                            "product_id": str(shopify_product.get("product_id")) if isinstance(shopify_product, dict) else None,
                            "handle": str(shopify_product.get("handle")) if isinstance(shopify_product, dict) else None,
                            "notes": "auto-generated; edit as needed",
                            "disabled": False,
                        }
                        mapping_changed = True

                if not isinstance(shopify_product, dict) or confidence < SHOPIFY_MATCH_THRESHOLD:
                    shopify_match = ShopifyMatch(
                        matched=False,
                        confidence=round(confidence, 4) if confidence else None,
                        product_id=None,
                        product_title=None,
                        handle=None,
                        variant_id=None,
                        variant_title=None,
                        current_price_nok_inc_vat=None,
                        compare_at_price_nok_inc_vat=None,
                        inventory_quantity=None,
                        available_for_sale=None,
                        recommended_price_nok_inc_vat=rec_gross,
                        price_delta_nok=None,
                        action="unknown",
                        mapping_source=match_source,
                    )
                else:
                    v = parse_primary_variant(shopify_product)
                    price, compare_at, inv, afs, variant_id, variant_title = parse_variant_pricing(v)
                    delta, action = decide_action(price, rec_gross)
                    shopify_match = ShopifyMatch(
                        matched=True,
                        confidence=round(confidence, 4),
                        product_id=str(shopify_product.get("product_id") or None),
                        product_title=str(shopify_product.get("title") or None),
                        handle=str(shopify_product.get("handle") or None),
                        variant_id=str(variant_id or None),
                        variant_title=str(variant_title or None),
                        current_price_nok_inc_vat=price,
                        compare_at_price_nok_inc_vat=compare_at,
                        inventory_quantity=inv,
                        available_for_sale=afs,
                        recommended_price_nok_inc_vat=rec_gross,
                        price_delta_nok=delta,
                        action=action,
                        mapping_source=match_source,
                    )

                all_items_by_link[link] = Item(
                    apparel_id=apparel_id,
                    name_ja=name_ja,
                    name_en=name_en,
                    series_en=series_en,
                    type_en=type_en,
                    name_en_short=name_short,
                    shrink_wrap=shrink_wrap,
                    price_text_jpy=price_text,
                    min_price_jpy=min_price_jpy,
                    shipping_cost_jpy=SHIPPING_COST_JPY,
                    shipping_cost_nok=shipping_cost_nok,
                    estimated_price_nok=estimated_nok,
                    estimated_price_nok_shipping=estimated_nok_shipping,
                    recommended_sale_price_nok_inc_vat=rec_gross,
                    recommended_sale_price_nok_ex_vat=rec_net,
                    target_cost_basis_nok_ex_vat=cost_basis_nok_ex_vat,
                    shopify=shopify_match,
                    link=link,
                    image=img,
                )
                kept += 1

            time.sleep(0.35)

    if translations_changed or not TRANSLATIONS_FILE.exists():
        save_kv_cache(TRANSLATIONS_FILE, translations)

    # Save mapping table ONLY if new keys were added or file doesn't exist.
    mapping_table["mappings"] = mappings
    if mapping_changed or not MAPPINGS_FILE.exists():
        save_mapping_table(MAPPINGS_FILE, mapping_table)

    items = list(all_items_by_link.values())
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {"snkrdunk_api": SNKRDUNK_API_URL, "pages": PAGES_TO_FETCH, "params": COMMON_PARAMS},
        "fx": {"provider": "frankfurter", "pair": "JPY->NOK", "rate_nok_per_1_jpy": fx_jpy_to_nok},
        "pricing_adjustments": {
            "shipping_cost_jpy_per_item": SHIPPING_COST_JPY,
            "min_margin_on_net": MIN_MARGIN,
            "vat_rate": VAT_RATE,
            "round_up_step_nok": ROUND_UP_STEP_NOK,
        },
        "filters": {
            "disregard_type_en": sorted(list(DISREGARD_TYPE_EN)),
            "disregard_box_if_no_shrink": DISREGARD_BOX_IF_NO_SHRINK,
            "disregard_if_title_contains_pack_and_min_price_jpy_le": PACK_TITLE_MAX_JPY,
            "disregard_if_name_en_contains": "[No Shrink Wrap]",
        },
        "shopify_matching": {
            "shopify_local_file": str(SHOPIFY_LOCAL_FILE),
            "match_threshold": SHOPIFY_MATCH_THRESHOLD,
            "price_ok_band_nok": PRICE_OK_BAND_NOK,
            "mapping_file": str(MAPPINGS_FILE),
            "mapping_persistence": "existing keys are never modified automatically; only new keys are added",
        },
        "counters": {
            "kept": kept,
            "skipped_pack_by_type_en": skipped_pack,
            "skipped_pack_by_title_and_price": skipped_pack_title_price,
            "skipped_no_shrink_box": skipped_no_shrink_box,
            "skipped_no_shrink_wrap_tag": skipped_no_shrink_wrap_tag,
            "new_mappings_added_this_run": int(mapping_changed),
        },
        "items": [asdict(i) for i in items],
    }
    atomic_write_json(RESULTS_FILE, payload)

    print("\n=== DONE ===")
    print(f"Kept items: {kept}")
    print(f"Skipped Pack items (type_en == 'Pack'): {skipped_pack}")
    print(f"Skipped Pack items (title contains 'Pack' and min_price_jpy <= {PACK_TITLE_MAX_JPY}): {skipped_pack_title_price}")
    print(f"Skipped no-shrink Box items (JA title says シュリンクなし): {skipped_no_shrink_box}")
    print(f"Skipped items with '[No Shrink Wrap]' in translated title: {skipped_no_shrink_wrap_tag}")
    print(f"Translations cache: {len(translations)} entries -> {TRANSLATIONS_FILE}")
    print(f"Mappings table: {len(mappings)} entries -> {MAPPINGS_FILE}")
    print(f"Results -> {RESULTS_FILE}\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
