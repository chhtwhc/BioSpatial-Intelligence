"""
BioSpatial-Intelligence - 邏輯層核心路由 (Logic Tier)
檔案位置: api/main.py

模組用途：
1. 擔任 FastAPI 服務的總入口，負責接收前端 Leaflet 傳遞的 GeoJSON 請求。
2. 處理 PostGIS 空間資料庫的 CRUD 操作，包含即時動態投影轉換 (EPSG:4326 <-> EPSG:3826)。
3. 調度 data/main_pipeline.py 的 ETL 分析管線，觸發衛星影像抓取與 AI 模型推論。

維護提示：
本模組涉及所有對外的 API 接口。若未來新增其他分析模型或切換資料來源，需優先於此處擴充路由與參數檢核機制。
"""

from fastapi import FastAPI, Depends, Query, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, text
from geoalchemy2.shape import to_shape
import json

from . import models, database, schemas
from .config import ALLOWED_ORIGINS
from data.main_pipeline import run_integration_pipeline

app = FastAPI(title="BioSpatial Intelligence API")

# ---------------------------------------------------------
# 中介軟體與全域狀態配置
# ---------------------------------------------------------

# 配置 CORS，確保前端介面 (如 localhost:5500) 能順利發送 API 請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 靜態快取：暫存無需頻繁查詢資料庫的基準圖資狀態，降低 DB 負載
STATIC_HABITAT_CACHE = {}

# ---------------------------------------------------------
# API 端點定義
# ---------------------------------------------------------

@app.get("/habitats", response_model=schemas.FeatureCollection)
def get_habitats(
    bbox: str = Query(None),
    source: str = Query("sentinel"),
    db: Session = Depends(database.get_db)
):
    """
    獲取指定範圍內的棲地幾何圖資 (GeoJSON)。
    包含動態面積計算與幾何簡化邏輯，以優化前端 WebGIS 渲染效能。
    """
    global STATIC_HABITAT_CACHE
    
    # 若未指定 BBOX 且快取命中，直接回傳全區快取資料
    if not bbox and source in STATIC_HABITAT_CACHE:
        return STATIC_HABITAT_CACHE[source]

    # 建構資料庫查詢邏輯：
    # 1. ST_Area + ST_Transform(3826)：將 WGS84(4326) 即時轉為 TWD97(3826) 以確保台灣區域法定面積(平方公尺)計算之精確度。
    # 2. ST_Simplify：利用 Douglas-Peucker 演算法剔除微小節點，減少傳輸與瀏覽器渲染負擔。
    query = db.query(
        models.Habitat.id,
        models.Habitat.habitat_type,
        models.Habitat.source,
        func.ST_Area(func.ST_Transform(models.Habitat.geom, 3826)).label('area_sqm'),
        func.ST_AsGeoJSON(func.ST_Simplify(models.Habitat.geom, 0.00001)).label('geojson_str')
    ).filter(
        models.Habitat.source == source,
        models.Habitat.geom.isnot(None) # 防呆：排除異常空值
    )

    # 空間過濾器：若有傳入 bbox，建立 ST_MakeEnvelope 以進行 ST_Intersects 交集篩選
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = map(float, bbox.split(','))
            envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
            query = query.filter(func.ST_Intersects(models.Habitat.geom, envelope))
        except ValueError:
            raise HTTPException(status_code=400, detail="bbox 參數格式錯誤，預期為 'min_lon,min_lat,max_lon,max_lat'")

    results = query.all()
    features = []
    
    # 封裝為標準 GeoJSON FeatureCollection 格式
    for row in results:
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
                continue # 若遇毀損的幾何字串則跳過，避免整支 API 崩潰
        
    return {"type": "FeatureCollection", "features": features}


@app.post("/analyze")
def start_analysis(
    source: str = Query("sentinel"),
    roi: schemas.RegionQuery = Body(...),
    db: Session = Depends(database.get_db)
):
    """
    觸發 AI 分析管線。
    接收前端框選的 ROI (Region of Interest)，清空該區域舊資料後，交由管線重新分析。
    """
    roi_geojson = json.dumps(roi.geometry)
    try:
        # 空間精準清理：利用 ST_Intersects 刪除與使用者新選取範圍重疊的舊有棲地，避免資料疊加污染
        sql_delete = text("""
            DELETE FROM habitats 
            WHERE ST_Intersects(geom, ST_SetSRID(ST_GeomFromGeoJSON(:roi_json), 4326))
        """)
        db.execute(sql_delete, {"roi_json": roi_geojson})
        db.commit()
    except Exception as e:
        db.rollback()

    # 從前端傳入的多邊形座標中，萃取出外接矩形 (Bounding Box)
    coords = roi.geometry['coordinates'][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    dynamic_bbox = [min(lons), min(lats), max(lons), max(lats)]
    
    # 調度外部 ETL 分析管線 (整合影像抓取、SAM 分割與 Random Forest 分類)
    success, message = run_integration_pipeline(bbox=dynamic_bbox, source=source)
    if not success:
        raise HTTPException(status_code=500, detail=message)
    
    return {"status": "success", "message": message, "bbox": dynamic_bbox}


@app.delete("/habitats/all")
def clear_all_habitats(db: Session = Depends(database.get_db)):
    """
    全域資料庫重置接口。
    強制清空資料庫與記憶體快取，供系統維護或重新初始化時使用。
    """
    try:
        # 使用 TRUNCATE 取代 DELETE，同時重設主鍵的 IDENTITY 序列 (ID 回歸 1)，並執行級聯刪除
        db.execute(text("TRUNCATE TABLE habitats RESTART IDENTITY CASCADE;"))
        db.commit()
        
        # 同步清除後端記憶體狀態
        global STATIC_HABITAT_CACHE
        STATIC_HABITAT_CACHE = {}
        
        return {"status": "success", "message": "資料庫已清空，畫布重置成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清空失敗: {str(e)}")


@app.get("/")
def read_root():
    """健康檢查端點"""
    return {"message": "Welcome to BioSpatial Intelligence Logic Tier"}