"""Email notification service using Resend."""
from datetime import datetime
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo

import resend


def _get_email_settings(db) -> dict:
    """Read email settings from the database."""
    from app.models import Setting
    keys = ["resend_api_key", "notification_email", "email_notifications_enabled", "notification_from_email"]
    result = {}
    for key in keys:
        row = db.query(Setting).filter(Setting.key == key).first()
        result[key] = row.value.strip() if row and row.value else ""
    return result


def _format_nok(value) -> str:
    """Format a number as NOK with Norwegian locale style (e.g., kr 1 234)."""
    try:
        v = float(value)
        if v == int(v):
            return f"kr {int(v):,}".replace(",", " ")
        return f"kr {v:,.2f}".replace(",", " ")
    except (ValueError, TypeError):
        return str(value)


def _delta_color(delta) -> str:
    try:
        d = float(delta)
        if d > 0:
            return "#dc2626"
        if d < 0:
            return "#16a34a"
    except (ValueError, TypeError):
        pass
    return "#6b7280"


def _stock_color(qty) -> str:
    if qty <= 0:
        return "#dc2626"
    if qty <= 3:
        return "#ea580c"
    return "#d97706"


def _get_low_stock_products(db) -> List[Dict[str, Any]]:
    """Query booster box variants with inventory_quantity <= 5."""
    from app.models import Product, Variant
    from sqlalchemy import and_

    rows = (
        db.query(Product, Variant)
        .join(Variant, Product.id == Variant.product_id)
        .filter(
            and_(
                Product.status == "ACTIVE",
                Variant.inventory_quantity <= 5,
                Variant.option_value.ilike("%box%"),
            )
        )
        .order_by(Variant.inventory_quantity.asc())
        .all()
    )

    results = []
    for product, variant in rows:
        results.append({
            "title": product.title or "Unknown",
            "image_url": product.image_url or "",
            "variant": variant.option_value or variant.title or "Box",
            "stock": variant.inventory_quantity or 0,
            "price": float(variant.price) if variant.price else 0,
        })
    return results


# ── Shared style constants ────────────────────────────────────────────────

_S = {
    "bg": "#f0f2f5",
    "card": "#ffffff",
    "border": "#e2e5ea",
    "text": "#1a1d23",
    "text2": "#5f6672",
    "text3": "#8b919d",
    "accent": "#4f46e5",
    "accent_light": "#eef2ff",
    "success": "#16a34a",
    "danger": "#dc2626",
    "warning": "#d97706",
    "header_bg": "linear-gradient(135deg,#312e81 0%,#4f46e5 50%,#6366f1 100%)",
}

_TH = (
    "padding:10px 12px;text-align:left;font-size:10px;color:#8b919d;"
    "text-transform:uppercase;letter-spacing:0.8px;font-weight:600;"
    "border-bottom:2px solid #e2e5ea"
)

_TD = "padding:10px 12px;border-bottom:1px solid #f0f2f5;font-size:13px;color:#1a1d23"


