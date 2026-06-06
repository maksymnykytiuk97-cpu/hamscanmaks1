from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
import asyncio
import logging
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import resend
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import bcrypt
import jwt
import requests
from bs4 import BeautifulSoup
import re
import uuid
import hashlib

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Resend setup
resend.api_key = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'maximnikityk@ukr.net')

# Web Push (VAPID) setup
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_CLAIM_EMAIL = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@hamburg-scanner.com')

# JWT setup
JWT_ALGORITHM = "HS256"

def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")
auth_router = APIRouter(prefix="/api/auth")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============= MODELS =============

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    role: str = "user"

class Apartment(BaseModel):
    id: str
    title: str
    price: Optional[float] = None
    rooms: Optional[float] = None
    area: Optional[float] = None
    district: Optional[str] = None
    address: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    landlord: Optional[str] = None
    found_at: datetime
    status: str = "new"

# ============= AUTH HELPERS =============

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
        "type": "access"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh"
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        
        user["_id"] = str(user["_id"])
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

async def get_admin_user(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

def set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    response.set_cookie(
        key="access_token", value=access_token, httponly=True,
        secure=True, samesite="none", max_age=86400, path="/"
    )
    response.set_cookie(
        key="refresh_token", value=refresh_token, httponly=True,
        secure=True, samesite="none", max_age=604800, path="/"
    )

# ============= SCRAPER FUNCTIONS =============

# Playwright is optional. Some deploy environments (e.g. Emergent native)
# cannot install the Chromium binary at build time. When unavailable, the
# scrapers that rely on it skip cleanly while the GraphQL/HTTP-based ones
# (Immomio, SAGA, GCV, BDS, VHW, BGFG, Hamburger Wohnen, Walddörfer) continue
# to work. Set PLAYWRIGHT_DISABLED=1 to force-skip without trying the import.
_PLAYWRIGHT_DISABLED = os.environ.get("PLAYWRIGHT_DISABLED", "0").lower() in ("1", "true", "yes")

def _import_playwright_sync():
    """Return playwright.sync_api.sync_playwright or None if unavailable."""
    if _PLAYWRIGHT_DISABLED:
        return None
    try:
        from playwright.sync_api import sync_playwright  # noqa: WPS433
        return sync_playwright
    except Exception as e:
        logger.warning(f"Playwright unavailable, browser-based scrapers will be skipped: {e}")
        return None


IMMOMIO_GRAPHQL_URL = "https://gql-ps.immomio.com/tenant/graphql"


def _extract_immomio_homepage_token(url: str) -> Optional[str]:
    """Extract `token` query param from a homepage.immomio.com landlord URL.
    Returns the token string, or None if the URL is not a homepage-token URL.
    """
    if 'homepage.immomio.com' not in url:
        return None
    m = re.search(r'[?&]token=([A-Za-z0-9_\-\.]+)', url)
    return m.group(1) if m else None

IMMOMIO_PROPERTY_QUERY = """
query Property($id: ID!) {
  property(id: $id) {
    id
    status
    applyLink
    customer { name logo }
    data {
      name
      size
      rooms
      halfRooms
      totalRentGross
      basePrice
      customerName
      customerLogo
      address { city street houseNumber zipCode region country }
      attachments { url title type }
    }
  }
}
"""


def parse_immomio_listing(url: str, raise_errors: bool = False) -> Optional[dict]:
    """Parse a single immomio.com/apply/{uuid} listing via Immomio's public GraphQL API.
    No Chromium / Playwright required.
    """
    uuid_match = re.search(r'/apply/([a-f0-9\-]+)', url, re.IGNORECASE)
    if not uuid_match:
        if raise_errors:
            raise ValueError(f"Could not extract listing UUID from URL: {url}")
        return None
    listing_id = uuid_match.group(1)

    try:
        resp = requests.post(
            IMMOMIO_GRAPHQL_URL,
            json={"query": IMMOMIO_PROPERTY_QUERY, "variables": {"id": listing_id}},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Origin": "https://tenant.immomio.com",
                "Referer": "https://tenant.immomio.com/",
            },
            timeout=20,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.error(f"Immomio GraphQL request failed for {url}: {e}")
        if raise_errors:
            raise
        return None

    if payload.get("errors"):
        err_msg = "; ".join(err.get("message", "?") for err in payload["errors"])
        logger.error(f"Immomio GraphQL errors for {url}: {err_msg}")
        if raise_errors:
            raise RuntimeError(f"Immomio GraphQL error: {err_msg}")
        return None

    prop = (payload.get("data") or {}).get("property")
    if not prop:
        logger.info(f"Listing not active / not found: {url}")
        if raise_errors:
            raise RuntimeError("Wohnung nicht gefunden oder bereits offline")
        return None

    data = prop.get("data") or {}

    # Title
    title = (data.get("name") or "").strip() or "Wohnung in Hamburg"

    # Rooms (Zimmer + halbe Zimmer)
    rooms = data.get("rooms")
    half_rooms = data.get("halfRooms")
    if rooms is not None:
        try:
            rooms = float(rooms)
            if half_rooms:
                rooms += float(half_rooms) * 0.5
        except (TypeError, ValueError):
            rooms = None
            # Area
    area = data.get("size")
    if area is not None:
        try:
            area = float(area)
        except (TypeError, ValueError):
            area = None

    # Price (total rent gross, fallback to base price)
    price = data.get("totalRentGross") or data.get("basePrice")
    if price is not None:
        try:
            price = float(price)
        except (TypeError, ValueError):
            price = None

    # Address - "Street Nr, PLZ City"
    address = None
    district = None
    addr = data.get("address") or {}
    street = (addr.get("street") or "").strip()
    house_no = (addr.get("houseNumber") or "").strip()
    zip_code = (addr.get("zipCode") or "").strip()
    city = (addr.get("city") or "").strip()
    if street or zip_code or city:
        parts = []
        street_part = (street + (f" {house_no}" if house_no else "")).strip()
        if street_part:
            parts.append(street_part)
        city_part = (f"{zip_code} {city}".strip())
        if city_part:
            parts.append(city_part)
        address = ", ".join(parts) if parts else None

    # District from title ("3-Zimmer Wohnung in Steilshoop")
    dist_match = re.search(r'\bin\s+([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)', title)
    if dist_match:
        district = dist_match.group(1).strip()
    if not district:
        dist_match = re.search(r'Hamburg-([A-ZÄÖÜ][A-Za-zÄÖÜäöüß\-]+)', title)
        if dist_match:
            district = dist_match.group(1)

    # Image - first IMG attachment
    image_url = None
    for att in (data.get("attachments") or []):
        if att.get("type") == "IMG" and att.get("url"):
            image_url = att["url"]
            break
    if not image_url:
        image_url = data.get("customerLogo") or (prop.get("customer") or {}).get("logo")

    # Landlord
    landlord = (
        data.get("customerName")
        or (prop.get("customer") or {}).get("name")
    )
    if landlord:
        landlord = landlord.strip()[:150]

    return {
        "id": listing_id,
        "title": title,
        "price": price,
        "rooms": rooms,
        "area": area,
        "district": district,
        "address": address,
        "url": url,
        "image_url": image_url,
        "landlord": landlord,
        "found_at": datetime.now(timezone.utc),
        "status": "new",
    }


def _scrape_landlord_pages(start_url: str, detail_link_pattern: str, base_url: str, source_name: str, max_pages: int = 30) -> List[str]:
    """Generic Playwright scraper - finds immomio URLs by visiting detail pages of a landlord site"""
    import time
    immomio_urls = set()
    
    sync_playwright = _import_playwright_sync()
    if sync_playwright is None:
        return list(immomio_urls)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                ]
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='de-DE',
                viewport={'width': 1920, 'height': 1080},
                extra_http_headers={
                    'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                }
            )
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {}, app: {} };
            """)
            page = context.new_page()
            
            try:
                page.goto(start_url, timeout=60000, wait_until='networkidle')
                
                # Wait for Friendly Captcha to solve (auto, ~10s)
                for _ in range(15):
                    time.sleep(2)
                    title = page.title()
                    if 'Bot check' not in title and 'Sicherheitspr' not in title:
                        break
                
                # Accept cookies via JS (multiple methods to be reliable)
                try:
                    page.evaluate("""
                        () => {
                            const buttons = document.querySelectorAll('button, a, span');
                            for (const b of buttons) {
                                const txt = (b.innerText || b.textContent || '').trim().toUpperCase();
                                if (txt === 'ALLES AKZEPTIEREN' || txt === 'ALLE AKZEPTIEREN' || txt === 'ACCEPT ALL') {
                                    b.click();
                                    return;
                                }
                            }
                        }
                    """)
                except Exception:
                    pass
                
                # Extra wait for content to load via AJAX
                page.wait_for_timeout(6000)
                html = page.content()
                
                # Find immomio links directly
                direct_links = re.findall(
                    r'https?://tenant\.immomio\.com/(?:de/)?apply/[a-f0-9-]+',
                    html
                )
                immomio_urls.update(direct_links)
                
                # Find detail page links
                detail_paths = list(dict.fromkeys(re.findall(detail_link_pattern, html)))
                logger.info(f"{source_name}: found {len(detail_paths)} detail pages, visiting first {max_pages}")
                
                # Visit each detail page
                for detail_path in detail_paths[:max_pages]:
                    try:
                        detail_url = detail_path if detail_path.startswith('http') else f'{base_url}{detail_path}'
                        page.goto(detail_url, timeout=20000, wait_until='domcontentloaded')
                        page.wait_for_timeout(3000)
                        detail_html = page.content()
                        
                        found = re.findall(r'https?://tenant\.immomio\.com/(?:de/)?apply/[a-f0-9-]+', detail_html)
                        immomio_urls.update(found)
                        
                        iframe_srcs = re.findall(r'<iframe[^>]*src="([^"]*immomio[^"]*)"', detail_html)
                        for iframe in iframe_srcs:
                            uuid_match = re.search(r'apply/([a-f0-9-]+)', iframe)
                            if uuid_match:
                                immomio_urls.add(f"https://tenant.immomio.com/apply/{uuid_match.group(1)}")
                    except Exception as e:
                        logger.debug(f"{source_name}: error on detail page: {e}")
                        continue
            except Exception as e:
                logger.error(f"{source_name}: error in main scrape: {str(e)}")
            finally:
                browser.close()
        
        logger.info(f"{source_name} scraper found {len(immomio_urls)} immomio URLs")
    except Exception as e:
        logger.error(f"{source_name} scraper failed: {str(e)}")
    
    return list(immomio_urls)


def _saga_solve_pow_session() -> Optional[requests.Session]:
    """
    Bypass SAGA's bot-check by solving the PoW challenge and faking the
    Friendly-Captcha validation step. Returns an authenticated Session, or None.
    """
    import hashlib
    s = requests.Session()
    s.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                     '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'de-DE,de;q=0.9,en;q=0.8',
    })
    base_url = 'https://www.saga.hamburg/immobiliensuche/aktuelle_angebote/wohnung'
    try:
        # Step 1: trigger initial request (gets the bot-check HTML, no cookies yet)
        s.get(base_url, timeout=20)

        # Step 2: solve PoW challenge → POWSESS cookie
        c = s.get(base_url + '?create_challenge', timeout=15).json()
        algo = getattr(hashlib, c.get('algo', 'sha256'))
        salt, expire, target = c['salt'], c['expire'], c['challenge']
        number = None
        for i in range(1, int(c.get('max_number', 100000)) + 1):
            if algo(f"{i}{salt}{expire}".encode()).hexdigest() == target:
                number = i
                break
        if number is None:
            logger.warning("SAGA: PoW challenge unsolvable")
            return None
        payload = {"number": number, "verify": c['verify'], "salt": salt,
                   "expire": expire, "algo": c['algo']}
        r = s.post(base_url + '?verify_challenge', json=payload, timeout=15)
        if r.status_code != 200:
            logger.warning(f"SAGA: PoW verify failed {r.status_code}")
            return None

        # Step 3: bypass Friendly-Captcha — server only checks the POST exists
        s.post('https://www.saga.hamburg/captcha-validate',
               json={"solution": ".UNFINISHED"},
               headers={'Content-Type': 'application/json'},
               timeout=15)
        return s
    except Exception as e:
        logger.error(f"SAGA PoW session failed: {e}")
        return None


def scrape_saga_direct() -> List[dict]:
    """
    SAGA direct scraping. Bypasses the bot-check by solving the PoW challenge
    and posting an empty Friendly-Captcha solution, then fetches the AJAX
    listings endpoint. No browser, no proxy required.
    """
    from bs4 import BeautifulSoup
    apartments: List[dict] = []
    s = _saga_solve_pow_session()
    if not s:
        return apartments

    url = 'https://www.saga.hamburg/immobiliensuche/aktuelle_angebote/wohnung'
    try:
        r = s.get(url, headers={'X-Requested-With': 'XMLHttpRequest'}, timeout=20)
        if r.status_code != 200:
            logger.warning(f"SAGA listings fetch failed: {r.status_code}")
            return apartments

        soup = BeautifulSoup(r.text, 'html.parser')
        # Each apartment card has id="APARTMENT-card-N"
        cards = soup.select('div[id^="APARTMENT-card-"]')
        logger.info(f"SAGA: found {len(cards)} apartment cards")

        for card in cards:
            try:
                # Title + URL come from the title <a>
                title_a = card.select_one('h3 a')
                if not title_a:
                    continue
                title = title_a.get_text(strip=True)
                path = title_a.get('href', '')
                if not path.startswith('/'):
                    continue
                detail_url = f'https://www.saga.hamburg{path}'

                # Stable id from the SAGA detail path (e.g. /immo-detail/6614/...)
                m = re.search(r'/immo-detail/(\d+)/', path)
                saga_id = m.group(1) if m else hashlib.md5(path.encode()).hexdigest()[:10]

                # District is the first .font-bold paragraph
                district_p = card.select_one('hgroup p.font-bold')
                district = district_p.get_text(strip=True) if district_p else None

                # Address sits in the first <p class="pb-3 md:grow">
                addr_p = card.select_one('p.pb-3.md\\:grow') or card.find('p', class_='pb-3')
                address = addr_p.get_text(strip=True) if addr_p else None

                # Rooms, area, price live in data-* attributes (rich data, never hidden)
                rooms = area = price = None
                el = card.select_one('[data-rooms]')
                if el and el.get('data-rooms'):
                    try:
                        rooms = float(el['data-rooms'].replace(',', '.'))
                    except ValueError:
                        pass
                el = card.select_one('[data-livingSpace], [data-livingspace]')
                if el:
                    val = el.get('data-livingSpace') or el.get('data-livingspace')
                    if val:
                        try:
                            area = float(val.replace('.', '').replace(',', '.'))
                        except ValueError:
                            pass
                el = card.select_one('[data-fullCosts], [data-fullcosts]')
                if el:
                    val = el.get('data-fullCosts') or el.get('data-fullcosts')
                    if val:
                        try:
                            price = float(val.replace('.', '').replace(',', '.'))
                        except ValueError:
                            pass

                # First <img> inside the card is the preview
                image_url = None
                img = card.find('img')
                if img and img.get('src'):
                    src = img['src']
                    image_url = src if src.startswith('http') else f'https://www.saga.hamburg{src}'

                apartments.append({
                    "id": f"saga-{saga_id}",
                    "title": title[:200],
                    "price": price,
                    "rooms": rooms,
                    "area": area,
                    "district": district,
                    "address": address,
                    "url": detail_url,
                    "image_url": image_url,
                    "landlord": "SAGA Hamburg",
                    "found_at": datetime.now(timezone.utc),
                    "status": "new",
                })
            except Exception as e:
                logger.debug(f"SAGA card parse error: {e}")
                continue

        logger.info(f"SAGA direct: parsed {len(apartments)} apartments")
    except Exception as e:
        logger.error(f"SAGA direct failed: {e}")

    return apartments


async def scan_saga_only():
    """Lightweight SAGA-only scan (runs every minute for fast detection)"""
    if scanning_state["is_scanning"]:
        return
    try:
        saga_apts = await asyncio.to_thread(scrape_saga_direct)
        if not saga_apts:
            return
        
        new_count = 0
        for apt in saga_apts:
            existing = await db.apartments.find_one({"id": apt["id"]}, {"_id": 0})
            if not existing:
                apt_dict = apt.copy()
                if isinstance(apt_dict['found_at'], datetime):
                    apt_dict['found_at'] = apt_dict['found_at'].isoformat()
                await db.apartments.insert_one(apt_dict)
                new_count += 1
                logger.info(f"SAGA quick-scan: new apartment {apt['title']}")
        
        if new_count > 0:
            logger.info(f"SAGA quick-scan: {new_count} new apartments found")
    except Exception as e:
        logger.error(f"SAGA quick-scan error: {e}")


# Immomio homepage tokens for landlords (extracted from their websites)
IMMOMIO_TOKENS = {
    'BGFG': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoxNTY2MDQwMzUsImlkIjoxNzA2MDA0NjIsImNyZWF0ZWQiOjE2NDIxNjYwNDY2Mzh9.1QlkdnxWyyJMcRS1JubN1EkDrHPRaqfASe6oUJq7ptU',
    'Hamburger Wohnen': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoxNDI3MzI5MjksImlkIjoxODcwMDEzMjAsImNyZWF0ZWQiOjE2NTc0NzYyMzg4Nzl9.C1vwdfjJ27h7-HWIvGKBrsgWGcj-8-ArzkiOKoBpSgs',
    'BDS Hamburg': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoyODYxOTA4ODMsImlkIjoyOTIxMTgyMzgsImNyZWF0ZWQiOjE2NjY1OTQ0NzE5OTJ9.l-IorHm_QkfJf7tidzsCoW9x9xeIk01uO8BbuzmJ6Bg',
    'VHW Hamburg': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoyNTQxMzQ1MDYsImlkIjoyNzI4MDEwODUsImNyZWF0ZWQiOjE2NjE5NDY5ODY1MDF9.fo3dJ4iNYF825tbg1E5C6q0mXbtbePO1LO3S_3_SEhM',
    # Walddörfer's iframe loads after cookie consent and uses this homepage token
    # (customerId=1250590938). The page also exposes a Tenant Pool registration
    # token, which we do NOT use — only this one queries propertyList.
    'Walddörfer': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoxMjUwNTkwOTM4LCJpZCI6MTI1NzM3OTYyMywiY3JlYXRlZCI6MTczOTQ0OTkyNjQwOX0.veqPULd54M9ruMr8OeqWmMaYH0cCm3PWahPvyRne9NE',
}


def scrape_immomio_landlord_token(landlord_name: str, token: str) -> List[dict]:
    """Fetch all apartments for a landlord using their immomio GraphQL token"""
    apartments = []
    
    query = """
    query propertyList($input: HomepagePropertySearchRequest!) {
      propertyList(input: $input) {
        page { totalElements totalPages }
        nodes {
          name totalRooms size totalRentGross propertyType marketingType externalId applicationLink
          titleImage { url }
          address { city street houseNumber zipCode district }
        }
      }
    }
    """
    
    try:
        variables = {
            "input": {
                "page": 0,
                "size": 100,
                "token": token,
                "propertyType": None,
                "wbs": None,
                "barrierFree": None,
                "balconyOrTerrace": None,
                "roomNumber": {"from": None, "to": None},
                "floor": {"from": None, "to": None},
                "totalRentGross": {"from": None, "to": None}
            }
        }
        
        response = requests.post(
            'https://gql-hp.immomio.com/homepage/graphql',
            json={'query': query, 'variables': variables, 'operationName': 'propertyList'},
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'},
            timeout=20
        )
        
        if response.status_code != 200:
            logger.warning(f"{landlord_name}: GraphQL returned {response.status_code}")
            return apartments
        
        data = response.json()
        if data.get('errors'):
            logger.warning(f"{landlord_name}: GraphQL errors: {data['errors'][:1]}")
            return apartments
        
        nodes = data.get('data', {}).get('propertyList', {}).get('nodes', [])
        
        for node in nodes:
            # Only apartments/houses, skip GARAGE/parking spots
            ptype = node.get('propertyType', '').upper()
            if ptype in ('GARAGE', 'PARKING', 'GEWERBE', 'OFFICE', 'STORAGE', 'COMMERCIAL'):
                continue
            
            apply_link = node.get('applicationLink')
            if not apply_link:
                continue
            
            # Extract UUID from apply link
            uuid_match = re.search(r'/apply/([a-f0-9-]+)', apply_link)
            if not uuid_match:
                continue
            listing_id = uuid_match.group(1)
            
            addr = node.get('address', {}) or {}
            address_str = None
            if addr.get('street'):
                parts = [
                    f"{addr.get('street', '')} {addr.get('houseNumber', '')}".strip(),
                    f"{addr.get('zipCode', '')} {addr.get('city', '')}".strip()
                ]
                if addr.get('district'):
                    parts.append(addr['district'])
                address_str = ', '.join([p for p in parts if p])
            
            # Only Hamburg
            if addr.get('city') and 'Hamburg' not in addr['city']:
                continue
            
            apartment = {
                "id": listing_id,
                "title": node.get('name', 'Wohnung in Hamburg'),
                "price": float(node['totalRentGross']) if node.get('totalRentGross') else None,
                "rooms": float(node['totalRooms']) if node.get('totalRooms') else None,
                "area": float(node['size']) if node.get('size') else None,
                "district": addr.get('district'),
                "address": address_str,
                "url": apply_link,
                "image_url": (node.get('titleImage') or {}).get('url'),
                "landlord": landlord_name,
                "found_at": datetime.now(timezone.utc),
                "status": "new"
            }
            apartments.append(apartment)
        
        logger.info(f"{landlord_name}: GraphQL returned {len(apartments)} apartments")
    
    except Exception as e:
        logger.error(f"{landlord_name} GraphQL error: {str(e)}")
    
    return apartments


def extract_immomio_token_from_site(landlord_name: str, site_url: str) -> Optional[str]:
    """Extract immomio token from a landlord website by parsing the iframe src"""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        response = requests.get(site_url, headers=headers, timeout=15)
        if response.status_code != 200:
            return None
        # Find iframe with immomio token
        match = re.search(r'homepage\.immomio\.com/de/properties\?token=([^"\'&\s]+)', response.text)
        if match:
            return match.group(1)
    except Exception as e:
        logger.error(f"Error extracting token from {landlord_name}: {e}")
    return None


def scrape_saga_hamburg() -> List[str]:
    """DEPRECATED - replaced by scrape_saga_direct(). Returns empty."""
    return []


def scrape_vonovia_hamburg() -> List[dict]:
    """Vonovia Hamburg - DIRECT scraping (not via immomio).
    Returns full apartment dicts with vonovia.de URLs."""
    import time
    apartments = []
    
    sync_playwright = _import_playwright_sync()
    if sync_playwright is None:
        return apartments
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
            )
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                locale='de-DE',
                viewport={'width': 1920, 'height': 1080}
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined });")
            page = context.new_page()
            
            try:
                # Search Hamburg with 25km radius
                page.goto(
                    'https://www.vonovia.de/zuhause-finden/immobilien?rentType=miete&latitude=53.6035393&longitude=9.9495941&perimeter=25&immoType=wohnung',
                    timeout=60000, wait_until='networkidle'
                )
                time.sleep(8)
                html = page.content()
                
                detail_paths = list(set(re.findall(r'href="(/zuhause-finden/immobilien/[^"]+)"', html)))
                logger.info(f"Vonovia: found {len(detail_paths)} apartments")
                
                for path in detail_paths[:30]:
                    try:
                        detail_url = f'https://www.vonovia.de{path}'
                        page.goto(detail_url, timeout=20000, wait_until='domcontentloaded')
                        time.sleep(3)
                        
                        text = page.evaluate('document.body.innerText')
                        dhtml = page.content()
                        
                        # Extract data from structured text
                        title_match = re.search(r'^([^\n]+(?:Wohnung|Apartment)[^\n]*)', text, re.MULTILINE)
                        title = title_match.group(1).strip() if title_match else 'Vonovia Wohnung Hamburg'
                        
                        # Address: "Streetname Nr - PLZ Hamburg ..."
                        addr_match = re.search(r'([\w\.\-äöüÄÖÜß\s]+?\s+\d+[a-zA-Z]?)\s*-\s*(\d{5})\s+Hamburg(?:\s+OT\s+([\w\-äöüÄÖÜß]+))?', text)
                        address = None
                        district = None
                        if addr_match:
                            address = f"{addr_match.group(1).strip()}, {addr_match.group(2)} Hamburg"
                            if addr_match.group(3):
                                district = addr_match.group(3).strip()
                                address += f" ({district})"
                        
                        # Price (Warmmiete preferred, fallback Kaltmiete)
                        price = None
                        warm_match = re.search(r'([\d.]+,\d{2})\s*€\s*\n?\s*Warmmiete', text)
                        if warm_match:
                            try:
                                price = float(warm_match.group(1).replace('.', '').replace(',', '.'))
                            except ValueError:
                                pass
                        if price is None:
                            kalt_match = re.search(r'([\d.]+,\d{2})\s*€\s*\n?\s*Kaltmiete', text)
                            if kalt_match:
                                try:
                                    price = float(kalt_match.group(1).replace('.', '').replace(',', '.'))
                                except ValueError:
                                    pass
                        
                        # Area
                        area = None
                        area_match = re.search(r'([\d.]+,\d+)\s*m²\s*\n?\s*Größe', text)
                        if area_match:
                            try:
                                area = float(area_match.group(1).replace('.', '').replace(',', '.'))
                            except ValueError:
                                pass
                        
                        # Rooms
                        rooms = None
                        # Try "X,X Zimmer" or "X-Zimmer"
                        rooms_match = re.search(r'([\d.]+,\d+|\d+)\s*\n?\s*Zimmer\s*\n', text)
                        if rooms_match:
                            try:
                                rooms = float(rooms_match.group(1).replace(',', '.'))
                            except ValueError:
                                pass
                        if rooms is None:
                            t_rooms = re.search(r'(\d+(?:[,.]\d+)?)\s*[-\s]?Zimmer', title)
                            if t_rooms:
                                try:
                                    rooms = float(t_rooms.group(1).replace(',', '.'))
                                except ValueError:
                                    pass
                        
                        # Image — try a few patterns in order of preference
                        image_url = None
                        for pat in (
                            r'src="(https://cdn\.expose\.vonovia\.de/[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                            r'srcset="(https://cdn\.expose\.vonovia\.de/[^",\s]+)',
                            r'<meta[^>]+property="og:image"[^>]+content="(https://[^"]+)"',
                            r'src="(https://(?:cdn|images?)\.[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"',
                        ):
                            m = re.search(pat, dhtml)
                            if m:
                                image_url = m.group(1).split('&amp;')[0].split(' ')[0]
                                break
                        
                        # Use URL path as unique ID
                        listing_id = f"vonovia-{path.split('/')[-1]}"
                        
                        apartments.append({
                            "id": listing_id,
                            "title": title[:200],
                            "price": price,
                            "rooms": rooms,
                            "area": area,
                            "district": district,
                            "address": address,
                            "url": detail_url,
                            "image_url": image_url,
                            "landlord": "Vonovia",
                            "found_at": datetime.now(timezone.utc),
                            "status": "new"
                        })
                    except Exception as e:
                        logger.debug(f"Vonovia detail error: {e}")
                        continue
            except Exception as e:
                logger.error(f"Vonovia main error: {e}")
            finally:
                browser.close()
        
        logger.info(f"Vonovia: parsed {len(apartments)} apartments")
    except Exception as e:
        logger.error(f"Vonovia failed: {e}")
    
    return apartments


def scrape_walddoerfer_direct() -> List[dict]:
    """Walddörfer redirects everything to Immomio — the GraphQL path in
    IMMOMIO_TOKENS handles their listings. The direct HTML scrape is a no-op.
    """
    return []


def scrape_walddoerfer() -> List[str]:
    """DEPRECATED - kept for compatibility, now returns empty"""
    return []


def scrape_gcv() -> List[dict]:
    """
    GCV Verwaltungsgesellschaft. The actual listings are not on gcv-gmbh.de —
    that page only embeds an ImmoScout24 portfolio iframe
    (portal.immobilienscout24.de/ergebnisliste/84239610).
    We scrape the IS24 portal directly via plain HTTP.
    """
    from bs4 import BeautifulSoup
    apartments: List[dict] = []
    portal_url = 'https://portal.immobilienscout24.de/ergebnisliste/84239610'
    try:
        r = requests.get(
            portal_url,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9',
                'Accept-Language': 'de-DE,de;q=0.9',
            },
            timeout=20,
        )
        if r.status_code != 200:
            logger.warning(f"GCV (IS24): status {r.status_code}")
            return apartments

        soup = BeautifulSoup(r.text, 'html.parser')
        cards = soup.select('.result__list--element')
        logger.info(f"GCV (IS24): found {len(cards)} cards")

        for card in cards:
            try:
                text = card.get_text(' ', strip=True)

                # Skip commercial properties (Gastronomie, Büro, Lager …)
                if any(kw in text for kw in [
                    'Gastronomie', 'Gewerbe', 'Büro', 'Lager', 'Restaurant',
                    'Imbiss', 'Halle', 'Gesamtfläche',
                ]):
                    continue
                # Only Hamburg (some IS24 portfolios include neighbouring towns)
                if 'Hamburg' not in text:
                    continue

                # Title comes from the second <a> tag (the linked title text).
                # The class `.result__list__element__infos__list--title` is a
                # label class used for "Kaltmiete"/"Wohnfläche"/"Zimmer" labels,
                # NOT the listing title — so we use the <a> text instead.
                title = None
                title_links = [
                    a for a in card.find_all('a', href=True)
                    if a.get_text(' ', strip=True)
                ]
                if title_links:
                    title = title_links[0].get_text(' ', strip=True)
                if not title:
                    title = 'GCV Wohnung'

                # Detail link
                a = card.find('a', href=True)
                href = a['href'] if a else ''
                if href.startswith('/'):
                    detail_url = f'https://portal.immobilienscout24.de{href}'
                else:
                    detail_url = href or portal_url
                m = re.search(r'/expose/\d+/(\d+)', detail_url)
                expose_id = m.group(1) if m else hashlib.md5(detail_url.encode()).hexdigest()[:10]

                # Image (often //pictures.immobilienscout24.de/...)
                image_url = None
                img = card.find('img')
                if img:
                    src = img.get('src') or img.get('data-src') or ''
                    if src.startswith('//'):
                        src = f'https:{src}'
                    if src.startswith('http'):
                        image_url = src

                # Price (Kaltmiete) — value may be "1.266,23" or "3.000"
                price = None
                m = re.search(r'Kaltmiete\s*€\s*([\d.]+(?:,\d+)?)', text)
                if m:
                    try:
                        price = float(m.group(1).replace('.', '').replace(',', '.'))
                    except ValueError:
                        pass

                # Area (Wohnfläche)
                area = None
                m = re.search(r'Wohnfläche\s*([\d.]+(?:,\d+)?)\s*m²', text)
                if m:
                    try:
                        area = float(m.group(1).replace('.', '').replace(',', '.'))
                    except ValueError:
                        pass

                # Rooms (number after "Zimmer")
                rooms = None
                m = re.search(r'Zimmer\s+([\d]+(?:[,.]\d+)?)', text)
                if m:
                    try:
                        rooms = float(m.group(1).replace(',', '.'))
                    except ValueError:
                        pass

                # Address (street, …, Hamburg-District, Deutschland)
                address = None
                district = None
                m = re.search(
                    r'([\w\.\-äöüÄÖÜß\s]+\d+[a-zA-Z]?),\s*Hamburg(?:,\s*([\w\-äöüÄÖÜß]+))?',
                    text,
                )
                if m:
                    address = f"{m.group(1).strip()}, Hamburg"
                    if m.group(2):
                        district = m.group(2).strip()

                apartments.append({
                    "id": f"gcv-{expose_id}",
                    "title": title[:200],
                    "price": price,
                    "rooms": rooms,
                    "area": area,
                    "district": district,
                    "address": address,
                    "url": detail_url,
                    "image_url": image_url,
                    "landlord": "GCV Hamburg",
                    "found_at": datetime.now(timezone.utc),
                    "status": "new",
                })
            except Exception as e:
                logger.debug(f"GCV card parse error: {e}")
                continue

        logger.info(f"GCV: parsed {len(apartments)} apartments")
    except Exception as e:
        logger.error(f"GCV failed: {e}")

    return apartments


def search_google_for_immomio() -> List[str]:
    """Search Google for immomio Hamburg listings using DuckDuckGo as fallback"""
    immomio_urls = set()
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # DuckDuckGo HTML search (Google has more anti-bot, DDG works better)
        queries = [
            'site:tenant.immomio.com Hamburg',
            'site:tenant.immomio.com apply Hamburg',
            '"tenant.immomio.com/apply" Hamburg Wohnung',
        ]
        
        for query in queries:
            try:
                ddg_url = f'https://html.duckduckgo.com/html/?q={query}'
                response = requests.get(ddg_url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    # Find immomio apply URLs
                    found_urls = re.findall(
                        r'https?://tenant\.immomio\.com/(?:de/)?apply/[a-f0-9-]+',
                        response.text
                    )
                    immomio_urls.update(found_urls)
            except Exception as e:
                logger.error(f"Error searching '{query}': {str(e)}")
                continue
        
        logger.info(f"Google/DDG search found {len(immomio_urls)} immomio URLs")
    
    except Exception as e:
        logger.error(f"Error in Google search: {str(e)}")
    
    return list(immomio_urls)


async def scrape_immomio_hamburg():
    """Main scraping function - GraphQL for landlords with tokens + Playwright for others + manual URLs"""
    apartments = []
    
    try:
        # === STEP 1: GraphQL scraping for landlords with known tokens (FAST!) ===
        for landlord_name, token in IMMOMIO_TOKENS.items():
            try:
                landlord_apts = await asyncio.to_thread(scrape_immomio_landlord_token, landlord_name, token)
                apartments.extend(landlord_apts)
            except Exception as e:
                logger.error(f"{landlord_name} GraphQL failed: {e}")
        
        # === STEP 2: Refresh tokens from landlord websites (in case they change) ===
        landlord_sites = {
            'BGFG': 'https://www.bgfg.de/zuhause-finden/aktuelle-angebote',
            'Hamburger Wohnen': 'https://www.hamburgerwohnen.de/wohnen/wohnungssuche-home.html',
            'BDS Hamburg': 'https://www.bds-hamburg.de/unser-angebot/interessentenportal-immomio/',
            'VHW Hamburg': 'https://www.vhw-hamburg.de/wohnen/aktuelle-angebote.html',
        }
        for name, site_url in landlord_sites.items():
            try:
                token = await asyncio.to_thread(extract_immomio_token_from_site, name, site_url)
                if token and token != IMMOMIO_TOKENS.get(name):
                    logger.info(f"{name}: token refreshed from website")
                    fresh_apts = await asyncio.to_thread(scrape_immomio_landlord_token, name, token)
                    apartments.extend(fresh_apts)
                    IMMOMIO_TOKENS[name] = token
            except Exception as e:
                logger.debug(f"Token refresh for {name}: {e}")
        
        # === STEP 3: SAGA direct scraping (returns apartment dicts) ===
        try:
            saga_apts = await asyncio.to_thread(scrape_saga_direct)
            apartments.extend(saga_apts)
        except Exception as e:
            logger.error(f"SAGA scraper failed: {e}")
        
        # all_urls used by manual URLs below
        all_urls = set()
        
        # === STEP 4: DIRECT scrapers (Vonovia, Walddörfer - no immomio) ===
        try:
            vonovia_apts = await asyncio.to_thread(scrape_vonovia_hamburg)
            apartments.extend(vonovia_apts)
        except Exception as e:
            logger.error(f"Vonovia direct failed: {e}")
        
        try:
            wald_apts = await asyncio.to_thread(scrape_walddoerfer_direct)
            apartments.extend(wald_apts)
        except Exception as e:
            logger.error(f"Walddörfer direct failed: {e}")
        
        try:
            gcv_apts = await asyncio.to_thread(scrape_gcv)
            apartments.extend(gcv_apts)
        except Exception as e:
            logger.error(f"GCV failed: {e}")
        
        # === STEP 4: Manual URLs from database (apply + homepage-token) ===
        manual_urls = await db.manual_urls.find({}, {"_id": 0}).to_list(100)
        manual_apply_urls = []
        for item in manual_urls:
            mu_url = item['url']
            token = _extract_immomio_homepage_token(mu_url)
            if token:
                # Landlord-pool URL: fetch ALL Hamburg apartments for this token
                try:
                    name = item.get('label') or f"Manual:{token[:8]}"
                    token_apts = await asyncio.to_thread(scrape_immomio_landlord_token, name, token)
                    apartments.extend(token_apts)
                except Exception as e:
                    logger.error(f"Manual token URL failed for {mu_url}: {e}")
            else:
                manual_apply_urls.append(item)
                all_urls.add(mu_url)
        
        logger.info(f"Manual apply URLs to process: {len(all_urls)}")
        
        existing_ids = {a['id'] for a in apartments}
        for url in all_urls:
            normalized_url = url.replace('/de/apply/', '/apply/')
            uuid_match = re.search(r'/apply/([a-f0-9-]+)', normalized_url)
            if uuid_match and uuid_match.group(1) in existing_ids:
                continue
            
            try:
                apartment = await asyncio.to_thread(parse_immomio_listing, normalized_url)
            except Exception as e:
                logger.error(f"Parse error for {normalized_url}: {e}")
                continue
            
            if not apartment:
                continue
            
            is_hamburg = (
                (apartment.get('address') and 'Hamburg' in apartment['address']) or
                ('Hamburg' in apartment.get('title', ''))
            )
            is_manual = any(item['url'].replace('/de/apply/', '/apply/') == normalized_url for item in manual_apply_urls)
            
            if is_hamburg or is_manual:
                apartments.append(apartment)
        
        logger.info(f"TOTAL apartments collected: {len(apartments)}")
    
    except Exception as e:
        logger.error(f"Error in main scraper: {str(e)}")
    
    return apartments


# ============= SCAN TASK =============

scanning_state = {
    "is_scanning": False,
    "last_scan": None,
    "next_scan": None
}

async def scan_apartments():
    """Scan for new apartments and send email if found"""
    if scanning_state["is_scanning"]:
        logger.info("Scan already in progress, skipping...")
        return
    
    scanning_state["is_scanning"] = True
    logger.info("Starting apartment scan...")
    
    try:
        apartments = await scrape_immomio_hamburg()
        
        new_apartments = []
        total_found = len(apartments)
        
        for apt in apartments:
            existing = await db.apartments.find_one({"id": apt["id"]}, {"_id": 0})
            
            if not existing:
                apt_dict = apt.copy()
                if isinstance(apt_dict['found_at'], datetime):
                    apt_dict['found_at'] = apt_dict['found_at'].isoformat()
                await db.apartments.insert_one(apt_dict)
                new_apartments.append(apt)
                logger.info(f"New apartment found: {apt['title']}")
                # Live push to all connected dashboards
                try:
                    payload_apt = {k: v for k, v in apt_dict.items() if k != '_id'}
                    await ws_manager.broadcast({"type": "new_apartment", "apartment": payload_apt})
                except Exception as e:
                    logger.debug(f"WS broadcast new_apartment failed: {e}")
            else:
                # Update existing data if we now have more info
                update_fields = {}
                for field in ['price', 'rooms', 'area', 'district', 'address', 'image_url', 'landlord']:
                    if apt.get(field) is not None and existing.get(field) is None:
                        update_fields[field] = apt[field]
                if update_fields:
                    await db.apartments.update_one({"id": apt["id"]}, {"$set": update_fields})
                    logger.info(f"Updated apartment {apt['id']} with new fields: {list(update_fields.keys())}")
        
        # Log scan
        scan_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "found_count": total_found,
            "new_count": len(new_apartments),
            "status": "success",
            "message": f"Found {total_found} apartments, {len(new_apartments)} new"
        }
        await db.scan_logs.insert_one(scan_log)
        
        # Send email to all users with notifications enabled - filtered by their personal preferences
        if new_apartments and resend.api_key:
            users_to_notify = await db.users.find({
                "notifications_enabled": True,
                "notification_email": {"$ne": None, "$ne": ""}
            }, {
                "notification_email": 1, "min_price": 1, "max_price": 1, 
                "min_rooms": 1, "max_rooms": 1, "_id": 0
            }).to_list(1000)
            
            for user_prefs in users_to_notify:
                email_addr = user_prefs.get('notification_email')
                if not email_addr:
                    continue
                
                # Filter apartments based on user's personal preferences
                user_apts = []
                for apt in new_apartments:
                    if user_prefs.get('min_price') is not None and (apt.get('price') is None or apt['price'] < user_prefs['min_price']):
                        continue
                    if user_prefs.get('max_price') is not None and (apt.get('price') is None or apt['price'] > user_prefs['max_price']):
                        continue
                    if user_prefs.get('min_rooms') is not None and (apt.get('rooms') is None or apt['rooms'] < user_prefs['min_rooms']):
                        continue
                    if user_prefs.get('max_rooms') is not None and (apt.get('rooms') is None or apt['rooms'] > user_prefs['max_rooms']):
                        continue
                    user_apts.append(apt)
                
                if not user_apts:
                    logger.info(f"No matching apartments for {email_addr} (filtered out)")
                    continue
                
                try:
                    html_content = f"<h2>🏠 {len(user_apts)} neue Wohnungen in Hamburg gefunden!</h2>"
                    html_content += "<ul>"
                    for apt in user_apts:
                        html_content += f"<li><strong>{apt['title']}</strong><br>"
                        if apt.get('price'):
                            html_content += f"Preis: €{apt['price']:.2f}<br>"
                        if apt.get('rooms'):
                            html_content += f"Zimmer: {apt['rooms']}<br>"
                        if apt.get('area'):
                            html_content += f"Fläche: {apt['area']}m²<br>"
                        if apt.get('address'):
                            html_content += f"Adresse: {apt['address']}<br>"
                        if apt.get('landlord'):
                            html_content += f"Vermieter: {apt['landlord']}<br>"
                        html_content += f"<a href='{apt['url']}'>Zur Anzeige</a></li><br>"
                    html_content += "</ul>"
                    
                    params = {
                        "from": SENDER_EMAIL,
                        "to": [email_addr],
                        "subject": f"🏠 {len(user_apts)} neue Wohnungen in Hamburg",
                        "html": html_content
                    }
                    await asyncio.to_thread(resend.Emails.send, params)
                    logger.info(f"Email sent to {email_addr} with {len(user_apts)} filtered apartments")
                except Exception as e:
                    logger.error(f"Failed to send email to {email_addr}: {str(e)}")
        
        # ===== PUSH NOTIFICATIONS =====
        # Per-user web-push (PWA) — respects each user's profile filters.
        # Runs even when email is disabled or when user does not have an email
        # set, so users can opt into push-only delivery.
        if new_apartments:
            try:
                await send_push_notifications_for_new_apartments(new_apartments)
            except Exception as e:
                logger.error(f"Push notifications failed: {e}")

        scanning_state["last_scan"] = datetime.now(timezone.utc)
        scanning_state["next_scan"] = datetime.now(timezone.utc) + timedelta(minutes=3)

        # Notify dashboards that a scan just finished
        try:
            await ws_manager.broadcast({
                "type": "scan_finished",
                "found_count": total_found,
                "new_count": len(new_apartments),
                "last_scan": scanning_state["last_scan"].isoformat(),
                "next_scan": scanning_state["next_scan"].isoformat(),
            })
        except Exception as e:
            logger.debug(f"WS broadcast scan_finished failed: {e}")
    
    except Exception as e:
        logger.error(f"Error during scan: {str(e)}")
    
    finally:
        scanning_state["is_scanning"] = False


# ============= AUTH ENDPOINTS =============

@auth_router.post("/login")
async def login(credentials: UserLogin, response: Response):
    email = credentials.email.lower()
    user = await db.users.find_one({"email": email})
    
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    user_id = str(user["_id"])
    access_token = create_access_token(user_id, email)
    refresh_token = create_refresh_token(user_id)
    
    set_auth_cookies(response, access_token, refresh_token)
    
    return {
        "id": user_id,
        "email": email,
        "name": user.get("name"),
        "role": user.get("role", "user")
    }

@auth_router.post("/logout")
async def logout(response: Response):
    """Idempotent logout - always clears cookies regardless of auth state"""
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}

@auth_router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["_id"],
        "email": current_user["email"],
        "name": current_user.get("name"),
        "role": current_user.get("role", "user"),
        "notification_email": current_user.get("notification_email"),
        "notifications_enabled": current_user.get("notifications_enabled", False)
    }

# ============= PROFILE ENDPOINTS =============

class ProfileUpdate(BaseModel):
    notification_email: Optional[EmailStr] = None
    notifications_enabled: bool = False
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_rooms: Optional[float] = None
    max_rooms: Optional[float] = None

@api_router.get("/profile")
async def get_profile(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["_id"],
        "email": current_user["email"],
        "name": current_user.get("name"),
        "notification_email": current_user.get("notification_email") or current_user["email"],
        "notifications_enabled": current_user.get("notifications_enabled", False),
        "min_price": current_user.get("min_price"),
        "max_price": current_user.get("max_price"),
        "min_rooms": current_user.get("min_rooms"),
        "max_rooms": current_user.get("max_rooms"),
    }

@api_router.put("/profile")
async def update_profile(profile: ProfileUpdate, current_user: dict = Depends(get_current_user)):
    update_data = {
        "notifications_enabled": profile.notifications_enabled,
        "min_price": profile.min_price,
        "max_price": profile.max_price,
        "min_rooms": profile.min_rooms,
        "max_rooms": profile.max_rooms,
    }
    if profile.notification_email:
        update_data["notification_email"] = profile.notification_email
    
    await db.users.update_one(
        {"_id": ObjectId(current_user["_id"])},
        {"$set": update_data}
    )
    
    return {"message": "Profile updated", **update_data}

# ============= ADMIN ENDPOINTS =============

@api_router.get("/admin/users")
async def list_users(admin: dict = Depends(get_admin_user)):
    users = await db.users.find({}, {"password_hash": 0}).to_list(1000)
    return [{
        "id": str(u["_id"]),
        "email": u["email"],
        "name": u.get("name"),
        "role": u.get("role", "user"),
        "created_at": u.get("created_at").isoformat() if u.get("created_at") else None
    } for u in users]

@api_router.post("/admin/users")
async def create_user(user_data: UserCreate, admin: dict = Depends(get_admin_user)):
    email = user_data.email.lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    result = await db.users.insert_one({
        "email": email,
        "password_hash": hash_password(user_data.password),
        "name": user_data.name,
        "role": user_data.role,
        "created_at": datetime.now(timezone.utc)
    })
    
    return {
        "id": str(result.inserted_id),
        "email": email,
        "name": user_data.name,
        "role": user_data.role
    }

@api_router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: dict = Depends(get_admin_user)):
    if user_id == admin["_id"]:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    result = await db.users.delete_one({"_id": ObjectId(user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted"}

# Manual URL management (admin)
class ManualUrlAdd(BaseModel):
    url: str

@api_router.get("/admin/manual-urls")
async def list_manual_urls(admin: dict = Depends(get_admin_user)):
    urls = await db.manual_urls.find({}, {"_id": 0}).to_list(1000)
    return urls

@api_router.post("/admin/manual-urls")
async def add_manual_url(data: ManualUrlAdd, admin: dict = Depends(get_admin_user)):
    is_apply = 'tenant.immomio.com/apply/' in data.url or 'tenant.immomio.com/de/apply/' in data.url
    homepage_token = _extract_immomio_homepage_token(data.url)
    if not is_apply and not homepage_token:
        raise HTTPException(
            status_code=400,
            detail=(
                "URL muss tenant.immomio.com/apply/{uuid} oder "
                "homepage.immomio.com/de/properties?token=... sein"
            ),
        )

    existing = await db.manual_urls.find_one({"url": data.url})
    if existing:
        raise HTTPException(status_code=400, detail="URL already added")

    url_type = "homepage_token" if homepage_token else "apply"
    await db.manual_urls.insert_one({
        "url": data.url,
        "type": url_type,
        "added_at": datetime.now(timezone.utc).isoformat()
    })

    apartment_payload = None
    apartments_count = 0
    parse_error = None

    try:
        if homepage_token:
            name = f"Manual:{homepage_token[:8]}"
            apts = await asyncio.to_thread(scrape_immomio_landlord_token, name, homepage_token)
            if not apts:
                parse_error = (
                    "Token gültig, aber aktuell keine Hamburg-Wohnungen verfügbar. "
                    "Neue Wohnungen werden beim nächsten Scan (alle 3 Min) automatisch erkannt."
                )
            else:
                for apt in apts:
                    apt_dict = apt.copy()
                    if isinstance(apt_dict.get('found_at'), datetime):
                        apt_dict['found_at'] = apt_dict['found_at'].isoformat()
                    existing_apt = await db.apartments.find_one({"id": apt_dict["id"]}, {"_id": 0})
                    if not existing_apt:
                        await db.apartments.insert_one(apt_dict)
                        apartments_count += 1
                        try:
                            payload = {k: v for k, v in apt_dict.items() if k != '_id'}
                            await ws_manager.broadcast({"type": "new_apartment", "apartment": payload})
                        except Exception as e:
                            logger.debug(f"WS broadcast (token-url) failed: {e}")
                logger.info(
                    f"[manual-url] Homepage token: {apartments_count} new (total {len(apts)}) from {homepage_token[:16]}..."
                )
        else:
            normalized_url = data.url.replace('/de/apply/', '/apply/')
            apartment = await asyncio.to_thread(parse_immomio_listing, normalized_url, True)
            if apartment:
                apt_dict = apartment.copy()
                if isinstance(apt_dict.get('found_at'), datetime):
                    apt_dict['found_at'] = apt_dict['found_at'].isoformat()

                existing_apt = await db.apartments.find_one({"id": apt_dict["id"]}, {"_id": 0})
                if not existing_apt:
                    await db.apartments.insert_one(apt_dict)
                    apartments_count = 1
                    logger.info(f"[manual-url] New apartment: {apt_dict.get('title')} ({apt_dict['id']})")
                else:
                    update_fields = {}
                    for field in ['price', 'rooms', 'area', 'district', 'address', 'image_url', 'landlord', 'title']:
                        if apt_dict.get(field) is not None and existing_apt.get(field) in (None, ""):
                            update_fields[field] = apt_dict[field]
                    if update_fields:
                        await db.apartments.update_one({"id": apt_dict["id"]}, {"$set": update_fields})

                apartment_payload = {k: v for k, v in apt_dict.items() if k != '_id'}
                try:
                    await ws_manager.broadcast({"type": "new_apartment", "apartment": apartment_payload})
                except Exception as e:
                    logger.debug(f"WS broadcast (manual-url) failed: {e}")
            else:
                parse_error = "Listing konnte nicht geladen werden (möglicherweise abgelaufen oder offline)"
    except Exception as e:
        err_text = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
        parse_error = err_text
        logger.error(f"[manual-url] Parse error for {data.url}: {e}")

    return {
        "message": "URL added",
        "url": data.url,
        "type": url_type,
        "apartment": apartment_payload,
        "apartments_count": apartments_count,
        "parse_error": parse_error,
    }

@api_router.delete("/admin/manual-urls")
async def remove_manual_url(data: ManualUrlAdd, admin: dict = Depends(get_admin_user)):
    result = await db.manual_urls.delete_one({"url": data.url})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="URL not found")
    return {"message": "URL removed"}

# ============= APARTMENT ENDPOINTS (protected) =============

@api_router.get("/")
async def root():
    return {"message": "Hamburg Apartment Scanner API"}

@api_router.get("/apartments")
async def get_apartments(
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rooms: Optional[float] = None,
    max_rooms: Optional[float] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    
    if min_price is not None or max_price is not None:
        query["price"] = {}
        if min_price is not None:
            query["price"]["$gte"] = min_price
        if max_price is not None:
            query["price"]["$lte"] = max_price
    
    if min_rooms is not None or max_rooms is not None:
        query["rooms"] = {}
        if min_rooms is not None:
            query["rooms"]["$gte"] = min_rooms
        if max_rooms is not None:
            query["rooms"]["$lte"] = max_rooms
    
    # "new" = added in last 24 hours, "history" = older than 24 hours, no filter = all
    if status == "new":
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        query["found_at"] = {"$gte": cutoff}
    elif status == "history":
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        query["found_at"] = {"$lt": cutoff}
    
    apartments = await db.apartments.find(query, {"_id": 0}).sort("found_at", -1).to_list(1000)
    return apartments

@api_router.get("/apartments/history")
async def get_apartment_history(current_user: dict = Depends(get_current_user)):
    """Return all apartments older than 24 hours"""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    apartments = await db.apartments.find(
        {"found_at": {"$lt": cutoff}}, {"_id": 0}
    ).sort("found_at", -1).to_list(1000)
    return apartments

@api_router.get("/scan-status")
async def get_scan_status(current_user: dict = Depends(get_current_user)):
    total = await db.apartments.count_documents({})
    # "new" = within last 24h
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    new = await db.apartments.count_documents({"found_at": {"$gte": cutoff}})
    
    return {
        "is_scanning": scanning_state["is_scanning"],
        "last_scan": scanning_state["last_scan"].isoformat() if scanning_state["last_scan"] else None,
        "next_scan": scanning_state["next_scan"].isoformat() if scanning_state["next_scan"] else None,
        "total_apartments": total,
        "new_apartments": new
    }

@api_router.post("/scan-now")
async def trigger_scan(current_user: dict = Depends(get_current_user)):
    if scanning_state["is_scanning"]:
        raise HTTPException(status_code=400, detail="Scan already in progress")
    asyncio.create_task(scan_apartments())
    return {"message": "Scan started"}


@api_router.get("/stats/daily")
async def get_daily_stats(
    days: int = 30,
    current_user: dict = Depends(get_current_user),
):
    """
    Daily apartment counts for the last `days` days, broken down by landlord.
    Returns a list of points: {date: 'YYYY-MM-DD', total: N, byLandlord: {SAGA: 1, ...}}
    Always returns a continuous range (zero-padded for days with no findings).
    """
    days = max(1, min(days, 90))
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    start_iso = start.isoformat()

    # found_at is stored as an ISO string (see scan_apartments). Substring the
    # first 10 chars (YYYY-MM-DD) to bucket by day.
    pipeline = [
        {"$match": {"found_at": {"$gte": start_iso}}},
        {"$group": {
            "_id": {
                "date": {"$substr": ["$found_at", 0, 10]},
                "landlord": {"$ifNull": ["$landlord", "Unbekannt"]},
            },
            "count": {"$sum": 1},
        }},
    ]

    buckets: dict[str, dict] = {}
    async for row in db.apartments.aggregate(pipeline):
        date = row["_id"]["date"]
        landlord = row["_id"]["landlord"]
        b = buckets.setdefault(date, {"total": 0, "byLandlord": {}})
        b["total"] += row["count"]
        b["byLandlord"][landlord] = b["byLandlord"].get(landlord, 0) + row["count"]

    # Continuous range — fill empty days with zeros so the chart x-axis is even
    points = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        info = buckets.get(d, {"total": 0, "byLandlord": {}})
        points.append({"date": d, "total": info["total"], "byLandlord": info["byLandlord"]})

    # Collect set of landlords seen in the window (for chart legend / stacks)
    landlords = sorted({l for p in points for l in p["byLandlord"]})

    return {"days": days, "points": points, "landlords": landlords}

@api_router.post("/apartments/{apartment_id}/mark-seen")
async def mark_apartment_seen(apartment_id: str, current_user: dict = Depends(get_current_user)):
    result = await db.apartments.update_one(
        {"id": apartment_id},
        {"$set": {"status": "seen"}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Apartment not found")
    return {"message": "Apartment marked as seen"}

@api_router.get("/settings")
async def get_settings(current_user: dict = Depends(get_current_user)):
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        return {"email": RECIPIENT_EMAIL}
    return settings

class SettingsModel(BaseModel):
    email: EmailStr

@api_router.post("/settings")
async def save_settings(settings: SettingsModel, current_user: dict = Depends(get_current_user)):
    await db.settings.update_one({}, {"$set": settings.model_dump()}, upsert=True)
    return {"message": "Settings saved"}


# ============= WEB PUSH (PWA) =============

def _apartment_matches_filters(apt: dict, prefs: dict) -> bool:
    """Apply a user's price/rooms filters to an apartment."""
    if prefs.get('min_price') is not None and (apt.get('price') is None or apt['price'] < prefs['min_price']):
        return False
    if prefs.get('max_price') is not None and (apt.get('price') is None or apt['price'] > prefs['max_price']):
        return False
    if prefs.get('min_rooms') is not None and (apt.get('rooms') is None or apt['rooms'] < prefs['min_rooms']):
        return False
    if prefs.get('max_rooms') is not None and (apt.get('rooms') is None or apt['rooms'] > prefs['max_rooms']):
        return False
    return True


