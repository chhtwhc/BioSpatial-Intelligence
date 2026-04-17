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
STATIC_HABITAT_CACHE = {}

# --- API 端點 ---

@app.get("/habitats", response_model=schemas.FeatureCollection)
def get_habitats(
    bbox: str = Query(None, description="範圍查詢框限制 (格式: min_lon,min_lat,max_lon,max_lat)"),
    source: str = Query("sentinel", description="影像來源篩選 (例如: sentinel 或 nlsc)"),
    db: Session = Depends(database.get_db)
):
    global STATIC_HABITAT_CACHE
    
    if not bbox and source in STATIC_HABITAT_CACHE:
        return STATIC_HABITAT_CACHE[source]

    # 🚀 效能優化核心：
    # 1. 避免 Select 整個 ORM 物件，只撈取需要的欄位
    # 2. ST_Simplify(geom, 0.00001): 將多邊形頂點精簡 (0.00001度大約1公尺誤差，能大幅減少傳輸量)
    # 3. ST_AsGeoJSON: 讓底層資料庫直接幫我們轉好 JSON 字串，省去 Python Shapely 轉換的時間
    query = db.query(
        models.Habitat.id,
        models.Habitat.habitat_type,
        models.Habitat.source,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm'),
        func.ST_AsGeoJSON(func.ST_Simplify(models.Habitat.geom, 0.00001)).label('geojson_str')
    ).filter(models.Habitat.source == source)

    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(','))
            envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            query = query.filter(func.ST_Intersects(models.Habitat.geom, envelope))
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox 格式錯誤")

    results = query.all()
    
    features = []
    # 現在迴圈內不需要跑沈重的 Shapely 轉換了
    for row in results:
        features.append({
            "type": "Feature",
            "properties": {
                "id": row.id,
                "habitat_type": row.habitat_type,
                "area_sqm": round(row.area_sqm, 2),
                "source": row.source
            },
            "geometry": json.loads(row.geojson_str) # 直接將字串載入為 JSON
        })
        
    response_data = {"type": "FeatureCollection", "features": features}
    
    if not bbox:
        STATIC_HABITAT_CACHE[source] = response_data
        
    return response_data

@app.post("/habitats/intersect", response_model=schemas.FeatureCollection)
def post_habitats_intersect(
    query_data: schemas.RegionQuery = Body(...),
    db: Session = Depends(database.get_db)
):
    """接收前端傳送的 EPSG:4326 GeoJSON 多邊形，回傳交集的棲地資料。"""
    geojson_str = json.dumps(query_data.geometry)
    
    # 🚀 同步實作效能優化：
    # 1. 使用 ST_AsGeoJSON 直接在資料庫端轉換，避開 Python 的 Shapely 轉換開銷。
    # 2. 使用 ST_Simplify 減少頂點數量，大幅降低傳輸量。
    query = db.query(
        models.Habitat.id,
        models.Habitat.habitat_type,
        models.Habitat.source,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm'),
        func.ST_AsGeoJSON(func.ST_Simplify(models.Habitat.geom, 0.00001)).label('geojson_str')
    ).filter(
        func.ST_Intersects(
            models.Habitat.geom, 
            func.ST_SetSRID(func.ST_GeomFromGeoJSON(geojson_str), 4326)
        )
    )

    results = query.all()
    
    features = []
    for row in results:
        features.append({
            "type": "Feature",
            "properties": {
                "id": row.id,
                "habitat_type": row.habitat_type,
                "area_sqm": round(row.area_sqm, 2),
                "source": row.source
            },
            "geometry": json.loads(row.geojson_str)
        })
        
    return {"type": "FeatureCollection", "features": features}

@app.get("/")
def read_root():
    return {"message": "Welcome to BioSpatial Intelligence Logic Tier"}