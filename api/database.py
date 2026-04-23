"""
BioSpatial-Intelligence - 資料庫連線管理層 (Database Engine & Session)
檔案位置: api/database.py

模組用途：
1. 實例化 SQLAlchemy 資料庫引擎 (Engine)，作為 Python 程式與 PostGIS 通訊的底層橋樑。
2. 定義 SessionLocal 工廠類別，用於產生與資料庫互動的對話實例。
3. 提供 FastAPI 依賴注入專用的 get_db 函式，嚴格控制資料庫連線的生命週期。

維護提示：
若未來系統併發量增加，需在此處的 create_engine 中加入連線池配置（如 pool_size, max_overflow）。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import SQLALCHEMY_DATABASE_URL

# 1. 建立資料庫引擎 (Engine)
# 此處會讀取 config.py 中建構好的 PostgreSQL/PostGIS 連線字串。
# Engine 是底層連線池的持有者，負責實際的網路通訊與 SQL 翻譯。
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# 2. 建立 SessionLocal 工廠
# sessionmaker 會產生一個 Session 類別。
# autocommit=False: 確保我們必須顯式呼叫 db.commit() 才會寫入，增加事務安全性。
# autoflush=False: 避免在查詢時自動將未提交的變動推送到資料庫。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 3. 建立宣告式基類 (Base)
# 所有的 models.py 類別都必須繼承自此 Base，以便 SQLAlchemy 進行 ORM 映射追蹤。
Base = declarative_base()

# ---------------------------------------------------------
# FastAPI 依賴注入函式 (Dependency Injection)
# ---------------------------------------------------------

def get_db():
    """
    資料庫 Session 生成器。
    
    運作機制：
    1. 當 API 收到請求時，實例化一個 db Session。
    2. 使用 yield 將 Session 交給請求處理函式 (例如 main.py 中的路由)。
    3. 核心關鍵：不論請求成功或失敗，最後的 finally 區塊保證會執行 db.close()。
    
    重要性：
    這能確保每條資料庫連線在任務完成後都會回到連線池，防止因忘記關閉連線而導致資料庫連線數爆滿 (Connection Limit)。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()