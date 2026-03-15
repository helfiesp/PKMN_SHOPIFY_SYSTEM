"""Receipt service — fetches Shopify orders and generates receipt HTML."""
import requests
from datetime import datetime
from typing import Optional
from app.config import settings


class ReceiptService:
    """Service for fetching orders and generating receipts."""

    COMPANY = {
        "name": "Pokelageret AS",
        "org_nr": "934 641 434",
        "address": "H. Halvorsens vei 5",
        "zip": "1734",
        "city": "Hafslundsøy",
        "country": "Norge",
        "email": "kontakt@pokelageret.no",
        "website": "pokelageret.no",
    }

    def __init__(self):
        self.api_version = settings.shopify_api_version

    def _get_credentials(self):
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        return shop, token

    def _graphql_request(self, query: str, variables: dict = None) -> dict:
        shop, token = self._get_credentials()
        if not shop or not token:
            raise Exception("Shopify credentials not configured.")
        if not shop.lower().endswith(".myshopify.com"):
            raise Exception(f"shopify_shop must be a .myshopify.com domain, not '{shop}'.")

        url = f"https://{shop}/admin/api/{self.api_version}/graphql.json"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            url,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=60,
            allow_redirects=False,
        )
        resp.raise_for_status()
        data = resp.json()
        if "errors" in data and "data" not in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def fetch_orders(self, limit: int = 50, cursor: Optional[str] = None, query_filter: Optional[str] = None) -> dict:
        """Fetch orders from Shopify."""
        gql = """
        query($first: Int!, $after: String, $query: String) {
          orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: true) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id
                name
                email
                createdAt
                displayFinancialStatus
                displayFulfillmentStatus
                totalPriceSet { shopMoney { amount currencyCode } }
                subtotalPriceSet { shopMoney { amount currencyCode } }
                totalTaxSet { shopMoney { amount currencyCode } }
                totalShippingPriceSet { shopMoney { amount currencyCode } }
                totalDiscountsSet { shopMoney { amount currencyCode } }
                billingAddress {
                  firstName
                  lastName
                  phone
                  address1
                  address2
                  city
                  zip
                  province
                  country
                  company
                }
                shippingAddress {
                  firstName
                  lastName
                  phone
                  address1
                  address2
                  city
                  zip
                  province
                  country
                  company
                }
                lineItems(first: 100) {
                  edges {
                    node {
                      title
                      variantTitle
                      quantity
                      originalUnitPriceSet { shopMoney { amount currencyCode } }
                      discountedUnitPriceSet { shopMoney { amount currencyCode } }
                      totalDiscountSet { shopMoney { amount currencyCode } }
                      taxLines {
                        title
                        rate
                        priceSet { shopMoney { amount currencyCode } }
                      }
                      sku
                    }
                  }
                }
                taxLines {
                  title
                  rate
                  priceSet { shopMoney { amount currencyCode } }
                }
              }
            }
          }
        }
        """
        variables = {"first": limit}
        if cursor:
            variables["after"] = cursor
        if query_filter:
            # Shopify order search: if it looks like an order number (#1234 or 1234),
            # search by name. Otherwise treat as free-text which searches across
            # customer name, email, and order fields.
            q = query_filter.strip()
            if q.startswith("#"):
                variables["query"] = f"name:{q}"
            elif q.isdigit():
                variables["query"] = f"name:#{q}"
            else:
                variables["query"] = q

        result = self._graphql_request(gql, variables)
        orders_data = result.get("orders", {})
        page_info = orders_data.get("pageInfo", {})

        orders = []
        for edge in orders_data.get("edges", []):
            node = edge["node"]
            orders.append(self._normalize_order(node))

        return {
            "orders": orders,
            "has_next_page": page_info.get("hasNextPage", False),
            "end_cursor": page_info.get("endCursor"),
        }

    def fetch_order_by_id(self, order_id: str) -> dict:
        """Fetch a single order by its Shopify GID."""
        gql = """
        query($id: ID!) {
          order(id: $id) {
            id
            name
            email
            createdAt
            displayFinancialStatus
            displayFulfillmentStatus
            totalPriceSet { shopMoney { amount currencyCode } }
            subtotalPriceSet { shopMoney { amount currencyCode } }
            totalTaxSet { shopMoney { amount currencyCode } }
            totalShippingPriceSet { shopMoney { amount currencyCode } }
            totalDiscountsSet { shopMoney { amount currencyCode } }
            billingAddress {
              firstName
              lastName
              phone
              address1
              address2
              city
              zip
              province
              country
              company
            }
            shippingAddress {
              firstName
              lastName
              phone
              address1
              address2
              city
              zip
              province
              country
              company
            }
            lineItems(first: 100) {
              edges {
                node {
                  title
                  variantTitle
                  quantity
                  originalUnitPriceSet { shopMoney { amount currencyCode } }
                  discountedUnitPriceSet { shopMoney { amount currencyCode } }
                  totalDiscountSet { shopMoney { amount currencyCode } }
                  taxLines {
                    title
                    rate
                    priceSet { shopMoney { amount currencyCode } }
                  }
                  sku
                }
              }
            }
            taxLines {
              title
              rate
              priceSet { shopMoney { amount currencyCode } }
            }
          }
        }
        """
        result = self._graphql_request(gql, {"id": order_id})
        order = result.get("order")
        if not order:
            raise Exception(f"Order not found: {order_id}")
        return self._normalize_order(order)

    def _normalize_order(self, node: dict) -> dict:
        """Normalize a GraphQL order node into a clean dict."""
        def money(field):
            s = node.get(field) or {}
            m = s.get("shopMoney") or {}
            return {"amount": m.get("amount", "0.00"), "currency": m.get("currencyCode", "NOK")}

        # Use billingAddress for receipt (fallback to shippingAddress)
        addr = node.get("billingAddress") or node.get("shippingAddress") or {}

        line_items = []
        for edge in (node.get("lineItems") or {}).get("edges", []):
            li = edge["node"]
            unit_price_data = li.get("discountedUnitPriceSet") or li.get("originalUnitPriceSet") or {}
            unit_price = (unit_price_data.get("shopMoney") or {}).get("amount", "0.00")
            orig_price_data = li.get("originalUnitPriceSet") or {}
            orig_price = (orig_price_data.get("shopMoney") or {}).get("amount", "0.00")
            discount_data = li.get("totalDiscountSet") or {}
            discount = (discount_data.get("shopMoney") or {}).get("amount", "0.00")

            tax_lines = []
            for tl in li.get("taxLines") or []:
                tp = (tl.get("priceSet") or {}).get("shopMoney") or {}
                tax_lines.append({
                    "title": tl.get("title", "MVA"),
                    "rate": tl.get("rate", 0.25),
                    "amount": tp.get("amount", "0.00"),
                })

            line_items.append({
                "title": li.get("title", ""),
                "variant_title": li.get("variantTitle", ""),
                "quantity": li.get("quantity", 1),
                "unit_price": unit_price,
                "original_unit_price": orig_price,
                "discount": discount,
                "sku": li.get("sku", ""),
                "tax_lines": tax_lines,
            })

        order_tax_lines = []
        for tl in node.get("taxLines") or []:
            tp = (tl.get("priceSet") or {}).get("shopMoney") or {}
            order_tax_lines.append({
                "title": tl.get("title", "MVA"),
                "rate": tl.get("rate", 0.25),
                "amount": tp.get("amount", "0.00"),
            })

        return {
            "id": node["id"],
            "name": node.get("name", ""),
            "created_at": node.get("createdAt", ""),
            "financial_status": node.get("displayFinancialStatus", ""),
            "fulfillment_status": node.get("displayFulfillmentStatus", ""),
            "total": money("totalPriceSet"),
            "subtotal": money("subtotalPriceSet"),
            "total_tax": money("totalTaxSet"),
            "total_shipping": money("totalShippingPriceSet"),
            "total_discounts": money("totalDiscountsSet"),
            "customer": {
                "first_name": addr.get("firstName", ""),
                "last_name": addr.get("lastName", ""),
                "email": node.get("email", ""),
                "phone": addr.get("phone", ""),
                "company": addr.get("company", ""),
                "address1": addr.get("address1", ""),
                "address2": addr.get("address2", ""),
                "city": addr.get("city", ""),
                "zip": addr.get("zip", ""),
                "province": addr.get("province", ""),
                "country": addr.get("country", ""),
            },
            "line_items": line_items,
            "tax_lines": order_tax_lines,
        }

    def generate_receipt_html(self, order: dict) -> str:
        """Generate a printable receipt HTML page for an order."""
        company = self.COMPANY
        customer = order["customer"]
        created = order["created_at"]
        try:
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            date_str = dt.strftime("%d.%m.%Y")
        except Exception:
            date_str = created[:10] if len(created) >= 10 else created

        # Build line items rows
        rows_html = ""
        for i, li in enumerate(order["line_items"]):
            name = li["title"]
            if li["variant_title"]:
                name += f' — {li["variant_title"]}'
            qty = li["quantity"]
            unit = float(li["unit_price"])
            line_total = qty * unit
            vat_rate = 0.25
            if li["tax_lines"]:
                vat_rate = float(li["tax_lines"][0].get("rate", 0.25))
            unit_ex_vat = unit / (1 + vat_rate)
            line_ex_vat = qty * unit_ex_vat
            line_vat = line_total - line_ex_vat
            bg = "#f9fafb" if i % 2 == 0 else "#ffffff"

            rows_html += f"""
            <tr style="background:{bg}">
                <td class="td-prod">{_esc(name)}{f'<span class="sku-inline">{_esc(li["sku"])}</span>' if li['sku'] else ''}</td>
                <td class="td-num">{qty}</td>
                <td class="td-num">{_fmt_nok(unit)}</td>
                <td class="td-num">{int(vat_rate * 100)} %</td>
                <td class="td-num td-bold">{_fmt_nok(line_total)}</td>
            </tr>"""

        subtotal = float(order["subtotal"]["amount"])
        total_tax = float(order["total_tax"]["amount"])
        total_shipping = float(order["total_shipping"]["amount"])
        total_discounts = float(order["total_discounts"]["amount"])
        total = float(order["total"]["amount"])

        total_ex_vat = total / 1.25
        calculated_vat = total - total_ex_vat

        # Customer address block
        cust_lines = []
        if customer.get("company"):
            cust_lines.append(f'<strong>{_esc(customer["company"])}</strong>')
        name_parts = [customer.get("first_name", ""), customer.get("last_name", "")]
        cust_name = " ".join(p for p in name_parts if p)
        if cust_name:
            cust_lines.append(_esc(cust_name))
        if customer.get("address1"):
            cust_lines.append(_esc(customer["address1"]))
        if customer.get("address2"):
            cust_lines.append(_esc(customer["address2"]))
        zip_city = " ".join(p for p in [customer.get("zip", ""), customer.get("city", "")] if p)
        if zip_city:
            cust_lines.append(_esc(zip_city))
        if customer.get("country"):
            cust_lines.append(_esc(customer["country"]))
        if customer.get("email"):
            cust_lines.append(f'<span style="color:#6366f1">{_esc(customer["email"])}</span>')
        if customer.get("phone"):
            cust_lines.append(_esc(customer["phone"]))

        cust_html = "<br>".join(cust_lines) if cust_lines else "<em>Ingen kundeinformasjon</em>"

        # Summary rows
        summary_rows = f"""
        <tr>
          <td class="sum-label">Subtotal ekskl. MVA</td>
          <td class="sum-val">{_fmt_nok(total_ex_vat)}</td>
        </tr>
        <tr>
          <td class="sum-label">MVA (25 %)</td>
          <td class="sum-val">{_fmt_nok(calculated_vat)}</td>
        </tr>"""

        if total_discounts > 0:
            summary_rows += f"""
        <tr>
          <td class="sum-label">Rabatt</td>
          <td class="sum-val" style="color:#dc2626">-{_fmt_nok(total_discounts)}</td>
        </tr>"""

        if total_shipping > 0:
            summary_rows += f"""
        <tr>
          <td class="sum-label">Frakt</td>
          <td class="sum-val">{_fmt_nok(total_shipping)}</td>
        </tr>"""

        return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kvittering {_esc(order['name'])} — Pokelageret</title>
