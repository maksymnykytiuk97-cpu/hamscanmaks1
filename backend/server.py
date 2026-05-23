from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import asyncio
import logging
from pathlib import Path
from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from datetime import datetime, timezone
import resend
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import hashlib
import random

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Resend setup
resend.api_key = os.environ.get('RESEND_API_KEY', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', 'onboarding@resend.dev')
RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'maximnikityk@ukr.net')

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Models
class Apartment(BaseModel):
    id: str
    title: str
    price: Optional[float] = None
    rooms: Optional[int] = None
    area: Optional[float] = None
    district: Optional[str] = None
    url: str
    image_url: Optional[str] = None
    found_at: datetime
    status: str = "new"  # new, seen

class ScanLog(BaseModel):
    timestamp: datetime
    found_count: int
    new_count: int
    status: str
    message: Optional[str] = None

class Settings(BaseModel):
    email: EmailStr
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_rooms: Optional[int] = None
    max_rooms: Optional[int] = None

class ScanStatus(BaseModel):
    is_scanning: bool
    last_scan: Optional[datetime] = None
    next_scan: Optional[datetime] = None
    total_apartments: int
    new_apartments: int

# Global state
scanning_state = {
    "is_scanning": False,
    "last_scan": None,
    "next_scan": None
}

# Scraper function
async def scrape_immomio_hamburg():
    """Scrape apartment listings from immomio.com for Hamburg"""
    apartments = []
    
    try:
        # For MVP, we'll generate mock data
        # In production, you would implement actual scraping logic here
        # The site immomio.com requires authentication, so this would need
        # proper credentials or API access
        
        districts = ["Eimsbüttel", "Altona", "St. Pauli", "Winterhude", "Harburg", "Bergedorf", "Wandsbek"]
        
        # Generate some mock listings with variation to simulate new finds
        num_listings = random.randint(3, 6)
        
        mock_listings = []
        for i in range(num_listings):
            district = random.choice(districts)
            rooms = random.randint(1, 4)
            base_price = rooms * 500 + random.randint(100, 500)
            area = rooms * 30 + random.randint(10, 40)
            
            listing = {
                "title": f"{rooms}-Zimmer Wohnung in {district}",
                "price": float(base_price),
                "rooms": rooms,
                "area": float(area),
                "district": district,
                "url": f"https://tenant.immomio.com/listing/{random.randint(1000, 9999)}",
                "image_url": random.choice([
                    "https://images.pexels.com/photos/32178051/pexels-photo-32178051.png?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940",
                    "https://images.unsplash.com/photo-1628592102751-ba83b0314276?crop=entropy&cs=srgb&fm=jpg&q=85"
                ])
            }
            mock_listings.append(listing)
        
        for listing in mock_listings:
            # Create unique ID based on URL
            listing_id = hashlib.md5(listing['url'].encode()).hexdigest()
            
            apartment = {
                "id": listing_id,
                "title": listing['title'],
                "price": listing['price'],
                "rooms": listing['rooms'],
                "area": listing['area'],
                "district": listing['district'],
                "url": listing['url'],
                "image_url": listing['image_url'],
                "found_at": datetime.now(timezone.utc),
                "status": "new"
            }
            apartments.append(apartment)
            
    except Exception as e:
        logger.error(f"Error scraping immomio: {str(e)}")
    
    return apartments

