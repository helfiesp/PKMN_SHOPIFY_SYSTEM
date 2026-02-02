# competition/scrape_utils.py
from __future__ import annotations

from urllib.parse import urljoin, urlparse


def el_text(el) -> str:
    if el is None:
        return ""
    t = (el.text or "").strip()
    if t:
        return t
    return (el.get_attribute("textContent") or "").strip()


def normalize_url(href: str, *, base: str) -> str:
    """
    Normalize product links to a stable key:
    - join relative URLs to base
    - drop querystring + fragment
    """
    href = (href or "").strip()
    if not href:
        return ""
    abs_url = href if href.startswith("http") else urljoin(base, href)
    u = urlparse(abs_url)
    return f"{u.scheme}://{u.netloc}{u.path}"
