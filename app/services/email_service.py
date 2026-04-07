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
            return "#dc2626"  # red = price went up
        if d < 0:
            return "#16a34a"  # green = price went down
    except (ValueError, TypeError):
        pass
    return "#6b7280"


def _build_price_update_html(
    results: List[Dict[str, Any]],
    settings_summary: Dict[str, Any],
    errors: List[Dict[str, Any]],
) -> str:
    """Build a well-formatted HTML email for the SNKRDUNK price update report."""
    now = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%d.%m.%Y %H:%M")

    pushed = [r for r in results if r.get("pushed")]
    skipped = [r for r in results if not r.get("pushed") and not r.get("shopify_error")]
    failed = [r for r in results if r.get("shopify_error")]

    # Settings summary
    rate = settings_summary.get("rate", "?")
    shipping = settings_summary.get("shipping_jpy", "?")
    margin = settings_summary.get("margin_pct", "?")
    pack_markup = settings_summary.get("pack_markup_pct", "?")

    # Build pushed rows
    pushed_rows = ""
    for r in pushed:
        product = r.get("product", "Unknown")
        jpy = r.get("jpy", 0)

        # Box change
        if "box_old" in r and "box_new" in r:
            delta = r["box_new"] - r["box_old"]
            sign = "+" if delta > 0 else ""
            color = _delta_color(delta)
            pushed_rows += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">{product}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">Box</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right">{_format_nok(jpy)} JPY</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right">{_format_nok(r['box_old'])}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;font-weight:600">{_format_nok(r['box_new'])}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;color:{color};font-weight:600">{sign}{_format_nok(delta)}</td>
            </tr>"""

        # Pack change
        if "pack_old" in r and "pack_new" in r:
            delta = r["pack_new"] - r["pack_old"]
            sign = "+" if delta > 0 else ""
            color = _delta_color(delta)
            packs = r.get("packs_per_box", "?")
            pushed_rows += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">{product}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px">Pack ({packs}/box)</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right">{_format_nok(jpy)} JPY</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right">{_format_nok(r['pack_old'])}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;font-weight:600">{_format_nok(r['pack_new'])}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:13px;text-align:right;color:{color};font-weight:600">{sign}{_format_nok(delta)}</td>
            </tr>"""

    # Skipped rows
    skipped_rows = ""
    for r in skipped:
        product = r.get("product", "Unknown")
        box_skip = r.get("box_skip", "")
        pack_skip = r.get("pack_skip", "")
        reason = "; ".join(filter(None, [
            f"Box: {box_skip}" if box_skip else "",
            f"Pack: {pack_skip}" if pack_skip else "",
        ])) or "No mapped variants"
        skipped_rows += f"""
        <tr>
            <td style="padding:6px 12px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#6b7280">{product}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #f3f4f6;font-size:12px;color:#9ca3af">{reason}</td>
        </tr>"""

    # Error rows
    error_rows = ""
    for e in errors:
        product = e.get("product", "Unknown")
        err = e.get("errors") or e.get("error", "Unknown error")
        error_rows += f"""
        <tr>
            <td style="padding:6px 12px;border-bottom:1px solid #fecaca;font-size:12px;color:#991b1b">{product}</td>
            <td style="padding:6px 12px;border-bottom:1px solid #fecaca;font-size:12px;color:#991b1b">{err}</td>
        </tr>"""

    # Assemble
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
    <div style="max-width:680px;margin:0 auto;padding:24px 16px">

        <!-- Header -->
        <div style="background:linear-gradient(135deg,#1e293b 0%,#334155 100%);border-radius:12px 12px 0 0;padding:28px 32px;color:white">
            <h1 style="margin:0;font-size:22px;font-weight:700">SNKRDUNK Price Update</h1>
            <p style="margin:6px 0 0;font-size:13px;opacity:0.8">Pokelageret &mdash; {now}</p>
        </div>

        <!-- Stats bar -->
        <div style="background:#ffffff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:20px 32px;display:flex;gap:24px;flex-wrap:wrap">
            <div style="text-align:center;min-width:80px">
                <div style="font-size:28px;font-weight:700;color:#1e293b">{len(pushed)}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Updated</div>
            </div>
            <div style="text-align:center;min-width:80px">
                <div style="font-size:28px;font-weight:700;color:#6b7280">{len(skipped)}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Skipped</div>
            </div>
            <div style="text-align:center;min-width:80px">
                <div style="font-size:28px;font-weight:700;color:{'#dc2626' if failed else '#6b7280'}">{len(failed)}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Errors</div>
            </div>
            <div style="text-align:center;min-width:80px">
                <div style="font-size:28px;font-weight:700;color:#1e293b">{len(results)}</div>
                <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.5px">Total</div>
            </div>
        </div>

        <!-- Settings summary -->
        <div style="background:#f8fafc;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:16px 32px;border-top:1px solid #e5e7eb">
            <h3 style="margin:0 0 10px;font-size:13px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px">Pricing Parameters</h3>
            <table style="width:100%" cellpadding="0" cellspacing="0">
                <tr>
                    <td style="padding:3px 16px 3px 0;font-size:12px;color:#64748b">FX Rate</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">{rate} NOK/JPY</td>
                    <td style="padding:3px 16px 3px 24px;font-size:12px;color:#64748b">Shipping</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">{shipping} JPY</td>
                </tr>
                <tr>
                    <td style="padding:3px 16px 3px 0;font-size:12px;color:#64748b">Margin</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">{margin}%</td>
                    <td style="padding:3px 16px 3px 24px;font-size:12px;color:#64748b">Pack Markup</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">{pack_markup}%</td>
                </tr>
                <tr>
                    <td style="padding:3px 16px 3px 0;font-size:12px;color:#64748b">VAT</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">25%</td>
                    <td style="padding:3px 16px 3px 24px;font-size:12px;color:#64748b">Min Change</td>
                    <td style="padding:3px 0;font-size:12px;font-weight:600;color:#1e293b">Box: kr 25 / Pack: kr 10</td>
                </tr>
            </table>
        </div>"""

    # Price changes table
    if pushed_rows:
        html += f"""
        <div style="background:#ffffff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:20px 32px;border-top:1px solid #e5e7eb">
            <h3 style="margin:0 0 12px;font-size:14px;color:#1e293b">Price Changes Pushed to Shopify</h3>
            <table style="width:100%;border-collapse:collapse;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden" cellpadding="0" cellspacing="0">
                <thead>
                    <tr style="background:#f8fafc">
                        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">Product</th>
                        <th style="padding:10px 12px;text-align:left;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">Variant</th>
                        <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">SNKRDUNK</th>
                        <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">Old Price</th>
                        <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">New Price</th>
                        <th style="padding:10px 12px;text-align:right;font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.5px;border-bottom:2px solid #e5e7eb">Delta</th>
                    </tr>
                </thead>
                <tbody>
                    {pushed_rows}
                </tbody>
            </table>
        </div>"""

    # No changes
    if not pushed_rows and not error_rows:
        html += """
        <div style="background:#ffffff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:32px;border-top:1px solid #e5e7eb;text-align:center">
            <p style="margin:0;font-size:14px;color:#6b7280">No price changes were pushed this run. All prices are within threshold.</p>
        </div>"""

    # Skipped section
    if skipped_rows:
        html += f"""
        <div style="background:#ffffff;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:20px 32px;border-top:1px solid #e5e7eb">
            <details>
                <summary style="cursor:pointer;font-size:13px;color:#6b7280;font-weight:600">Skipped ({len(skipped)} products within threshold)</summary>
                <table style="width:100%;border-collapse:collapse;margin-top:8px" cellpadding="0" cellspacing="0">
                    {skipped_rows}
                </table>
            </details>
        </div>"""

    # Errors section
    if error_rows:
        html += f"""
        <div style="background:#fef2f2;border-left:1px solid #e5e7eb;border-right:1px solid #e5e7eb;padding:20px 32px;border-top:1px solid #fecaca">
            <h3 style="margin:0 0 12px;font-size:14px;color:#991b1b">Errors</h3>
            <table style="width:100%;border-collapse:collapse" cellpadding="0" cellspacing="0">
                <tr style="background:#fee2e2">
                    <th style="padding:8px 12px;text-align:left;font-size:11px;color:#991b1b;text-transform:uppercase">Product</th>
                    <th style="padding:8px 12px;text-align:left;font-size:11px;color:#991b1b;text-transform:uppercase">Error</th>
                </tr>
                {error_rows}
            </table>
        </div>"""

    # Footer
    html += f"""
        <div style="background:#f1f5f9;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;border-top:none;padding:16px 32px;text-align:center">
            <p style="margin:0;font-size:11px;color:#94a3b8">
                Pokelageret Price &amp; Stock Monitor &mdash; Automated report generated {now}
            </p>
        </div>

    </div>
    </body>
    </html>"""

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

        pushed_count = sum(1 for r in results if r.get("pushed"))
        subject = f"SNKRDUNK Update: {pushed_count} price{'s' if pushed_count != 1 else ''} pushed to Shopify"

        html = _build_price_update_html(results, settings_summary, errors)

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

    now = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%d.%m.%Y %H:%M")
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#f9fafb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
    <div style="max-width:500px;margin:40px auto;padding:32px;background:white;border-radius:12px;border:1px solid #e5e7eb;text-align:center">
        <div style="font-size:48px;margin-bottom:16px">&#9989;</div>
        <h2 style="margin:0 0 8px;color:#1e293b">Email Connected!</h2>
        <p style="margin:0 0 20px;color:#64748b;font-size:14px">
            Your Resend integration is working. You'll receive price update reports after every SNKRDUNK auto-update.
        </p>
        <div style="background:#f8fafc;border-radius:8px;padding:16px;font-size:13px;color:#64748b">
            <strong>From:</strong> {from_email}<br>
            <strong>To:</strong> {to_email}<br>
            <strong>Time:</strong> {now}
        </div>
        <p style="margin:20px 0 0;font-size:11px;color:#94a3b8">Pokelageret Price &amp; Stock Monitor</p>
    </div>
    </body>
    </html>"""

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
