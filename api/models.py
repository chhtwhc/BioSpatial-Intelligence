from sqlalchemy import Column, Integer, String, Float
from geoalchemy2 import Geometry
from .database import Base

class Habitat(Base):
    __tablename__ = "habitats"

    # 資料表的主鍵
    # 雖然 database_manager 沒明寫 id，但 SQLAlchemy 需要一個 primary_key
    # 通常 Pandas 寫入時如果有 index 或自動生成序列，這裡就可以對應到
    id = Column(Integer, primary_key=True, index=True) 
    
    # 對應棲地類型 (如: '次生林', '草生地')
    habitat_type = Column(String(50), nullable=False)
    
    # 紀錄資料來源，例如 "sentinel" 或 "nlsc"
    source = Column(String(50), nullable=False, default="sentinel")
    
    # 核心空間欄位：對應 PostGIS 的 MultiPolygon，且 SRID 設為 4326
    geom = Column(Geometry(geometry_type='MULTIPOLYGON', srid=4326))