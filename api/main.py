from fastapi import FastAPI, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, field_validator
from geoalchemy2.shape import to_shape
import json

from . import models, database

app = FastAPI(title="BioSpatial Intelligence API")

# --- 1. 定義資料交換格式 (Data Contract) ---

# 輸出 Schema
class Feature(BaseModel):
    type: str = "Feature"
    properties: dict
    geometry: dict

class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[Feature]

# 輸入 Schema：強制檢驗傳入的空間資料格式
class RegionQuery(BaseModel):
    type: str = "Feature"
    geometry: dict

    @field_validator('geometry')
    @classmethod
    def validate_epsg4326(cls, v):
        """強制檢查：確保傳入的座標系統符合 EPSG:4326 的經緯度合理範圍"""
        geom_type = v.get("type")
        if geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValueError("幾何類型必須為 Polygon 或 MultiPolygon")
        
        # 簡易防呆：檢查第一組座標的經度是否落在合理範圍 (-180 到 180)
        # 若傳入 EPSG:3826 (如 X: 215000, Y: 2670000)，此處將直接阻擋
        try:
            if geom_type == "Polygon":
                first_coord = v["coordinates"][0][0]
            else:
                first_coord = v["coordinates"][0][0][0]
                
            lon, lat = first_coord[0], first_coord[1]
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                raise ValueError(f"座標數值異常 (經度: {lon}, 緯度: {lat})，請確認是否為 EPSG:4326 投影")
        except (KeyError, IndexError, TypeError):
            raise ValueError("GeoJSON 座標結構解析失敗")
            
        return v

# --- 快取機制配置 ---
# 針對無參數的靜態查詢建立記憶體快取
STATIC_HABITAT_CACHE = None

# --- 2. API 端點 ---

@app.get("/habitats", response_model=FeatureCollection)
def get_habitats(
    bbox: str = Query(None, description="範圍查詢框限制 (格式: min_lon,min_lat,max_lon,max_lat)"),
    db: Session = Depends(database.get_db)
):
    global STATIC_HABITAT_CACHE
    
    # 若為全域查詢且快取已存在，直接命中快取回傳
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
    
    # 寫入快取
    if not bbox:
        STATIC_HABITAT_CACHE = response_data
        
    return response_data

@app.post("/habitats/intersect", response_model=FeatureCollection)
def post_habitats_intersect(
    query_data: RegionQuery = Body(...),
    db: Session = Depends(database.get_db)
):
    """
    接收前端傳送的 EPSG:4326 GeoJSON 多邊形，回傳交集的棲地資料。
    """
    # 將 dict 轉為 JSON 字串，交由 PostGIS ST_GeomFromGeoJSON 處理
    geojson_str = json.dumps(query_data.geometry)
    
    # 建立交集查詢
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