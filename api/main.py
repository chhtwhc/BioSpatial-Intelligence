from fastapi import FastAPI, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from geoalchemy2.shape import to_shape
import json

from . import models, database

# 建立 FastAPI 應用程式實例
app = FastAPI(title="BioSpatial Intelligence API")

# --- 1. 定義資料交換格式 (Data Contract) ---
class Feature(BaseModel):
    type: str = "Feature"
    properties: dict
    geometry: dict

class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[Feature]

# --- 2. API 端點 ---

@app.get("/habitats", response_model=FeatureCollection)
def get_habitats(
    bbox: str = Query(None, description="範圍查詢框限制 (格式: min_lon,min_lat,max_lon,max_lat)"),
    db: Session = Depends(database.get_db)
):
    """
    取得棲地資料，支援 Bounding Box 空間過濾。
    空間欄位維持 EPSG:4326，面積透過 EPSG:3826 即時計算。
    """
    # 建立基礎查詢：包含實體與面積計算
    query = db.query(
        models.Habitat,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm')
    )

    # 實作空間範圍查詢邏輯 (Bounding Box)
    if bbox:
        try:
            # 解析傳入的 bbox 字串
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(','))
            
            # 使用 ST_MakeEnvelope 建立邊界框幾何 (需指定 SRID 4326)
            envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            
            # 使用 ST_Intersects 過濾出與邊界框相交的多邊形
            query = query.filter(func.ST_Intersects(models.Habitat.geom, envelope))
        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="bbox 格式錯誤，請使用 'min_lon,min_lat,max_lon,max_lat' 格式輸入浮點數。"
            )

    # 執行查詢
    results = query.all()
    
    features = []
    for habitat_obj, area_sqm in results:
        shapely_geom = to_shape(habitat_obj.geom)
        geom_dict = json.loads(json.dumps(shapely_geom.__geo_interface__))
        
        feature = {
            "type": "Feature",
            "properties": {
                "id": habitat_obj.id,
                "habitat_type": habitat_obj.habitat_type,
                "area_sqm": round(area_sqm, 2)
            },
            "geometry": geom_dict
        }
        features.append(feature)
        
    return {"type": "FeatureCollection", "features": features}

@app.get("/")
def read_root():
    return {"message": "Welcome to BioSpatial Intelligence Logic Tier"}