from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, HTTPException, Request, Response, Depends
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

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Resend setup
resend.api_key = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'maximnikityk@ukr.net')

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

def parse_immomio_listing(url: str) -> Optional[dict]:
    """Parse a single immomio.com/apply/{uuid} page using Playwright"""
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='de-DE'
            )
            page = context.new_page()
            
            try:
                page.goto(url, timeout=30000, wait_until='domcontentloaded')
                page.wait_for_timeout(6000)
                
                html = page.content()
                text = page.evaluate('document.body.innerText')
                
                # Get image URLs
                img_srcs = page.evaluate('''
                    Array.from(document.querySelectorAll('img')).map(img => img.src)
                ''')
            finally:
                browser.close()
        
        # Extract UUID from URL
        uuid_match = re.search(r'/apply/([a-f0-9-]+)', url)
        if not uuid_match:
            return None
        listing_id = uuid_match.group(1)
        
        # Check if listing is still active (no error page)
        if 'Diese Seite existiert nicht' in text or 'Anzeige wurde entfernt' in text or len(text) < 200:
            logger.info(f"Listing not active: {url}")
            return None
        
        # Extract title from h1
        h1_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        title = h1_match.group(1).strip() if h1_match else "Wohnung in Hamburg"
        
        # Extract address - German pattern with PLZ
        address = None
        # Get all matches and clean each
        addr_matches = re.findall(r'([^\n]+?\d+[a-zA-Z]?,\s*\d{5}\s+Hamburg(?:,\s*Deutschland)?)', text)
        if addr_matches:
            cleaned = []
            for m in addr_matches:
                # If contains newline, take only the part after last newline
                if '\n' in m:
                    m = m.split('\n')[-1].strip()
                # Skip if too long (likely contains title)
                if len(m) < 120:
                    cleaned.append(m.strip())
            if cleaned:
                address = min(cleaned, key=len)
        
        # Extract district
        district = None
        dist_match = re.search(r'in\s+([A-ZÄÖÜ][a-zäöüß\-]+?)(?:\s+zu\s+vermieten|\s*$)', title)
        if dist_match:
            district = dist_match.group(1).strip()
        if not district:
            dist_match = re.search(r'Hamburg-([A-ZÄÖÜ][a-zäöüß\-]+)', title)
            if dist_match:
                district = dist_match.group(1)
        
        # Extract price - "Gesamtmiete (in €)" followed by value
        price = None
        gesamt_match = re.search(r'Gesamtmiete\s*\(in\s*€\)\s*\n?\s*([\d.]+,\d{2})\s*€', text)
        if gesamt_match:
            price_str = gesamt_match.group(1).replace('.', '').replace(',', '.')
            try:
                price = float(price_str)
            except ValueError:
                pass
        # Fallback: "X,XX € mtl"
        if price is None:
            mtl_match = re.search(r'([\d.]+,\d{2})\s*€\s*mtl', text)
            if mtl_match:
                price_str = mtl_match.group(1).replace('.', '').replace(',', '.')
                try:
                    price = float(price_str)
                except ValueError:
                    pass
        
        # Extract area - "XX,XX m²" or "XX,XX m\n2" (immomio splits the ²)
        area = None
        # First try with space + newline 2 (immomio specific)
        wohn_match = re.search(r'([\d]+(?:,\d+)?)\s*m\s*\n\s*2\b', text)
        if wohn_match:
            try:
                area = float(wohn_match.group(1).replace(',', '.'))
            except ValueError:
                pass
        if area is None:
            area_match = re.search(r'([\d]+(?:,\d+)?)\s*m²', text)
            if area_match:
                try:
                    area = float(area_match.group(1).replace(',', '.'))
                except ValueError:
                    pass
        
        # Extract rooms
        rooms = None
        # First try "X-Zimmer" pattern in title
        title_rooms = re.search(r'(\d+)(\s*1/2)?\s*[-\s]?Zimmer', title)
        if title_rooms:
            base = float(title_rooms.group(1))
            if title_rooms.group(2):
                base += 0.5
            rooms = base
        
        if rooms is None:
            # Try "X ganzes" / "X halbes" pattern (immomio standard)
            ganze_match = re.search(r'(\d+)\s+ganz', text)
            halbes_match = re.search(r'(\d+)\s+halbe', text)
            if ganze_match:
                rooms = float(ganze_match.group(1))
                if halbes_match:
                    rooms += float(halbes_match.group(1)) * 0.5
        
        if rooms is None:
            # Try "Anzahl Zimmer X"
            anzahl_match = re.search(r'Anzahl\s+Zimmer\s*\n?\s*([\d,]+)', text)
            if anzahl_match:
                try:
                    rooms = float(anzahl_match.group(1).replace(',', '.'))
                except ValueError:
                    pass
        
        # Extract landlord
        landlord = None
        landlord_match = re.search(r'Angebot\s+von:?\s*\n\s*([^\n]+?)(?:\n|$)', text)
        if landlord_match:
            landlord = landlord_match.group(1).strip()[:150]
        
        # Extract main image - largest non-logo immomio image
        image_url = None
        for src in img_srcs:
            if 'immomio-prod-img-storage' in src and 'logo' not in src.lower() and '.svg' not in src.lower():
                image_url = src
                break
        
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
            "status": "new"
        }
    
    except Exception as e:
        logger.error(f"Error parsing {url}: {str(e)}")
        return None