def _send_single_push(subscription: dict, payload: dict) -> bool:
    """Send a single Web Push. Returns True if delivered, False if the
    subscription is gone (404/410) and should be deleted by the caller."""
    from pywebpush import webpush, WebPushException
    import json as _json
    try:
        webpush(
            subscription_info=subscription,
            data=_json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_CLAIM_EMAIL},
        )
        return True
    except WebPushException as e:
        # 404 / 410 => subscription expired; caller should remove it.
        status = getattr(getattr(e, 'response', None), 'status_code', None)
        if status in (404, 410):
            return False
        logger.warning(f"Web push delivery failed ({status}): {e}")
        return True  # transient error — keep subscription


async def send_push_notifications_for_new_apartments(new_apartments: List[dict]) -> None:
    """Deliver per-user push notifications respecting profile filters.
    One push per user-batch (groups multiple matching apartments together)."""
    if not VAPID_PRIVATE_KEY or not new_apartments:
        return

    users = await db.users.find({}, {
        "_id": 1, "email": 1,
        "min_price": 1, "max_price": 1, "min_rooms": 1, "max_rooms": 1,
    }).to_list(1000)

    for user in users:
        user_id = str(user['_id'])
        matched = [a for a in new_apartments if _apartment_matches_filters(a, user)]
        if not matched:
            continue

        subs = await db.push_subscriptions.find({"user_id": user_id}).to_list(50)
        if not subs:
            continue

        # Build a single payload. If 1 apartment → show its details; if many
        # → show "N neue Wohnungen in Hamburg" + sample data of the first one.
        if len(matched) == 1:
            apt = matched[0]
            body_parts = []
            if apt.get('price'): body_parts.append(f"€{int(apt['price'])}")
            if apt.get('rooms'): body_parts.append(f"{apt['rooms']} Zi.")
            if apt.get('area'): body_parts.append(f"{int(apt['area'])}m²")
            if apt.get('district') or apt.get('address'):
                body_parts.append(apt.get('district') or apt['address'])
            payload = {
                "title": f"🏠 Neue Wohnung — {apt.get('landlord', '')}",
                "body": (apt.get('title') or 'Wohnung in Hamburg')[:80]
                        + ("\n" + " · ".join(body_parts) if body_parts else ""),
                "icon": apt.get('image_url') or "/icon-192.png",
                "badge": "/icon-72.png",
                "url": apt.get('url') or "/",
                "tag": f"apt-{apt.get('id', '')}",
            }
        else:
            first = matched[0]
            payload = {
                "title": f"🏠 {len(matched)} neue Wohnungen in Hamburg",
                "body": f"{first.get('title','')[:60]}\nund {len(matched)-1} weitere ...",
                "icon": "/icon-192.png",
                "badge": "/icon-72.png",
                "url": "/",
                "tag": "apt-batch",
            }

        # Send to each of the user's devices
        for sub in subs:
            sub_info = {
                "endpoint": sub["endpoint"],
                "keys": sub["keys"],
            }
            ok = await asyncio.to_thread(_send_single_push, sub_info, payload)
            if not ok:
                # Subscription is gone — clean it up
                await db.push_subscriptions.delete_one({"_id": sub["_id"]})
                logger.info(f"Removed expired push subscription for user {user_id}")


