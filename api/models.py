"""
BioSpatial-Intelligence - 資料模型定義層 (Data Models)
檔案位置: api/models.py

模組用途：
1. 定義 SQLAlchemy ORM 模型，將 Python 類別映射至 PostGIS 資料表。
2. 配置 GeoAlchemy2 空間擴充欄位，支援幾何物件（Geometry）的儲存與運算。
3. 規範系統內的空間參考系統（SRID: 4326），確保全球定位數據的一致性。

維護提示：
若未來需要增加「植生指數 (NDVI)」或「偵測信心度 (Confidence Score)」等屬性，需在此類別中新增 Column 定義。
"""

from sqlalchemy import Column, Integer, String, Float
from geoalchemy2 import Geometry
from .database import Base

class Habitat(Base):
    """
    棲地紀錄資料表 (habitats)
    儲存經由 AI 模型 (SAM/RF) 辨識後的幾何輪廓與分類屬性。
    """
    __tablename__ = "habitats"

    # --- 基礎屬性欄位 ---
    
    # 唯一識別碼：主鍵，自動遞增
    # 在執行 TRUNCATE ... RESTART IDENTITY 時，此欄位會歸零
    id = Column(Integer, primary_key=True, index=True) 
    
    # 棲地類型名稱 (例如: '次生林', '草生地', '水體/河流')
    # 使用 String(50) 限制長度以優化索引效能
    habitat_type = Column(String(50), nullable=False)
    
    # 資料來源標籤
    # 用於區分此紀錄是由 'sentinel' (衛星) 或 'nlsc' (航照) 產出
    source = Column(String(50), nullable=False, default="sentinel")
    
    # --- 核心空間幾何欄位 ---
    
    # 幾何物件儲存：
    # 1. geometry_type='MULTIPOLYGON'：強制限定為多邊形集，符合生態區塊的拓樸特性。
    # 2. srid=4326：指定座標系統為 WGS84 (GPS 經緯度)，這是本系統對外的資料交換標準。
    # 
    # 註：雖然儲存為 4326，但進行面積運算時，後端會動態轉投影至 EPSG:3826 (TWD97)。
    geom = Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))

    def __repr__(self):
        """物件字串表示，便於後端日誌調試"""
        return f"<Habitat(id={self.id}, type='{self.habitat_type}', source='{self.source}')>"