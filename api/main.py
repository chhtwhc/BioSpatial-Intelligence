from fastapi import FastAPI, Depends, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, text # 確保匯入了 text
from geoalchemy2.shape import to_shape
import json

# 導入內部模組
from . import models, database, schemas
from .config import ALLOWED_ORIGINS
# 匯入管線函式用於分析
from data.main_pipeline import run_integration_pipeline

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
    bbox: str = Query(None),
    source: str = Query("sentinel"),
    db: Session = Depends(database.get_db)
):
    global STATIC_HABITAT_CACHE
    if not bbox and source in STATIC_HABITAT_CACHE:
        return STATIC_HABITAT_CACHE[source]

    query = db.query(
        models.Habitat.id,
        models.Habitat.habitat_type,
        models.Habitat.source,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm'),
        func.ST_AsGeoJSON(func.ST_Simplify(models.Habitat.geom, 0.00001)).label('geojson_str')
    ).filter(
        models.Habitat.source == source,
        models.Habitat.geom.isnot(None) # 🌟 核心修正 1：過濾掉資料庫中的空值
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
    for row in results:
        # 🌟 核心修正 2：防禦性檢查，確保只有有效的 GeoJSON 字串才會被解析
        if row.geojson_str:
            try:
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
            except (json.JSONDecodeError, TypeError):
                continue # 跳過毀損的幾何資料
        
    return {"type": "FeatureCollection", "features": features}

@app.post("/analyze")
def start_analysis(
    source: str = Query("sentinel"),
    roi: schemas.RegionQuery = Body(...),
    db: Session = Depends(database.get_db)
):
    roi_geojson = json.dumps(roi.geometry)
    try:
        # 空間精確清理
        sql_delete = text("""
            DELETE FROM habitats 
            WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:roi_json), 4326))
        """)
        db.execute(sql_delete, {"roi_json": roi_geojson})
        db.commit()
    except Exception as e:
        db.rollback()

    coords = roi.geometry['coordinates'][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    dynamic_bbox = [min(lons), min(lats), max(lons), max(lats)]
    
    success, message = run_integration_pipeline(bbox=dynamic_bbox, source=source)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {"status": "success", "message": message, "bbox": dynamic_bbox}

# --- 全域清空接口 ---
@app.delete("/habitats/all")
def clear_all_habitats(db: Session = Depends(database.get_db)):
    """清空資料庫中所有的棲地紀錄並重設畫布。"""
    try:
        # 使用 TRUNCATE 強制重設表格並重新計算 ID 序列
        db.execute(text("TRUNCATE TABLE habitats RESTART IDENTITY CASCADE;"))
        db.commit()
        
        # 同步清空後端記憶體快取
        global STATIC_HABITAT_CACHE
        STATIC_HABITAT_CACHE = {}
        
        return {"status": "success", "message": "資料庫已清空，畫布重置成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清空失敗: {str(e)}")

@app.get("/")
def read_root():
    return {"message": "Welcome to BioSpatial Intelligence Logic Tier"}