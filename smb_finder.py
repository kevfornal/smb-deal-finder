import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

# ==============================================================================
# STATIC BUY-BOX CRITERIA
# ==============================================================================
MIN_CASH_FLOW = 100_000         # Min Annual Net Profit / Cash Flow ($100k)
MIN_PRICE = 500_000             # Min Asking Price ($500k)
MAX_PRICE = 2_000_000           # Max Asking Price ($2M)
MIN_YEARS_ESTABLISHED = 5       # Min Established Age (5+ Years)
MIN_CF_MULTIPLE = 2.0           # Min Cash Flow Multiple (2.0x)
MAX_CF_MULTIPLE = 4.0           # Max Cash Flow Multiple (4.0x)

# CONFIGURATION FROM SECRETS
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")
HISTORY_FILE = "listings_history.json"


def parse_numeric(value):
    """Clean currency/numeric strings into floats."""
    if not value or str(value).upper() in ["N/A", "UNDISCLOSED", "CONTACT SELLER"]:
        return None
    cleaned = str(value).replace('$', '').replace(',', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def meets_buy_box_criteria(deal):
    """Evaluates listing against static criteria."""
    price = parse_numeric(deal.get('price'))
    cash_flow = parse_numeric(deal.get('cash_flow'))
    years_est = parse_numeric(deal.get('years_established'))

    if price is None or not (MIN_PRICE <= price <= MAX_PRICE):
        return False, "Price outside $500k–$2M range"

    if cash_flow is None or cash_flow < MIN_CASH_FLOW:
        return False, "Cash flow under $100,000"

    multiple = price / cash_flow
    if not (MIN_CF_MULTIPLE <= multiple <= MAX_CF_MULTIPLE):
        return False, f"Multiple ({multiple:.2f}x) outside 2.0x–4.0x range"

    if years_est is not None and years_est < MIN_YEARS_ESTABLISHED:
        return False, f"Established only {years_est} years (Needs 5+)"

    deal['calculated_multiple'] = f"{multiple:.2f}x"
    deal['calculated_yield'] = f"{(cash_flow / price) * 100:.1f}%"
    return True, "Matches Buy-Box"


def fetch_scraped_listings():
    """
    Placeholder aggregator for web scrapers/APIs (Acquire.com, BizBuySell, etc.)
    Replace/expand this block with real site scrapers or API payloads.
    """
    # Sample structure of retrieved deals
    return [
        {
            "id": "acq_101",
            "title": "B2B SaaS - Workflow Automation",
            "price": "$850,000",
            "cash_flow": "$260,000",
            "years_established": 6,
            "link": "https://acquire.com",
            "source": "Acquire.com"
        }
    ]


def send_email_alert(new_matches):
    """Formats and sends email notifications for new matching deals."""
    if not new_matches or not SMTP_USER or not SMTP_PASS:
        print("No new matches or missing SMTP settings. Skipping email.")
        return

    subject = f"🎯 {len(new_matches)} New Business Deal(s) Matching Your Buy-Box!"
    body = "<h2>Matching Deal Summary</h2><ul>"
    
    for deal in new_matches:
        body += f"""
        <li>
            <strong>{deal['title']}</strong> ({deal['source']})<br/>
            <b>Price:</b> {deal['price']} | <b>Cash Flow:</b> {deal['cash_flow']}<br/>
            <b>Multiple:</b> {deal['calculated_multiple']} | <b>Yield:</b> {deal['calculated_yield']}<br/>
            <a href="{deal['link']}">View Listing Details →</a>
        </li><br/>
        """
    body += "</ul>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_USER
    msg["To"] = RECIPIENT_EMAIL
    msg.attach(MIMEText(body, "html"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, RECIPIENT_EMAIL, msg.as_string())
    print("Email alert sent successfully!")


def main():
    # Load past deal history
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
    else:
        history = {}

    raw_listings = fetch_scraped_listings()
    new_matches = []

    for deal in raw_listings:
        deal_id = deal['id']
        if deal_id in history:
            continue  # Already processed

        is_match, reason = meets_buy_box_criteria(deal)
        if is_match:
            print(f"MATCH: {deal['title']}")
            history[deal_id] = deal
            new_matches.append(deal)

    # Save updated history
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

    # Send alerts if new deals found
    if new_matches:
        send_email_alert(new_matches)


if __name__ == "__main__":
    main()