def _scrape_landlord_pages(start_url: str, detail_link_pattern: str, base_url: str, source_name: str, max_pages: int = 30) -> List[str]:
    """Generic Playwright scraper - finds immomio URLs by visiting detail pages of a landlord site"""
    import time
    immomio_urls = set()
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-features=IsolateOrigins,site-per-process',
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
            # Anti-detection: hide webdriver flag
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'languages', { get: () => ['de-DE', 'de', 'en'] });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                window.chrome = { runtime: {}, app: {} };
            """)
            page = context.new_page()
            
            try:
                page.goto(start_url, timeout=60000, wait_until='networkidle')
                
                # Wait for any captcha to resolve (Friendly Captcha solves automatically in ~2-10 seconds)
                for _ in range(15):
                    time.sleep(2)
                    title = page.title()
                    if 'Bot check' not in title and 'Sicherheitspr' not in title:
                        break
                
                # Extra wait for content to load via AJAX
                page.wait_for_timeout(5000)
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


# Immomio homepage tokens for landlords (extracted from their websites)
IMMOMIO_TOKENS = {
    'BGFG': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoxNTY2MDQwMzUsImlkIjoxNzA2MDA0NjIsImNyZWF0ZWQiOjE2NDIxNjYwNDY2Mzh9.1QlkdnxWyyJMcRS1JubN1EkDrHPRaqfASe6oUJq7ptU',
    'Hamburger Wohnen': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoxNDI3MzI5MjksImlkIjoxODcwMDEzMjAsImNyZWF0ZWQiOjE2NTc0NzYyMzg4Nzl9.C1vwdfjJ27h7-HWIvGKBrsgWGcj-8-ArzkiOKoBpSgs',
    'BDS Hamburg': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoyODYxOTA4ODMsImlkIjoyOTIxMTgyMzgsImNyZWF0ZWQiOjE2NjY1OTQ0NzE5OTJ9.l-IorHm_QkfJf7tidzsCoW9x9xeIk01uO8BbuzmJ6Bg',
    'VHW Hamburg': 'eyJhbGciOiJIUzI1NiJ9.eyJjdXN0b21lcklkIjoyNTQxMzQ1MDYsImlkIjoyNzI4MDEwODUsImNyZWF0ZWQiOjE2NjE5NDY5ODY1MDF9.fo3dJ4iNYF825tbg1E5C6q0mXbtbePO1LO3S_3_SEhM',
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
            if ptype in ('GARAGE', 'PARKING', 'GEWERBE', 'OFFICE', 'STORAGE'):
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
    """SAGA Hamburg - largest landlord (still tries detail pages, captcha may block)"""
    return _scrape_landlord_pages(
        start_url='https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT&Stadt=Hamburg',
        detail_link_pattern=r'href="(/immobiliensuche/immobilien-details/[^"]+)"',
        base_url='https://www.saga.hamburg',
        source_name='SAGA',
        max_pages=30
    )


def scrape_vonovia_hamburg() -> List[dict]:
    """Vonovia Hamburg - DIRECT scraping (not via immomio).
    Returns full apartment dicts with vonovia.de URLs."""
    import time
    apartments = []
    
    try:
        from playwright.sync_api import sync_playwright
        
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
                        
                        # Image
                        image_url = None
                        img_match = re.search(r'src="(https://cdn\.expose\.vonovia\.de/[a-f0-9-]+\.(?:jpg|jpeg|png|webp)[^"]*)"', dhtml)
                        if img_match:
                            image_url = img_match.group(1).split('&amp;')[0]
                        
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
    """Walddörfer direct scraping (not via immomio)"""
    import time
    apartments = []
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
                locale='de-DE'
            )
            page = context.new_page()
            
            try:
                page.goto('https://www.walddoerfer.de/wohnungsangebote/aktuelle-angebote/', timeout=30000, wait_until='networkidle')
                time.sleep(5)
                html = page.content()
                
                # Find apartment cards - try various patterns
                detail_paths = list(set(re.findall(r'href="(/wohnungsangebote/[a-z0-9\-]+/)"', html)))
                detail_paths = [d for d in detail_paths if 'aktuelle-angebote' not in d]
                
                logger.info(f"Walddoerfer: found {len(detail_paths)} apartments")
                
                for path in detail_paths[:20]:
                    try:
                        detail_url = f'https://www.walddoerfer.de{path}'
                        page.goto(detail_url, timeout=15000, wait_until='domcontentloaded')
                        time.sleep(2)
                        
                        text = page.evaluate('document.body.innerText')
                        dhtml = page.content()
                        
                        title_match = re.search(r'<h1[^>]*>([^<]+)</h1>', dhtml)
                        title = title_match.group(1).strip() if title_match else 'Walddörfer Wohnung'
                        
                        # Hamburg check
                        if 'Hamburg' not in text and 'Hamburg' not in title:
                            continue
                        
                        addr_match = re.search(r'([\w\.\-äöüÄÖÜß\s]+\d+[a-zA-Z]?\s*,?\s*\d{5}\s+[\w\-äöüÄÖÜß]+)', text)
                        address = addr_match.group(1).strip() if addr_match else None
                        
                        price_match = re.search(r'([\d.]+,\d{2})\s*€', text)
                        price = None
                        if price_match:
                            try:
                                price = float(price_match.group(1).replace('.', '').replace(',', '.'))
                            except ValueError:
                                pass
                        
                        area_match = re.search(r'([\d]+(?:,\d+)?)\s*m²', text)
                        area = None
                        if area_match:
                            try:
                                area = float(area_match.group(1).replace(',', '.'))
                            except ValueError:
                                pass
                        
                        rooms = None
                        t_rooms = re.search(r'(\d+(?:[,.]\d+)?)\s*[-\s]?Zimmer', title + ' ' + text[:500])
                        if t_rooms:
                            try:
                                rooms = float(t_rooms.group(1).replace(',', '.'))
                            except ValueError:
                                pass
                        
                        image_url = None
                        img_match = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp))"', dhtml)
                        if img_match:
                            image_url = img_match.group(1)
                        
                        listing_id = f"walddoerfer-{path.strip('/').replace('/', '-')}"
                        
                        apartments.append({
                            "id": listing_id,
                            "title": title[:200],
                            "price": price,
                            "rooms": rooms,
                            "area": area,
                            "district": None,
                            "address": address,
                            "url": detail_url,
                            "image_url": image_url,
                            "landlord": "Walddörfer",
                            "found_at": datetime.now(timezone.utc),
                            "status": "new"
                        })
                    except Exception as e:
                        logger.debug(f"Walddoerfer detail error: {e}")
                        continue
            except Exception as e:
                logger.error(f"Walddoerfer main error: {e}")
            finally:
                browser.close()
        
        logger.info(f"Walddörfer: parsed {len(apartments)} apartments")
    except Exception as e:
        logger.error(f"Walddörfer failed: {e}")
    
    return apartments


def scrape_walddoerfer() -> List[str]:
    """DEPRECATED - kept for compatibility, now returns empty"""
    return []


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
        
        # === STEP 3: SAGA via Playwright (immomio URLs only) ===
        all_urls = set()
        try:
            saga_urls = await asyncio.to_thread(scrape_saga_hamburg)
            all_urls.update(saga_urls)
        except Exception as e:
            logger.error(f"SAGA scraper failed: {e}")
        
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
        
        # === STEP 4: Manual URLs from database ===
        manual_urls = await db.manual_urls.find({}, {"_id": 0}).to_list(100)
        for item in manual_urls:
            all_urls.add(item['url'])
        
        logger.info(f"Playwright/manual URLs to process: {len(all_urls)}")
        
        # Parse each unique URL via Playwright (only ones not already from GraphQL)
        existing_ids = {a['id'] for a in apartments}
        for url in all_urls:
            normalized_url = url.replace('/de/apply/', '/apply/')
            uuid_match = re.search(r'/apply/([a-f0-9-]+)', normalized_url)
            if uuid_match and uuid_match.group(1) in existing_ids:
                continue  # Already have it from GraphQL
            
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
            is_manual = any(item['url'].replace('/de/apply/', '/apply/') == normalized_url for item in manual_urls)
            
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
        
        scanning_state["last_scan"] = datetime.now(timezone.utc)
        scanning_state["next_scan"] = datetime.now(timezone.utc) + timedelta(minutes=3)
    
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
    if 'tenant.immomio.com/apply/' not in data.url and 'tenant.immomio.com/de/apply/' not in data.url:
        raise HTTPException(status_code=400, detail="URL must be from tenant.immomio.com/apply/")
    
    # Check duplicates
    existing = await db.manual_urls.find_one({"url": data.url})
    if existing:
        raise HTTPException(status_code=400, detail="URL already added")
    
    await db.manual_urls.insert_one({
        "url": data.url,
        "added_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {"message": "URL added", "url": data.url}

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

# ============= APP SETUP =============

app.include_router(auth_router)
app.include_router(api_router)

# CORS - allow specific frontend origin with credentials
frontend_url = os.environ.get("FRONTEND_URL", "https://hamburg-listings.preview.emergentagent.com")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
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
