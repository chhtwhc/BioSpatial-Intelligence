from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 替換為你 PostGIS 的實際連線資訊
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:Crazypig12345@localhost:5432/postgres"

# 建立資料庫引擎
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 建立 SessionLocal 類別，為每個 API 請求提供獨立的資料庫對話
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency: 確保 API 請求結束時自動關閉連線
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()