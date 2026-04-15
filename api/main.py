from fastapi import FastAPI, Depends, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from geoalchemy2.shape import to_shape
import json

# 導入內部模組
from . import models, database, schemas
from .config import ALLOWED_ORIGINS

app = FastAPI(title="BioSpatial Intelligence API")

# --- CORS 配置 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 快取機制配置 ---
STATIC_HABITAT_CACHE = None

# --- API 端點 ---

@app.get("/habitats", response_model=schemas.FeatureCollection)
def get_habitats(
    bbox: str = Query(None, description="範圍查詢框限制 (格式: min_lon,min_lat,max_lon,max_lat)"),
    db: Session = Depends(database.get_db)
):
    global STATIC_HABITAT_CACHE
    
    if not bbox and STATIC_HABITAT_CACHE is not None:
        return STATIC_HABITAT_CACHE

    query = db.query(
        models.Habitat,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm')
    )

    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(','))
            envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            query = query.filter(func.ST_Intersects(models.Habitat.geom, envelope))
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox 格式錯誤")

    results = query.all()
    
    features = []
    for habitat_obj, area_sqm in results:
        shapely_geom = to_shape(habitat_obj.geom)
        geom_dict = json.loads(json.dumps(shapely_geom.__geo_interface__))
        
        features.append({
            "type": "Feature",
            "properties": {
                "id": habitat_obj.id,
                "habitat_type": habitat_obj.habitat_type,
                "area_sqm": round(area_sqm, 2)
            },
            "geometry": geom_dict
        })
        
    response_data = {"type": "FeatureCollection", "features": features}
    
    if not bbox:
        STATIC_HABITAT_CACHE = response_data
        
    return response_data

@app.post("/habitats/intersect", response_model=schemas.FeatureCollection)
def post_habitats_intersect(
    query_data: schemas.RegionQuery = Body(...),
    db: Session = Depends(database.get_db)
):
    """接收前端傳送的 EPSG:4326 GeoJSON 多邊形，回傳交集的棲地資料。"""
    geojson_str = json.dumps(query_data.geometry)
    
    query = db.query(
        models.Habitat,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm')
    ).filter(
        func.ST_Intersects(
            models.Habitat.geom, 
            func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson_str), 4326)
        )
    )

    results = query.all()
    
    features = []
    for habitat_obj, area_sqm in results:
        shapely_geom = to_shape(habitat_obj.geom)
        features.append({
            "type": "Feature",
            "properties": {
                "id": habitat_obj.id,
                "habitat_type": habitat_obj.habitat_type,
                "area_sqm": round(area_sqm, 2)
            },
            "geometry": json.loads(json.dumps(shapely_geom.__geo_interface__))
        })
        
    return {"type": "FeatureCollection", "features": features}

@app.get("/")
def read_root():
    return {"message": "Welcome to BioSpatial Intelligence Logic Tier"}