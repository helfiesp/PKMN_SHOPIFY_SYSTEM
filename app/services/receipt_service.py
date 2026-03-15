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
        "city": "Tønsberg",
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
        if "errors" in data:
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
                createdAt
                displayFinancialStatus
                displayFulfillmentStatus
                totalPriceSet { shopMoney { amount currencyCode } }
                subtotalPriceSet { shopMoney { amount currencyCode } }
                totalTaxSet { shopMoney { amount currencyCode } }
                totalShippingPriceSet { shopMoney { amount currencyCode } }
                totalDiscountsSet { shopMoney { amount currencyCode } }
                customer {
                  firstName
                  lastName
                  email
                  phone
                  defaultAddress {
                    address1
                    address2
                    city
                    zip
                    province
                    country
                    company
                  }
                }
                shippingAddress {
                  address1
                  address2
                  city
                  zip
                  province
                  country
                  company
                  firstName
                  lastName
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
            variables["query"] = query_filter

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
            createdAt
            displayFinancialStatus
            displayFulfillmentStatus
            totalPriceSet { shopMoney { amount currencyCode } }
            subtotalPriceSet { shopMoney { amount currencyCode } }
            totalTaxSet { shopMoney { amount currencyCode } }
            totalShippingPriceSet { shopMoney { amount currencyCode } }
            totalDiscountsSet { shopMoney { amount currencyCode } }
            customer {
              firstName
              lastName
              email
              phone
              defaultAddress {
                address1
                address2
                city
                zip
                province
                country
                company
              }
            }
            shippingAddress {
              address1
              address2
              city
              zip
              province
              country
              company
              firstName
              lastName
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

        customer = node.get("customer") or {}
        addr = node.get("shippingAddress") or customer.get("defaultAddress") or {}

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
                "first_name": customer.get("firstName", ""),
                "last_name": customer.get("lastName", ""),
                "email": customer.get("email", ""),
                "phone": customer.get("phone", ""),
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
        for li in order["line_items"]:
            name = li["title"]
            if li["variant_title"]:
                name += f' — {li["variant_title"]}'
            qty = li["quantity"]
            unit = float(li["unit_price"])
            line_total = qty * unit
            # Calculate ex-VAT (assuming 25% VAT included)
            vat_rate = 0.25
            if li["tax_lines"]:
                vat_rate = float(li["tax_lines"][0].get("rate", 0.25))
            ex_vat = line_total / (1 + vat_rate)
            vat_amount = line_total - ex_vat

            rows_html += f"""
            <tr>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:left">{_esc(name)}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:left;font-size:12px;color:#6b7280">{_esc(li['sku'])}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:center">{qty}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right">{_fmt_nok(unit)}</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right">{int(vat_rate * 100)} %</td>
                <td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;text-align:right;font-weight:600">{_fmt_nok(line_total)}</td>
            </tr>"""

        subtotal = float(order["subtotal"]["amount"])
        total_tax = float(order["total_tax"]["amount"])
        total_shipping = float(order["total_shipping"]["amount"])
        total_discounts = float(order["total_discounts"]["amount"])
        total = float(order["total"]["amount"])

        # Calculate ex-VAT totals
        subtotal_ex_vat = subtotal / 1.25
        shipping_ex_vat = total_shipping / 1.25
        total_ex_vat = total / 1.25
        calculated_vat = total - total_ex_vat

        # Customer address block
        cust_lines = []
        if customer.get("company"):
            cust_lines.append(customer["company"])
        name_parts = [customer.get("first_name", ""), customer.get("last_name", "")]
        cust_name = " ".join(p for p in name_parts if p)
        if cust_name:
            cust_lines.append(cust_name)
        if customer.get("address1"):
            cust_lines.append(customer["address1"])
        if customer.get("address2"):
            cust_lines.append(customer["address2"])
        zip_city = " ".join(p for p in [customer.get("zip", ""), customer.get("city", "")] if p)
        if zip_city:
            cust_lines.append(zip_city)
        if customer.get("email"):
            cust_lines.append(customer["email"])

        cust_html = "<br>".join(_esc(l) for l in cust_lines) if cust_lines else "<em>Ingen kundeinformasjon</em>"

        discount_row = ""
        if total_discounts > 0:
            discount_row = f"""
            <tr>
                <td style="padding:6px 0;color:#6b7280">Rabatt</td>
                <td style="padding:6px 0;text-align:right;color:#dc2626">-{_fmt_nok(total_discounts)}</td>
            </tr>"""

        shipping_row = ""
        if total_shipping > 0:
            shipping_row = f"""
            <tr>
                <td style="padding:6px 0;color:#6b7280">Frakt</td>
                <td style="padding:6px 0;text-align:right">{_fmt_nok(total_shipping)}</td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kvittering — {_esc(order['name'])} — Pokelageret</title>
<style>
  @media print {{
    body {{ margin: 0; }}
    .no-print {{ display: none !important; }}
    @page {{ margin: 20mm 15mm; }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    color: #1f2937;
    background: #f9fafb;
    line-height: 1.5;
  }}
  .receipt-container {{
    max-width: 800px;
    margin: 20px auto;
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 3px rgba(0,0,0,.1);
    overflow: hidden;
  }}
  .receipt-header {{
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
    color: #fff;
    padding: 32px 40px;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
  }}
  .receipt-header .logo-area {{
    display: flex;
    align-items: center;
    gap: 14px;
  }}
  .receipt-header .logo-icon {{
    width: 48px;
    height: 48px;
    background: rgba(255,255,255,.15);
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
  }}
  .receipt-header h1 {{
    font-size: 20px;
    font-weight: 700;
    letter-spacing: -0.3px;
  }}
  .receipt-header .subtitle {{
    font-size: 12px;
    opacity: .7;
    margin-top: 2px;
  }}
  .receipt-header .doc-title {{
    text-align: right;
  }}
  .receipt-header .doc-title h2 {{
    font-size: 26px;
    font-weight: 300;
    text-transform: uppercase;
    letter-spacing: 3px;
  }}
  .receipt-header .doc-title .order-no {{
    font-size: 14px;
    opacity: .8;
    margin-top: 4px;
  }}
  .receipt-body {{
    padding: 32px 40px;
  }}
  .info-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 24px;
    margin-bottom: 32px;
  }}
  .info-block label {{
    display: block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: #9ca3af;
    margin-bottom: 6px;
    font-weight: 600;
  }}
  .info-block p {{
    font-size: 14px;
    color: #374151;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }}
  thead th {{
    background: #f8fafc;
    padding: 10px 12px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .5px;
    color: #6b7280;
    font-weight: 600;
    border-bottom: 2px solid #e5e7eb;
  }}
  .totals-table {{
    width: 320px;
    margin-left: auto;
    margin-top: 24px;
    font-size: 14px;
  }}
  .totals-table td {{
    padding: 6px 0;
  }}
  .totals-table .total-row td {{
    padding-top: 12px;
    border-top: 2px solid #1e293b;
    font-size: 18px;
    font-weight: 700;
  }}
  .receipt-footer {{
    border-top: 1px solid #e5e7eb;
    padding: 24px 40px;
    text-align: center;
    font-size: 12px;
    color: #9ca3af;
  }}
  .receipt-footer strong {{
    color: #6b7280;
  }}
  .print-bar {{
    max-width: 800px;
    margin: 0 auto 12px;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }}
  .print-bar button {{
    padding: 8px 20px;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    cursor: pointer;
    font-weight: 500;
  }}
  .btn-print {{
    background: #1e293b;
    color: #fff;
  }}
  .btn-print:hover {{ background: #334155; }}
</style>
</head>
<body>

<div class="no-print print-bar">
  <button class="btn-print" onclick="window.print()">Skriv ut / Lagre som PDF</button>
</div>

<div class="receipt-container">
  <div class="receipt-header">
    <div class="logo-area">
      <div class="logo-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <circle cx="12" cy="12" r="3"/>
          <line x1="2" y1="12" x2="9" y2="12"/>
          <line x1="15" y1="12" x2="22" y2="12"/>
        </svg>
      </div>
      <div>
        <h1>{_esc(company['name'])}</h1>
        <div class="subtitle">Org.nr {_esc(company['org_nr'])}</div>
      </div>
    </div>
    <div class="doc-title">
      <h2>Kvittering</h2>
      <div class="order-no">{_esc(order['name'])}</div>
    </div>
  </div>

  <div class="receipt-body">
    <div class="info-grid">
      <div class="info-block">
        <label>Selger</label>
        <p>
          {_esc(company['name'])}<br>
          Org.nr {_esc(company['org_nr'])}<br>
          {_esc(company['address'])}<br>
          {_esc(company['city'])}, {_esc(company['country'])}
        </p>
      </div>
      <div class="info-block">
        <label>Kjøper</label>
        <p>{cust_html}</p>
      </div>
      <div class="info-block">
        <label>Ordredato</label>
        <p>{date_str}</p>
      </div>
      <div class="info-block">
        <label>Betalingsstatus</label>
        <p>{_esc(_translate_status(order['financial_status']))}</p>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th style="text-align:left">Produkt</th>
          <th style="text-align:left">SKU</th>
          <th style="text-align:center">Antall</th>
          <th style="text-align:right">Enhetspris</th>
          <th style="text-align:right">MVA</th>
          <th style="text-align:right">Sum</th>
        </tr>
      </thead>
      <tbody>
        {rows_html}
      </tbody>
    </table>

    <table class="totals-table">
      <tbody>
        <tr>
          <td style="color:#6b7280">Subtotal ekskl. MVA</td>
          <td style="text-align:right">{_fmt_nok(total_ex_vat)}</td>
        </tr>
        <tr>
          <td style="color:#6b7280">MVA (25 %)</td>
          <td style="text-align:right">{_fmt_nok(calculated_vat)}</td>
        </tr>
        {discount_row}
        {shipping_row}
        <tr class="total-row">
          <td>Totalt inkl. MVA</td>
          <td style="text-align:right">{_fmt_nok(total)}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="receipt-footer">
    <p>
      <strong>{_esc(company['name'])}</strong> &middot; Org.nr {_esc(company['org_nr'])} &middot;
      {_esc(company['address'])}, {_esc(company['city'])} &middot; {_esc(company['website'])}
    </p>
    <p style="margin-top:4px">Kvittering generert {datetime.now().strftime('%d.%m.%Y kl. %H:%M')}</p>
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


receipt_service = ReceiptService()
