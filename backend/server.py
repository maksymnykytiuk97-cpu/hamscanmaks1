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


def scrape_saga_hamburg() -> List[str]:
    """Scrape SAGA Hamburg website for immomio apply URLs using Playwright"""
    immomio_urls = set()
    
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
                # SAGA listing page
                page.goto('https://www.saga.hamburg/immobiliensuche?Kategorie=APARTMENT', timeout=30000, wait_until='domcontentloaded')
                page.wait_for_timeout(8000)  # Wait for JS challenge + content load
                
                # Get all links from the page
                html = page.content()
                
                # Find immomio links directly
                immomio_links = re.findall(
                    r'https?://tenant\.immomio\.com/(?:de/)?apply/[a-f0-9-]+',
                    html
                )
                immomio_urls.update(immomio_links)
                
                # Find all property detail pages on SAGA
                property_links = re.findall(
                    r'href="(/immobiliensuche/immobilien-details/[^"]+)"',
                    html
                )
                
                # Visit each property page to find immomio link (limit to first 20 for performance)
                for prop_path in property_links[:20]:
                    try:
                        prop_url = f'https://www.saga.hamburg{prop_path}'
                        page.goto(prop_url, timeout=20000, wait_until='domcontentloaded')
                        page.wait_for_timeout(3000)
                        prop_html = page.content()
                        prop_immomio = re.findall(
                            r'https?://tenant\.immomio\.com/(?:de/)?apply/[a-f0-9-]+',
                            prop_html
                        )
                        immomio_urls.update(prop_immomio)
                    except Exception as e:
                        logger.debug(f"Error fetching SAGA property page: {e}")
                        continue
                
            except Exception as e:
                logger.error(f"Error in SAGA Playwright scrape: {str(e)}")
            finally:
                browser.close()
        
        logger.info(f"SAGA scraper found {len(immomio_urls)} immomio URLs")
    
    except Exception as e:
        logger.error(f"Error in SAGA scraper: {str(e)}")
    
    return list(immomio_urls)


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
    """Main scraping function - combines SAGA + Google search"""
    apartments = []
    
    try:
        # Collect URLs from multiple sources
        all_urls = set()
        
        # Source 1: SAGA Hamburg
        saga_urls = await asyncio.to_thread(scrape_saga_hamburg)
        all_urls.update(saga_urls)
        
        # Source 2: Google/DuckDuckGo search
        search_urls = await asyncio.to_thread(search_google_for_immomio)
        all_urls.update(search_urls)
        
        # Source 3: Manually added URLs from database
        manual_urls = await db.manual_urls.find({}, {"_id": 0}).to_list(100)
        for item in manual_urls:
            all_urls.add(item['url'])
        
        logger.info(f"Total URLs to process: {len(all_urls)}")
        
        # Parse each unique URL
        for url in all_urls:
            # Normalize URL (remove /de/ prefix variant)
            normalized_url = url.replace('/de/apply/', '/apply/')
            
            apartment = await asyncio.to_thread(parse_immomio_listing, normalized_url)
            
            if not apartment:
                continue
            
            # Check Hamburg in address, title, or page (already parsed)
            is_hamburg = (
                (apartment.get('address') and 'Hamburg' in apartment['address']) or
                ('Hamburg' in apartment.get('title', ''))
            )
            
            # If URL is manually added by admin, always include it
            is_manual = any(item['url'].replace('/de/apply/', '/apply/') == normalized_url for item in manual_urls)
            
            if is_hamburg or is_manual:
                apartments.append(apartment)
        
        logger.info(f"Successfully parsed {len(apartments)} Hamburg apartments")
    
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
        
        # Send email
        if new_apartments and resend.api_key:
            try:
                # Get recipients (admin email + all user emails)
                settings = await db.settings.find_one({}, {"_id": 0})
                recipient = settings.get('email', RECIPIENT_EMAIL) if settings else RECIPIENT_EMAIL
                
                html_content = f"<h2>🏠 {len(new_apartments)} neue Wohnungen in Hamburg gefunden!</h2>"
                html_content += "<ul>"
                for apt in new_apartments:
                    html_content += f"<li><strong>{apt['title']}</strong><br>"
                    if apt.get('price'):
                        html_content += f"Preis: €{apt['price']:.2f}<br>"
                    if apt.get('rooms'):
                        html_content += f"Zimmer: {apt['rooms']}<br>"
                    if apt.get('area'):
                        html_content += f"Fläche: {apt['area']}m²<br>"
                    if apt.get('address'):
                        html_content += f"Adresse: {apt['address']}<br>"
                    html_content += f"<a href='{apt['url']}'>Zur Anzeige</a></li><br>"
                html_content += "</ul>"
                
                params = {
                    "from": SENDER_EMAIL,
                    "to": [recipient],
                    "subject": f"🏠 {len(new_apartments)} neue Wohnungen in Hamburg",
                    "html": html_content
                }
                
                await asyncio.to_thread(resend.Emails.send, params)
                logger.info(f"Email sent to {recipient}")
            except Exception as e:
                logger.error(f"Failed to send email: {str(e)}")
        
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
        "role": current_user.get("role", "user")
    }

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
    
    if status:
        query["status"] = status
    
    apartments = await db.apartments.find(query, {"_id": 0}).sort("found_at", -1).to_list(1000)
    return apartments

@api_router.get("/apartments/history")
async def get_apartment_history(current_user: dict = Depends(get_current_user)):
    apartments = await db.apartments.find({}, {"_id": 0}).sort("found_at", -1).to_list(1000)
    return apartments

@api_router.get("/scan-status")
async def get_scan_status(current_user: dict = Depends(get_current_user)):
    total = await db.apartments.count_documents({})
    new = await db.apartments.count_documents({"status": "new"})
    
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