# Scanner task
async def scan_apartments():
    """Scan for new apartments and send email if found"""
    if scanning_state["is_scanning"]:
        logger.info("Scan already in progress, skipping...")
        return
    
    scanning_state["is_scanning"] = True
    logger.info("Starting apartment scan...")
    
    try:
        # Scrape apartments
        apartments = await scrape_immomio_hamburg()
        
        new_apartments = []
        total_found = len(apartments)
        
        # Check each apartment
        for apt in apartments:
            # Check if apartment already exists
            existing = await db.apartments.find_one({"id": apt["id"]}, {"_id": 0})
            
            if not existing:
                # New apartment found
                apt_dict = apt.copy()
                apt_dict['found_at'] = apt_dict['found_at'].isoformat()
                await db.apartments.insert_one(apt_dict)
                new_apartments.append(apt)
                logger.info(f"New apartment found: {apt['title']}")
            else:
                # Update status to seen
                await db.apartments.update_one(
                    {"id": apt["id"]},
                    {"$set": {"status": "seen"}}
                )
        
        # Log scan
        scan_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "found_count": total_found,
            "new_count": len(new_apartments),
            "status": "success",
            "message": f"Found {total_found} apartments, {len(new_apartments)} new"
        }
        await db.scan_logs.insert_one(scan_log)
        
        # Send email if new apartments found
        if new_apartments and resend.api_key:
            try:
                html_content = "<h2>Neue Wohnungen in Hamburg gefunden!</h2>"
                html_content += f"<p>{len(new_apartments)} neue Wohnungen wurden gefunden:</p>"
                html_content += "<ul>"
                
                for apt in new_apartments:
                    html_content += f"<li>"
                    html_content += f"<strong>{apt['title']}</strong><br>"
                    html_content += f"Preis: €{apt['price']:.2f} | Zimmer: {apt['rooms']} | Fläche: {apt['area']}m²<br>"
                    html_content += f"Bezirk: {apt['district']}<br>"
                    html_content += f"<a href='{apt['url']}'>Zur Anzeige</a>"
                    html_content += f"</li><br>"
                
                html_content += "</ul>"
                
                params = {
                    "from": SENDER_EMAIL,
                    "to": [RECIPIENT_EMAIL],
                    "subject": f"🏠 {len(new_apartments)} neue Wohnungen in Hamburg",
                    "html": html_content
                }
                
                await asyncio.to_thread(resend.Emails.send, params)
                logger.info(f"Email sent to {RECIPIENT_EMAIL}")
                
            except Exception as e:
                logger.error(f"Failed to send email: {str(e)}")
        
        scanning_state["last_scan"] = datetime.now(timezone.utc)
        
    except Exception as e:
        logger.error(f"Error during scan: {str(e)}")
        scan_log = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "found_count": 0,
            "new_count": 0,
            "status": "error",
            "message": str(e)
        }
        await db.scan_logs.insert_one(scan_log)
    
    finally:
        scanning_state["is_scanning"] = False

# API Routes
@api_router.get("/")
async def root():
    return {"message": "Hamburg Apartment Scanner API"}

@api_router.get("/apartments")
async def get_apartments(
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_rooms: Optional[int] = None,
    max_rooms: Optional[int] = None,
    status: Optional[str] = None
):
    """Get apartments with optional filters"""
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
async def get_apartment_history():
    """Get all apartment history"""
    apartments = await db.apartments.find({}, {"_id": 0}).sort("found_at", -1).to_list(1000)
    return apartments

@api_router.get("/scan-status")
async def get_scan_status():
    """Get current scan status"""
    total = await db.apartments.count_documents({})
    new = await db.apartments.count_documents({"status": "new"})
    
    return {
        "is_scanning": scanning_state["is_scanning"],
        "last_scan": scanning_state["last_scan"],
        "next_scan": scanning_state["next_scan"],
        "total_apartments": total,
        "new_apartments": new
    }

@api_router.post("/scan-now")
async def trigger_scan():
    """Manually trigger a scan"""
    if scanning_state["is_scanning"]:
        raise HTTPException(status_code=400, detail="Scan already in progress")
    
    # Run scan in background
    asyncio.create_task(scan_apartments())
    
    return {"message": "Scan started"}

@api_router.get("/scan-logs")
async def get_scan_logs():
    """Get recent scan logs"""
    logs = await db.scan_logs.find({}, {"_id": 0}).sort("timestamp", -1).limit(50).to_list(50)
    return logs

@api_router.get("/settings")
async def get_settings():
    """Get user settings"""
    settings = await db.settings.find_one({}, {"_id": 0})
    if not settings:
        return {
            "email": RECIPIENT_EMAIL,
            "min_price": None,
            "max_price": None,
            "min_rooms": None,
            "max_rooms": None
        }
    return settings

@api_router.post("/settings")
async def save_settings(settings: Settings):
    """Save user settings"""
    settings_dict = settings.model_dump()
    await db.settings.update_one(
        {},
        {"$set": settings_dict},
        upsert=True
    )
    return {"message": "Settings saved", "settings": settings_dict}

@api_router.post("/apartments/{apartment_id}/mark-seen")
async def mark_apartment_seen(apartment_id: str):
    """Mark an apartment as seen"""
    result = await db.apartments.update_one(
        {"id": apartment_id},
        {"$set": {"status": "seen"}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Apartment not found")
    
    return {"message": "Apartment marked as seen"}

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Scheduler
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on startup"""
    logger.info("Starting apartment scanner service...")
    
    # Schedule scan every 3 minutes
    scheduler.add_job(scan_apartments, 'interval', minutes=3, id='apartment_scanner')
    scheduler.start()
    
    # Set next scan time
    scanning_state["next_scan"] = datetime.now(timezone.utc)
    
    # Run initial scan
    asyncio.create_task(scan_apartments())
    
    logger.info("Scheduler started - scanning every 3 minutes")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    scheduler.shutdown()
    client.close()
    logger.info("Scheduler stopped")