def _build_price_update_html(
    results: List[Dict[str, Any]],
    settings_summary: Dict[str, Any],
    errors: List[Dict[str, Any]],
    low_stock: List[Dict[str, Any]],
) -> str:
    """Build a polished HTML email for the SNKRDUNK price update report."""
    now = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%d.%m.%Y kl. %H:%M")

    pushed = [r for r in results if r.get("pushed")]
    skipped = [r for r in results if not r.get("pushed") and not r.get("shopify_error")]
    failed = [r for r in results if r.get("shopify_error")]

    rate = settings_summary.get("rate", "?")
    shipping = settings_summary.get("shipping_jpy", "?")
    margin = settings_summary.get("margin_pct", "?")
    pack_markup = settings_summary.get("pack_markup_pct", "?")

    # ── Header ──
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:{_S['bg']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased">
<div style="max-width:680px;margin:0 auto;padding:24px 12px">

<!-- Header -->
<div style="background:{_S['header_bg']};border-radius:16px 16px 0 0;padding:32px;text-align:center">
    <div style="font-size:36px;margin-bottom:8px">&#128200;</div>
    <h1 style="margin:0;font-size:24px;font-weight:800;color:#ffffff;letter-spacing:-0.3px">Price Update Report</h1>
    <p style="margin:8px 0 0;font-size:13px;color:rgba(255,255,255,0.7)">{now}</p>
</div>

<!-- Stats bar -->
<div style="background:{_S['card']};border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};padding:24px 20px">
<table width="100%" cellpadding="0" cellspacing="0"><tr>
    <td align="center" width="25%" style="padding:8px">
        <div style="background:#f0fdf4;border-radius:12px;padding:16px 8px">
            <div style="font-size:32px;font-weight:800;color:#16a34a">{len(pushed)}</div>
            <div style="font-size:10px;color:#16a34a;text-transform:uppercase;letter-spacing:1px;margin-top:4px;font-weight:700">Updated</div>
        </div>
    </td>
    <td align="center" width="25%" style="padding:8px">
        <div style="background:#f8fafc;border-radius:12px;padding:16px 8px">
            <div style="font-size:32px;font-weight:800;color:#64748b">{len(skipped)}</div>
            <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-top:4px;font-weight:700">Unchanged</div>
        </div>
    </td>
    <td align="center" width="25%" style="padding:8px">
        <div style="background:{'#fef2f2' if failed else '#f8fafc'};border-radius:12px;padding:16px 8px">
            <div style="font-size:32px;font-weight:800;color:{'#dc2626' if failed else '#94a3b8'}">{len(failed)}</div>
            <div style="font-size:10px;color:{'#dc2626' if failed else '#94a3b8'};text-transform:uppercase;letter-spacing:1px;margin-top:4px;font-weight:700">Errors</div>
        </div>
    </td>
    <td align="center" width="25%" style="padding:8px">
        <div style="background:{_S['accent_light']};border-radius:12px;padding:16px 8px">
            <div style="font-size:32px;font-weight:800;color:{_S['accent']}">{len(results)}</div>
            <div style="font-size:10px;color:{_S['accent']};text-transform:uppercase;letter-spacing:1px;margin-top:4px;font-weight:700">Total</div>
        </div>
    </td>
</tr></table>
</div>

<!-- Pricing parameters -->
<div style="background:#f8fafc;border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:1px solid {_S['border']};padding:20px 32px">
    <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
        <td style="padding:4px 0;font-size:11px;color:{_S['text3']};text-transform:uppercase;letter-spacing:0.5px;font-weight:600" colspan="4">&#9881; Pricing Parameters</td>
    </tr>
    <tr>
        <td style="padding:6px 12px 6px 0;font-size:12px;color:{_S['text2']}">FX Rate</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">{rate} NOK/JPY</td>
        <td style="padding:6px 12px 6px 20px;font-size:12px;color:{_S['text2']}">Shipping</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">&yen;{shipping}</td>
    </tr>
    <tr>
        <td style="padding:6px 12px 6px 0;font-size:12px;color:{_S['text2']}">Margin</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">{margin}%</td>
        <td style="padding:6px 12px 6px 20px;font-size:12px;color:{_S['text2']}">Pack Markup</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">{pack_markup}%</td>
    </tr>
    <tr>
        <td style="padding:6px 12px 6px 0;font-size:12px;color:{_S['text2']}">VAT</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">25%</td>
        <td style="padding:6px 12px 6px 20px;font-size:12px;color:{_S['text2']}">Min Change</td>
        <td style="padding:6px 0;font-size:12px;font-weight:700;color:{_S['text']}">Box: kr 25 / Pack: kr 10</td>
    </tr>
    </table>
</div>"""

    # ── Price changes table ──
    if pushed:
        html += f"""
<div style="background:{_S['card']};border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:1px solid {_S['border']};padding:20px 24px 8px">
    <h3 style="margin:0 0 16px;font-size:15px;color:{_S['text']};font-weight:700">&#9989; Price Changes Pushed</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    <thead><tr style="background:#f8fafc">
        <th style="{_TH}" colspan="2">Product</th>
        <th style="{_TH};text-align:right">SNKRDUNK</th>
        <th style="{_TH};text-align:right">Old</th>
        <th style="{_TH};text-align:right">New</th>
        <th style="{_TH};text-align:right">Delta</th>
    </tr></thead><tbody>"""

        for r in pushed:
            product = r.get("product", "Unknown")
            jpy = r.get("jpy", 0)
            img = r.get("image_url", "")
            img_cell = f'<td style="{_TD};width:36px;padding-right:0"><img src="{img}" width="32" height="32" style="border-radius:6px;object-fit:cover;display:block" /></td>' if img else f'<td style="{_TD};width:36px;padding-right:0"><div style="width:32px;height:32px;border-radius:6px;background:#f0f2f5"></div></td>'

            if "box_old" in r and "box_new" in r:
                delta = r["box_new"] - r["box_old"]
                sign = "+" if delta > 0 else ""
                color = _delta_color(delta)
                html += f"""<tr>
                    {img_cell}
                    <td style="{_TD};font-weight:600">{product}<br><span style="font-weight:400;font-size:11px;color:{_S['text3']}">Booster Box</span></td>
                    <td style="{_TD};text-align:right;font-family:monospace;font-size:12px">&yen;{jpy:,}</td>
                    <td style="{_TD};text-align:right;color:{_S['text3']};text-decoration:line-through">{_format_nok(r['box_old'])}</td>
                    <td style="{_TD};text-align:right;font-weight:700">{_format_nok(r['box_new'])}</td>
                    <td style="{_TD};text-align:right;font-weight:700;color:{color}">{sign}{_format_nok(delta)}</td>
                </tr>"""

            if "pack_old" in r and "pack_new" in r:
                delta = r["pack_new"] - r["pack_old"]
                sign = "+" if delta > 0 else ""
                color = _delta_color(delta)
                packs = r.get("packs_per_box", "?")
                html += f"""<tr>
                    {img_cell}
                    <td style="{_TD};font-weight:600">{product}<br><span style="font-weight:400;font-size:11px;color:{_S['text3']}">Pack ({packs}/box)</span></td>
                    <td style="{_TD};text-align:right;font-family:monospace;font-size:12px">&yen;{jpy:,}</td>
                    <td style="{_TD};text-align:right;color:{_S['text3']};text-decoration:line-through">{_format_nok(r['pack_old'])}</td>
                    <td style="{_TD};text-align:right;font-weight:700">{_format_nok(r['pack_new'])}</td>
                    <td style="{_TD};text-align:right;font-weight:700;color:{color}">{sign}{_format_nok(delta)}</td>
                </tr>"""

        html += "</tbody></table></div>"

    # ── No changes ──
    if not pushed and not failed:
        html += f"""
<div style="background:{_S['card']};border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:1px solid {_S['border']};padding:40px 32px;text-align:center">
    <div style="font-size:32px;margin-bottom:8px">&#128077;</div>
    <p style="margin:0;font-size:14px;color:{_S['text2']}">All prices are within threshold. No updates pushed.</p>
</div>"""

    # ── Low stock alerts ──
    if low_stock:
        oos_count = sum(1 for s in low_stock if s["stock"] <= 0)
        low_count = len(low_stock) - oos_count

        html += f"""
<div style="background:#fffbeb;border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:3px solid #f59e0b;padding:20px 24px 8px">
    <h3 style="margin:0 0 4px;font-size:15px;color:#92400e;font-weight:700">&#9888;&#65039; Low Stock Alert</h3>
    <p style="margin:0 0 16px;font-size:12px;color:#a16207">{len(low_stock)} booster box{'es' if len(low_stock) != 1 else ''} at critical stock level{f' ({oos_count} out of stock)' if oos_count else ''}</p>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
    <thead><tr style="background:rgba(245,158,11,0.1)">
        <th style="{_TH};color:#92400e" colspan="2">Product</th>
        <th style="{_TH};color:#92400e;text-align:right">Price</th>
        <th style="{_TH};color:#92400e;text-align:center">Stock</th>
    </tr></thead><tbody>"""

        for item in low_stock:
            qty = item["stock"]
            sc = _stock_color(qty)
            img = item.get("image_url", "")
            img_cell = f'<td style="{_TD};width:36px;padding-right:0;border-bottom-color:#fef3c7"><img src="{img}" width="32" height="32" style="border-radius:6px;object-fit:cover;display:block" /></td>' if img else f'<td style="{_TD};width:36px;padding-right:0;border-bottom-color:#fef3c7"><div style="width:32px;height:32px;border-radius:6px;background:#fef3c7"></div></td>'
            stock_label = "OUT OF STOCK" if qty <= 0 else str(qty)
            badge_bg = "#fef2f2" if qty <= 0 else "#fff7ed"

            html += f"""<tr>
                {img_cell}
                <td style="{_TD};font-weight:600;border-bottom-color:#fef3c7">{item['title']}<br><span style="font-weight:400;font-size:11px;color:#a16207">{item['variant']}</span></td>
                <td style="{_TD};text-align:right;border-bottom-color:#fef3c7">{_format_nok(item['price'])}</td>
                <td style="{_TD};text-align:center;border-bottom-color:#fef3c7">
                    <span style="display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:700;color:{sc};background:{badge_bg}">{stock_label}</span>
                </td>
            </tr>"""

        html += "</tbody></table></div>"

    # ── Skipped (collapsible) ──
    if skipped:
        skipped_summary = ""
        for r in skipped:
            product = r.get("product", "Unknown")
            box_skip = r.get("box_skip", "")
            pack_skip = r.get("pack_skip", "")
            reason = "; ".join(filter(None, [
                f"Box: {box_skip}" if box_skip else "",
                f"Pack: {pack_skip}" if pack_skip else "",
            ])) or "No mapped variants"
            skipped_summary += f'<tr><td style="padding:5px 12px;font-size:12px;color:{_S["text3"]};border-bottom:1px solid #f8fafc">{product}</td><td style="padding:5px 12px;font-size:11px;color:#b4b9c3;border-bottom:1px solid #f8fafc">{reason}</td></tr>'

        html += f"""
<div style="background:{_S['card']};border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:1px solid {_S['border']};padding:16px 24px">
    <details>
        <summary style="cursor:pointer;font-size:13px;color:{_S['text3']};font-weight:600">&#128196; {len(skipped)} products unchanged (within threshold)</summary>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:10px">
            {skipped_summary}
        </table>
    </details>
</div>"""

    # ── Errors ──
    if errors:
        error_rows = ""
        for e in errors:
            product = e.get("product", "Unknown")
            err = e.get("errors") or e.get("error", "Unknown error")
            error_rows += f'<tr><td style="padding:8px 12px;font-size:12px;color:#991b1b;border-bottom:1px solid #fecaca;font-weight:600">{product}</td><td style="padding:8px 12px;font-size:12px;color:#991b1b;border-bottom:1px solid #fecaca">{err}</td></tr>'

        html += f"""
<div style="background:#fef2f2;border-left:1px solid {_S['border']};border-right:1px solid {_S['border']};border-top:2px solid #dc2626;padding:20px 24px 8px">
    <h3 style="margin:0 0 12px;font-size:14px;color:#991b1b;font-weight:700">&#10060; Errors</h3>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{error_rows}</table>
</div>"""

    # ── Footer ──
    html += f"""
<div style="background:#f8fafc;border-radius:0 0 16px 16px;border:1px solid {_S['border']};border-top:none;padding:20px 32px;text-align:center">
    <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:{_S['text2']}">Pokelageret</p>
    <p style="margin:0;font-size:11px;color:{_S['text3']}">
        Price &amp; Stock Monitor &bull; Automated report &bull; {now}
    </p>
</div>

</div></body></html>"""

    return html


def send_price_update_email(
    db,
    results: List[Dict[str, Any]],
    settings_summary: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> Optional[str]:
    """Send a price update report email via Resend.

    Returns the email ID on success, or None if sending is disabled/fails.
    Never raises — logs errors instead so the caller flow isn't interrupted.
    """
    try:
        cfg = _get_email_settings(db)

        if cfg.get("email_notifications_enabled") != "true":
            print("[EMAIL] Notifications disabled, skipping.")
            return None

        api_key = cfg.get("resend_api_key")
        to_email = cfg.get("notification_email")
        from_email = cfg.get("notification_from_email") or "onboarding@resend.dev"

        if not api_key or not to_email:
            print("[EMAIL] Missing API key or recipient email, skipping.")
            return None

        resend.api_key = api_key

        # Enrich results with product images
        _enrich_with_images(db, results)

        # Get low stock booster boxes
        low_stock = _get_low_stock_products(db)

        pushed_count = sum(1 for r in results if r.get("pushed"))
        low_count = len(low_stock)

        subject_parts = []
        if pushed_count:
            subject_parts.append(f"{pushed_count} price{'s' if pushed_count != 1 else ''} updated")
        else:
            subject_parts.append("No price changes")
        if low_count:
            subject_parts.append(f"{low_count} low stock")

        subject = f"Pokelageret: {' | '.join(subject_parts)}"

        html = _build_price_update_html(results, settings_summary, errors, low_stock)

        r = resend.Emails.send({
            "from": from_email,
            "to": to_email,
            "subject": subject,
            "html": html,
        })

        email_id = r.get("id") if isinstance(r, dict) else str(r)
        print(f"[EMAIL] Price update email sent: {email_id}")
        return email_id

    except Exception as e:
        print(f"[EMAIL] Failed to send email: {e}")
        import traceback
        traceback.print_exc()
        return None


def _enrich_with_images(db, results: List[Dict[str, Any]]):
    """Add image_url from Product table into each result dict."""
    from app.models import Product

    # Collect all shopify IDs referenced
    shopify_ids = set()
    for r in results:
        sid = r.get("product_shopify_id")
        if sid:
            shopify_ids.add(sid)

    if not shopify_ids:
        return

    products = db.query(Product).filter(Product.shopify_id.in_(shopify_ids)).all()
    img_map = {p.shopify_id: p.image_url for p in products if p.image_url}

    for r in results:
        sid = r.get("product_shopify_id")
        if sid and sid in img_map:
            r["image_url"] = img_map[sid]


def send_test_email(db) -> dict:
    """Send a test email to verify Resend configuration.

    Returns a dict with success status and message.
    """
    cfg = _get_email_settings(db)

    api_key = cfg.get("resend_api_key")
    to_email = cfg.get("notification_email")
    from_email = cfg.get("notification_from_email") or "onboarding@resend.dev"

    if not api_key:
        return {"success": False, "message": "Resend API key not configured"}
    if not to_email:
        return {"success": False, "message": "Notification email not configured"}

    resend.api_key = api_key

    now = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%d.%m.%Y kl. %H:%M")
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
<div style="max-width:500px;margin:40px auto">
    <div style="background:linear-gradient(135deg,#312e81 0%,#4f46e5 50%,#6366f1 100%);border-radius:16px 16px 0 0;padding:32px;text-align:center">
        <div style="font-size:48px;margin-bottom:12px">&#9989;</div>
        <h2 style="margin:0;font-size:22px;font-weight:800;color:#ffffff">Email Connected!</h2>
    </div>
    <div style="background:#ffffff;padding:28px 32px;border-left:1px solid #e2e5ea;border-right:1px solid #e2e5ea">
        <p style="margin:0 0 20px;color:#5f6672;font-size:14px;text-align:center;line-height:1.6">
            Your Resend integration is working. You'll receive price update reports with stock alerts after every SNKRDUNK auto-update.
        </p>
        <div style="background:#f8fafc;border-radius:10px;padding:16px 20px;font-size:13px;color:#5f6672">
            <table width="100%" cellpadding="0" cellspacing="0">
                <tr><td style="padding:4px 0;font-weight:600;color:#1a1d23">From</td><td style="padding:4px 0;text-align:right">{from_email}</td></tr>
                <tr><td style="padding:4px 0;font-weight:600;color:#1a1d23">To</td><td style="padding:4px 0;text-align:right">{to_email}</td></tr>
                <tr><td style="padding:4px 0;font-weight:600;color:#1a1d23">Time</td><td style="padding:4px 0;text-align:right">{now}</td></tr>
            </table>
        </div>
    </div>
    <div style="background:#f8fafc;border-radius:0 0 16px 16px;border:1px solid #e2e5ea;border-top:none;padding:16px;text-align:center">
        <p style="margin:0;font-size:11px;color:#8b919d">Pokelageret Price &amp; Stock Monitor</p>
    </div>
</div>
</body></html>"""

    try:
        r = resend.Emails.send({
            "from": from_email,
            "to": to_email,
            "subject": "Pokelageret — Test Email",
            "html": html,
        })
        email_id = r.get("id") if isinstance(r, dict) else str(r)
        return {"success": True, "message": f"Test email sent (ID: {email_id})"}
    except Exception as e:
        return {"success": False, "message": f"Failed to send: {e}"}