<style>
  @media print {{
    html, body {{ background: #fff; }}
    .no-print {{ display: none !important; }}
    .receipt {{ box-shadow: none; margin: 0; border-radius: 0; }}
    @page {{ size: A4; margin: 12mm 14mm; }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    color: #1e293b;
    background: #eef2f7;
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
  }}
  .no-print {{ max-width: 820px; margin: 16px auto 10px; display: flex; justify-content: flex-end; gap: 8px; padding: 0 10px; }}
  .btn-action {{
    padding: 9px 22px; border: none; border-radius: 8px; font-size: 13px;
    font-weight: 600; cursor: pointer; transition: background .15s;
  }}
  .btn-print {{ background: #1e293b; color: #fff; }}
  .btn-print:hover {{ background: #334155; }}

  .receipt {{
    max-width: 820px; margin: 0 auto 40px; background: #fff;
    border-radius: 16px; box-shadow: 0 4px 24px rgba(0,0,0,.08);
    overflow: hidden;
  }}

  /* ── Header ── */
  .r-header {{
    padding: 36px 44px 32px;
    display: flex; justify-content: space-between; align-items: flex-start;
    border-bottom: 3px solid #f1f5f9;
  }}
  .r-header-left {{ display: flex; align-items: center; gap: 16px; }}
  .r-logo {{ height: 56px; width: auto; }}
  .r-header-right {{ text-align: right; }}
  .r-doc-type {{
    font-size: 28px; font-weight: 300; color: #94a3b8;
    text-transform: uppercase; letter-spacing: 4px;
  }}
  .r-order-no {{
    font-size: 22px; font-weight: 700; color: #1e293b; margin-top: 2px;
  }}
  .r-date {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}

  /* ── Info blocks ── */
  .r-info {{
    display: grid; grid-template-columns: 1fr 1fr;
    gap: 0; border-bottom: 3px solid #f1f5f9;
  }}
  .r-info-block {{
    padding: 28px 44px;
  }}
  .r-info-block:first-child {{ border-right: 1px solid #f1f5f9; }}
  .r-info-label {{
    font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px;
    color: #94a3b8; font-weight: 700; margin-bottom: 10px;
  }}
  .r-info-body {{ font-size: 13.5px; color: #475569; line-height: 1.7; }}
  .r-info-body strong {{ color: #1e293b; font-weight: 600; }}

  /* ── Table ── */
  .r-table-wrap {{ padding: 0 44px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  thead th {{
    padding: 14px 16px; font-size: 10px; text-transform: uppercase;
    letter-spacing: 1px; color: #94a3b8; font-weight: 700;
    border-bottom: 2px solid #e2e8f0; white-space: nowrap;
  }}
  .td-prod {{ padding: 14px 16px; text-align: left; color: #1e293b; font-weight: 500; }}
  .td-num  {{ padding: 14px 16px; text-align: right; color: #475569; white-space: nowrap; font-variant-numeric: tabular-nums; }}
  .td-bold {{ font-weight: 700; color: #1e293b; }}
  .sku-inline {{
    display: block; font-size: 11px; color: #94a3b8; font-weight: 400; margin-top: 1px;
  }}
  tbody tr {{ border-bottom: 1px solid #f1f5f9; }}
  tbody tr:last-child {{ border-bottom: none; }}

  /* ── Summary ── */
  .r-summary {{
    padding: 24px 44px 32px;
    display: flex; justify-content: flex-end;
  }}
  .r-summary table {{ width: 340px; }}
  .sum-label {{ padding: 7px 0; font-size: 13.5px; color: #64748b; }}
  .sum-val {{ padding: 7px 0; text-align: right; font-size: 13.5px; color: #334155; font-variant-numeric: tabular-nums; }}
  .sum-divider td {{ padding: 0; height: 1px; }}
  .sum-divider td div {{ height: 2px; background: #1e293b; margin: 8px 0; }}
  .sum-total td {{
    padding-top: 10px; font-size: 20px; font-weight: 800; color: #1e293b;
  }}
  .sum-total .sum-val {{ font-size: 20px; }}

  /* ── Badge ── */
  .r-badge {{
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .5px;
  }}
  .r-badge-paid {{ background: #dcfce7; color: #15803d; }}
  .r-badge-pending {{ background: #fef3c7; color: #92400e; }}
  .r-badge-refund {{ background: #fee2e2; color: #b91c1c; }}

  /* ── Footer ── */
  .r-footer {{
    background: #f8fafc; border-top: 1px solid #e2e8f0;
    padding: 20px 44px; text-align: center;
    font-size: 11.5px; color: #94a3b8; line-height: 1.8;
  }}
  .r-footer strong {{ color: #64748b; }}
</style>
</head>
<body>

<div class="no-print">
  <button class="btn-action btn-print" onclick="window.print()">Skriv ut / Lagre som PDF</button>
</div>

<div class="receipt">

  <!-- Header -->
  <div class="r-header">
    <div class="r-header-left">
      <img src="/static/pokelageret_logo.png" alt="Pokelageret" class="r-logo">
    </div>
    <div class="r-header-right">
      <div class="r-doc-type">Kvittering</div>
      <div class="r-order-no">{_esc(order['name'])}</div>
      <div class="r-date">{date_str} &nbsp;&middot;&nbsp;
        <span class="r-badge {_status_badge_class(order['financial_status'])}">{_esc(_translate_status(order['financial_status']))}</span>
      </div>
    </div>
  </div>

  <!-- Seller / Buyer -->
  <div class="r-info">
    <div class="r-info-block">
      <div class="r-info-label">Selger</div>
      <div class="r-info-body">
        <strong>{_esc(company['name'])}</strong><br>
        Org.nr {_esc(company['org_nr'])}<br>
        {_esc(company['address'])}<br>
        {_esc(company['zip'])} {_esc(company['city'])}<br>
        {_esc(company['country'])}
      </div>
    </div>
    <div class="r-info-block">
      <div class="r-info-label">Kjøper</div>
      <div class="r-info-body">{cust_html}</div>
    </div>
  </div>

  <!-- Line items -->
  <div class="r-table-wrap">
    <table>
      <thead>
        <tr>
          <th style="text-align:left">Produkt</th>
          <th style="text-align:right">Antall</th>
          <th style="text-align:right">Enhetspris</th>
          <th style="text-align:right">MVA</th>
          <th style="text-align:right">Sum</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>
  </div>

  <!-- Totals -->
  <div class="r-summary">
    <table>
      <tbody>
        {summary_rows}
        <tr class="sum-divider"><td colspan="2"><div></div></td></tr>
        <tr class="sum-total">
          <td>Totalt inkl. MVA</td>
          <td class="sum-val">{_fmt_nok(total)}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- Footer -->
  <div class="r-footer">
    <strong>{_esc(company['name'])}</strong> &middot; Org.nr {_esc(company['org_nr'])} &middot;
    {_esc(company['address'])}, {_esc(company['zip'])} {_esc(company['city'])} &middot;
    {_esc(company['website'])}<br>
    Kvittering generert {datetime.now().strftime('%d.%m.%Y kl. %H:%M')}
  </div>
</div>

</body>
</html>"""


def _esc(text: str) -> str:
    """HTML-escape a string."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt_nok(amount) -> str:
    """Format a number as NOK currency string."""
    val = float(amount)
    formatted = f"{val:,.2f}".replace(",", " ").replace(".", ",")
    return f"kr {formatted}"


def _translate_status(status: str) -> str:
    """Translate Shopify financial status to Norwegian."""
    translations = {
        "PAID": "Betalt",
        "PENDING": "Venter",
        "AUTHORIZED": "Autorisert",
        "PARTIALLY_PAID": "Delvis betalt",
        "PARTIALLY_REFUNDED": "Delvis refundert",
        "REFUNDED": "Refundert",
        "VOIDED": "Annullert",
        "EXPIRED": "Utløpt",
    }
    return translations.get(status.upper() if status else "", status or "Ukjent")


def _status_badge_class(status: str) -> str:
    """Return CSS class for payment status badge."""
    s = (status or "").upper()
    if s == "PAID":
        return "r-badge-paid"
    if s in ("REFUNDED", "PARTIALLY_REFUNDED", "VOIDED"):
        return "r-badge-refund"
    return "r-badge-pending"


receipt_service = ReceiptService()
