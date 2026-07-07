import os
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
import logging

from backend.up42_client import UP42Client
from backend.vector_parser import parse_vector_data

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("up42-system")

app = FastAPI(title="UP42 Catalog & Vector Matcher")

# Enable CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global UP42 Client instance
up42_client = UP42Client()

# Models
class Credentials(BaseModel):
    email: str
    password: str

class SearchRequest(BaseModel):
    email: Optional[str] = None
    password: Optional[str] = None
    geometry: Dict[str, Any]  # GeoJSON geometry (Polygon, MultiPolygon, etc.)
    collections: List[str]
    datetime: Optional[str] = None  # Format: "2025-01-01T00:00:00Z/2025-01-31T23:59:59Z"
    cloud_cover: Optional[int] = Field(default=None, ge=0, le=100)
    limit: Optional[int] = Field(default=100, ge=1, le=500)
    events: Optional[List[Dict[str, Any]]] = None  # List of event dicts with name, start, and end keys

class WktParseRequest(BaseModel):
    wkt: str
    filename: Optional[str] = "input.wkt"

@app.post("/api/auth/test")
async def test_auth(creds: Credentials):
    logger.info(f"Testing authentication for email: {creds.email}")
    try:
        # Create a temporary client to avoid modifying the main one if authentication fails
        temp_client = UP42Client()
        temp_client.set_credentials(creds.email, creds.password)
        success = temp_client.test_connection()
        if success:
            # Save credentials globally on success
            up42_client.set_credentials(creds.email, creds.password)
            return {"success": True, "message": "Successfully authenticated with UP42."}
        else:
            raise HTTPException(status_code=401, detail="Authentication failed. Check your email and password.")
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/api/collections")
async def get_collections():
    """
    Retrieves all available collections from UP42.
    It will map collections and identify which ones support searching.
    """
    try:
        # Fetch collections (handles public or authenticated access)
        raw_collections = up42_client.get_collections()
        
        processed_collections = []
        for item in raw_collections:
            integrations = item.get("integrations", [])
            # Only include collections that support catalog search
            search_available = "SEARCH_AVAILABLE" in integrations
            
            # Extract host name
            host_name = None
            for provider in item.get("providers", []):
                if "HOST" in provider.get("roles", []):
                    host_name = provider.get("name")
                    break
            
            # Fallback if no explicit host role, check if there's any provider name
            if not host_name and item.get("providers"):
                host_name = item["providers"][0].get("name")

            # Determine product type (OPTICAL, SAR, ELEVATION)
            product_type = item.get("metadata", {}).get("productType")
            if not product_type:
                name_lower = item.get("name", "").lower()
                if "dem" in name_lower or "elevation" in name_lower or "terrain" in name_lower:
                    product_type = "ELEVATION"
                elif "sar" in name_lower or "radar" in name_lower or "capella" in name_lower or "iceye" in name_lower or "umbra" in name_lower:
                    product_type = "SAR"
                else:
                    product_type = "OPTICAL"
            else:
                product_type = product_type.upper()

            processed_collections.append({
                "name": item.get("name"),
                "title": item.get("title"),
                "type": item.get("type"),
                "host": host_name,
                "search_available": search_available,
                "product_type": product_type,
                "description": item.get("description", ""),
                "integrations": integrations
            })
            
        return processed_collections
    except Exception as e:
        logger.error(f"Error fetching collections: {e}")
        # Return fallback mock/static list of collections if UP42 is unreachable or offline
        return [
            {"name": "worldview-legion-hd", "title": "WorldView Legion HD15", "type": "ARCHIVE", "host": "vantor-hd", "search_available": True, "product_type": "OPTICAL"},
            {"name": "worldview-legion", "title": "WorldView Legion", "type": "ARCHIVE", "host": "vantor", "search_available": True, "product_type": "OPTICAL"},
            {"name": "worldview-3", "title": "WorldView-3", "type": "ARCHIVE", "host": "vantor", "search_available": True, "product_type": "OPTICAL"},
            {"name": "worldview-2", "title": "WorldView-2", "type": "ARCHIVE", "host": "vantor", "search_available": True, "product_type": "OPTICAL"},
            {"name": "worldview-1", "title": "WorldView-1", "type": "ARCHIVE", "host": "vantor", "search_available": True, "product_type": "OPTICAL"},
            {"name": "worlddem-neo-dtm", "title": "WorldDEM Neo DTM", "type": "ARCHIVE", "host": "airbus-elevation", "search_available": True, "product_type": "ELEVATION"},
            {"name": "worlddem-neo", "title": "WorldDEM Neo DSM", "type": "ARCHIVE", "host": "airbus-elevation", "search_available": True, "product_type": "ELEVATION"},
            {"name": "worlddem-4ortho", "title": "WorldDEM4Ortho", "type": "ARCHIVE", "host": "airbus-elevation", "search_available": True, "product_type": "ELEVATION"}
        ]