@api_router.get("/push/vapid-public-key")
async def get_vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}


class PushSubscriptionPayload(BaseModel):
    endpoint: str
    keys: dict  # {p256dh, auth}


@api_router.post("/push/subscribe")
async def push_subscribe(
    sub: PushSubscriptionPayload,
    current_user: dict = Depends(get_current_user),
):
    """Idempotent: same endpoint replaces previous record for this user."""
    user_id = str(current_user['_id']) if '_id' in current_user else current_user.get('id')
    doc = {
        "user_id": user_id,
        "endpoint": sub.endpoint,
        "keys": sub.keys,
        "created_at": datetime.now(timezone.utc),
    }
    await db.push_subscriptions.update_one(
        {"user_id": user_id, "endpoint": sub.endpoint},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True}


@api_router.post("/push/unsubscribe")
async def push_unsubscribe(
    sub: PushSubscriptionPayload,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user['_id']) if '_id' in current_user else current_user.get('id')
    await db.push_subscriptions.delete_one({"user_id": user_id, "endpoint": sub.endpoint})
    return {"ok": True}


@api_router.post("/push/test")
async def push_test(current_user: dict = Depends(get_current_user)):
    """Trigger a test push to all of the calling user's devices."""
    user_id = str(current_user['_id']) if '_id' in current_user else current_user.get('id')
    subs = await db.push_subscriptions.find({"user_id": user_id}).to_list(50)
    if not subs:
        raise HTTPException(status_code=404, detail="No push subscriptions found for this user")
    payload = {
        "title": "🏠 Hamburg Scanner — Test",
        "body": "Push-Benachrichtigungen funktionieren!",
        "icon": "/icon-192.png",
        "badge": "/icon-72.png",
        "url": "/",
        "tag": "test-push",
    }
    sent = 0
    for sub in subs:
        sub_info = {"endpoint": sub["endpoint"], "keys": sub["keys"]}
        ok = await asyncio.to_thread(_send_single_push, sub_info, payload)
        if ok:
            sent += 1
        else:
            await db.push_subscriptions.delete_one({"_id": sub["_id"]})
    return {"ok": True, "sent": sent}


