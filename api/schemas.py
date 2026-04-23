"""
BioSpatial-Intelligence - 資料驗證與轉換層 (Schemas/DTOs)
檔案位置: api/schemas.py

模組用途：
1. 定義 Pydantic 模型 (BaseModel)，作為 API 請求 (Input) 與響應 (Output) 的資料傳輸物件 (DTO)。
2. 實作強型別幾何校驗，確保所有傳入的空間數據均符合標準 GeoJSON 格式與 EPSG:4326 範圍。
3. 分離資料庫模型 (Models) 與對外接口格式，提供彈性的數據封裝能力。

維護提示：
若未來需要增加自定義的分析參數（如分類信心度閾值），應在此處的 RegionQuery 類別中新增欄位。
"""

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------
# 輸出 Schema (Response Models)
# 定義 API 傳回給前端的 JSON 結構
# ---------------------------------------------------------

class Feature(BaseModel):
    """
    單一地理要素模型
    完全符合 GeoJSON 'Feature' 規範，包含屬性 (properties) 與幾何 (geometry)。
    """
    type: str = "Feature"
    properties: dict  # 包含 id, habitat_type, area_sqm, source 等資訊
    geometry: dict    # 儲存轉換為 GeoJSON 格式的幾何座標

class FeatureCollection(BaseModel):
    """
    地理要素集合模型
    用於批量回傳多個棲地多邊形，是 Leaflet 前端渲染的主流格式。
    """
    type: str = "FeatureCollection"
    features: list[Feature]

# ---------------------------------------------------------
# 輸入 Schema (Request Models)
# 定義前端發送到後端的資料規範與強制驗證
# ---------------------------------------------------------

class RegionQuery(BaseModel):
    """
    分析請求模型
    使用者在前端地圖框選 ROI (分析範圍) 時，會以此格式傳遞座標。
    """
    type: str = "Feature"
    geometry: dict

    @field_validator('geometry')
    @classmethod
    def validate_epsg4326(cls, v):
        """
        空間資料完整性守門員：
        強制檢查幾何類型是否合法，並排除錯誤的座標參考系統（例如誤傳 TWD97 座標至此）。
        """
        geom_type = v.get("type")
        
        # 1. 幾何類型檢查：本系統僅處理多邊形資料
        if geom_type not in ["Polygon", "MultiPolygon"]:
            raise ValueError("幾何類型不支援，必須為 'Polygon' 或 'MultiPolygon'")
        
        try:
            # 2. 深度定位座標：根據 GeoJSON 階層取得第一個頂點的經緯度
            if geom_type == "Polygon":
                # Polygon 座標格式: [[[lon, lat], ...]]
                first_coord = v["coordinates"][0][0]
            else:
                # MultiPolygon 座標格式: [[[[lon, lat], ...]]]
                first_coord = v["coordinates"][0][0][0]
                
            lon, lat = first_coord[0], first_coord[1]
            
            # 3. 數值合理性檢查：
            # 確保經度在 [-180, 180] 且緯度在 [-90, 90] 之間。
            # 這是防止「投影污染」的重要手段，避免將數十萬公尺的 TWD97 數值當作經緯度處理。
            if not (-180 <= lon <= 180) or not (-90 <= lat <= 90):
                raise ValueError(f"座標數值異常 (經度: {lon}, 緯度: {lat})。請確認資料是否為 EPSG:4326 (WGS84) 投影。")
                
        except (KeyError, IndexError, TypeError):
            # 幾何結構毀損或格式不符合標準 GeoJSON
            raise ValueError("GeoJSON 幾何結構解析失敗，請檢查座標巢狀層級是否正確。")
            
        return v