@app.post("/api/parse-vector")
async def parse_vector_file(file: UploadFile = File(...)):
    """
    Receives an uploaded vector file (GeoJSON, KML, ZIP Shapefile, or WKT TXT) and returns GeoJSON.
    """
    logger.info(f"Parsing uploaded file: {file.filename}")
    try:
        content = await file.read()
        geojson_data = parse_vector_data(content, file.filename)
        return geojson_data
    except Exception as e:
        logger.error(f"Failed to parse vector file: {e}")
        raise HTTPException(status_code=400, detail=f"Error parsing file: {str(e)}")

@app.post("/api/parse-wkt")
async def parse_wkt_text(body: WktParseRequest):
    """
    Receives a raw WKT string and parses it to GeoJSON.
    """
    try:
        geojson_data = parse_vector_data(body.wkt.encode('utf-8'), body.filename)
        return geojson_data
    except Exception as e:
        logger.error(f"Failed to parse WKT: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/search")
async def search_catalog(req: SearchRequest):
    """
    Performs search query on the selected collections across their respective data hosts.
    Aggregates the STAC results and returns them as a unified FeatureCollection.
    """
    # 1. Handle credentials setup
    if req.email and req.password:
        up42_client.set_credentials(req.email, req.password)
    
    if not up42_client.email or not up42_client.password:
        raise HTTPException(
            status_code=400,
            detail="Authentication credentials are required. Please log in first or include credentials in search."
        )

    # 2. Get list of collections to map each selected collection to its host name
    try:
        available_cols = await get_collections()
        col_to_host = {c["name"]: c["host"] for c in available_cols if c["host"]}
    except Exception as e:
        logger.warning(f"Could not fetch fresh collections list for mapping: {e}. Using default mappings.")
        # Default fallback mappings
        col_to_host = {
            "worldview-legion-hd": "vantor-hd",
            "worldview-legion": "vantor",
            "worldview-3": "vantor",
            "worldview-2": "vantor",
            "worldview-1": "vantor",
            "worlddem-neo-dtm": "airbus-elevation",
            "worlddem-neo": "airbus-elevation",
            "worlddem-4ortho": "airbus-elevation"
        }

    # 3. Group selected collections by host
    host_to_collections = {}
    for col in req.collections:
        host = col_to_host.get(col)
        if not host:
            logger.warning(f"No host mapped for collection '{col}'. Skipping search for this collection.")
            continue
        if host not in host_to_collections:
            host_to_collections[host] = []
        host_to_collections[host].append(col)

    if not host_to_collections:
        raise HTTPException(
            status_code=400,
            detail="None of the selected collections could be mapped to an active search host."
        )

    # 4. Perform searches for each host
    aggregated_features = []
    errors = {}

    # Define queries (either list of events or a single fallback query)
    queries = []
    if req.events:
        for evt in req.events:
            queries.append({
                "name": evt.get("name", "Event"),
                "datetime": f"{evt.get('start')}T00:00:00Z/{evt.get('end')}T23:59:59Z"
            })
    else:
        queries.append({
            "name": "Custom Search",
            "datetime": req.datetime
        })

    for q in queries:
        event_name = q["name"]
        dt_str = q["datetime"]
        
        for host, cols in host_to_collections.items():
            try:
                logger.info(f"Querying host '{host}' for event '{event_name}' ({dt_str})")
                results = up42_client.search_catalog(
                    host_name=host,
                    collections=cols,
                    geometry=req.geometry,
                    datetime_str=dt_str,
                    limit=req.limit,
                    cloud_cover=req.cloud_cover
                )

                # Standard STAC responses have features array
                features = results.get("features", [])
                for feature in features:
                    # Inject catalog host details, collection, and matching event name
                    feature["properties"]["_host"] = host
                    feature["properties"]["event_name"] = event_name
                    if "collection" not in feature["properties"] and feature.get("collection"):
                        feature["properties"]["collection"] = feature.get("collection")
                    
                    aggregated_features.append(feature)
                    
                if "error" in results:
                    errors[f"{host} ({event_name})"] = results["error"]

            except Exception as e:
                logger.error(f"Error querying host {host} for event {event_name}: {e}")
                errors[f"{host} ({event_name})"] = str(e)

    # 5. Return aggregated FeatureCollection (sliced to requested limit)
    sliced_features = aggregated_features[:req.limit] if req.limit else aggregated_features
    return {
        "type": "FeatureCollection",
        "features": sliced_features,
        "search_summary": {
            "total_features": len(sliced_features),
            "unfiltered_total": len(aggregated_features),
            "errors": errors if errors else None
        }
    }

# Serve frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")

@app.get("/")
async def read_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend files not found. Place index.html inside the frontend folder."}