# ============= WEBSOCKET (live updates) =============

class _ConnectionManager:
    """Manages all active WebSocket clients and broadcasts apartment events."""
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, payload: dict) -> None:
        dead: List[WebSocket] = []
        for ws in self.active:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = _ConnectionManager()


@app.websocket("/api/ws/apartments")
async def apartments_ws(websocket: WebSocket):
    """Live channel: emits {type:'new_apartment', apartment:{...}} when a
    brand-new listing is inserted, plus {type:'scan_finished', ...} after
    every scan. No auth required (read-only, public listing data)."""
    await ws_manager.connect(websocket)
    try:
        # Send a hello so the client can confirm the connection is live
        await websocket.send_json({"type": "hello", "ts": datetime.now(timezone.utc).isoformat()})
        while True:
            # Keep the socket alive; we ignore any client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)

# ============= APP SETUP =============

app.include_router(auth_router)
app.include_router(api_router)

# CORS — allow multiple origins from CORS_ORIGINS env (comma-separated),
# plus all Vercel preview deployments of this project via regex.
_cors_raw = os.environ.get("CORS_ORIGINS") or os.environ.get(
    "FRONTEND_URL", "https://hamburg-listings.preview.emergentagent.com"
)
allowed_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    # Match every Vercel preview/production URL (incl. hashed previews)
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Scheduler
scheduler = AsyncIOScheduler()

async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@hamburg-scanner.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc)
        })
        logger.info(f"Admin user created: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )
        logger.info(f"Admin password updated: {admin_email}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting apartment scanner service...")
    
    # Create indexes
    try:
        await db.users.create_index("email", unique=True)
        await db.apartments.create_index("id", unique=True)
    except Exception as e:
        logger.error(f"Index error: {e}")
    
    # Seed admin
    await seed_admin()
    
    # Schedule scan every 3 minutes
    scheduler.add_job(scan_apartments, 'interval', minutes=3, id='apartment_scanner')
    scheduler.start()
    
    scanning_state["next_scan"] = datetime.now(timezone.utc) + timedelta(minutes=3)
    
    # Run initial scan in background
    asyncio.create_task(scan_apartments())
    
    logger.info("Scheduler started - scanning every 3 minutes")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    client.close()
    logger.info("Scheduler stopped")
