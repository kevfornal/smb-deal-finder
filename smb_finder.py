import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup

# ==============================================================================
# STATIC BUY-BOX CRITERIA
# ==============================================================================
MIN_CASH_FLOW = 1         # Min Annual Net Profit / Cash Flow ($100k)
MIN_PRICE = 10_000             # Min Asking Price ($500k)
MAX_PRICE = 10_000_000           # Max Asking Price ($2,000,000)
MIN_YEARS_ESTABLISHED = 0       # Min Established Age (5+ Years)
MIN_CF_MULTIPLE = 0.5           # Min Cash Flow Multiple (2.0x)
MAX_CF_MULTIPLE = 10.0           # Max Cash Flow Multiple (4.0x)

# CONFIGURATION FROM SECRETS
SMTP_SERVER = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")
ACQUIRE_COOKIE = os.environ.get("ACQUIRE_COOKIE")
HISTORY_FILE = "smb_listings_history.json"


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


def fetch_smb_market_listings():
    """Scrapes listings from SMB market channels."""
    deals = []
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # Target listing endpoint
    url = "https://smb.co/businesses-for-sale"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            for card in soup.select('.listing-card, .business-card, tr.listing'):
                title_el = card.select_one('.title, .listing-title, h3')
                price_el = card.select_one('.price, .asking-price')
                cf_el = card.select_one('.cash-flow, .sde')
                link_el = card.select_one('a')

                if title_el and link_el:
                    link = link_el['href']
                    if not link.startswith('http'):
                        link = f"https://smb.co{link}"
                    
                    deals.append({
                        "id": f"smb_{abs(hash(link))}",
                        "source": "SMB.co",
                        "title": title_el.text.strip(),
                        "price": price_el.text.strip() if price_el else "N/A",
                        "cash_flow": cf_el.text.strip() if cf_el else "N/A",
                        "years_established": 5, # Default fallback if unlisted
                        "link": link
                    })
    except Exception as e:
        print(f"Error scraping SMB market: {e}")
    return deals


def fetch_acquire_listings():
    """Fetches public/authenticated listings from Acquire.com API."""
    deals = []
    headers = {'User-Agent': 'Mozilla/5.0'}
    if ACQUIRE_COOKIE:
        headers['Cookie'] = ACQUIRE_COOKIE

    url = "https://app.acquire.com/api/listings/search"
    payload = {
        "askingPriceMin": MIN_PRICE,
        "askingPriceMax": MAX_PRICE,
        "profitMin": MIN_CASH_FLOW
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            listings = data.get('listings', [])
            for item in listings:
                deals.append({
                    "id": f"acq_{item.get('id', item.get('_id'))}",
                    "source": "Acquire.com",
                    "title": item.get('title', 'Acquire SaaS / Business'),
                    "price": f"${item.get('askingPrice', 0):,}",
                    "cash_flow": f"${item.get('profit', 0):,}",
                    "years_established": item.get('ageInYears', 5),
                    "link": f"https://app.acquire.com/listing/{item.get('id')}"
                })
    except Exception as e:
        print(f"Error fetching Acquire listings: {e}")
        
    return deals


def fetch_all_listings():
    """Aggregates listings across target platforms."""
    all_deals = []
    all_deals.extend(fetch_smb_market_listings())
    all_deals.extend(fetch_acquire_listings())
    return all_deals


def send_email_alert(new_matches):
    """Sends email alert when new matching listings are discovered."""
    if not new_matches or not SMTP_USER or not SMTP_PASS:
        print("No new matches or missing SMTP settings. Skipping email notification.")
        return

    subject = f"🚨 {len(new_matches)} New SMB Deal(s) Found Matching Your Buy-Box!"
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
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r') as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = {}
    else:
        history = {}

    raw_listings = fetch_all_listings()
    new_matches = []

    for deal in raw_listings:
        deal_id = deal['id']
        if deal_id in history:
            continue

        is_match, reason = meets_buy_box_criteria(deal)
        if is_match:
            print(f"🎯 MATCH: {deal['title']} ({deal['price']})")
            history[deal_id] = deal
            new_matches.append(deal)
        else:
            print(f"Skipped {deal.get('title', 'Deal')}: {reason}")

    # Save updated history
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

    # Trigger alert if new matches exist
    if new_matches:
        send_email_alert(new_matches)


if __name__ == "__main__":
    main()
