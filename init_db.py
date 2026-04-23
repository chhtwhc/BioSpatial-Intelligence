"""
BioSpatial-Intelligence - 資料庫初始化與遷移腳本 (Database Initialization)
檔案位置: init_db.py

模組用途：
1. 作為系統部署時的首次啟動腳本，負責建立與 PostgreSQL 實體的連線。
2. 自動執行原生 SQL 指令，為資料庫啟用 PostGIS 空間擴充功能。
3. 透過 SQLAlchemy 的 Metadata 機制，自動掃描並建立系統所需的所有資料表結構 (Schema)。

維護提示：
此腳本具備「冪等性 (Idempotent)」，意即重複執行不會覆蓋或損毀現有已存在的資料表。
但請注意，若未來您在 models.py 中「修改」了現有欄位 (而非新增表)，此腳本不會自動執行資料庫遷移 (Migration)。屆時建議導入 Alembic 等遷移工具進行進階管理。
"""

from sqlalchemy import text
from api.database import engine
from api.models import Base

def initialize():
    """
    執行資料庫初始化流程。
    確保資料庫具備空間運算能力，並建構 ORM 所需的實體表。
    """
    try:
        print("[*] 正在連線資料庫...")
        
        # ---------------------------------------------------------
        # 步驟 1: 啟用 PostGIS 空間引擎
        # ---------------------------------------------------------
        # 使用 engine.begin() 建立一個具備自動提交/回滾能力的事務區塊 (Transaction)
        with engine.begin() as conn:
            # 🌟 核心關鍵：CREATE EXTENSION IF NOT EXISTS postgis
            # 這是整個系統能進行 ST_Area, ST_Transform, ST_Intersects 等空間運算的先決條件。
            # IF NOT EXISTS 確保了若擴充已啟用，指令不會報錯中斷。
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            print("[+] PostGIS 空間擴充功能已就緒。")

        # ---------------------------------------------------------
        # 步驟 2: 建立實體資料表
        # ---------------------------------------------------------
        print("[*] 正在依照模型定義建立資料表...")
        
        # Base.metadata.create_all 會自動讀取繼承自 Base 的所有類別 (如 api/models.py 中的 Habitat)
        # 並將其翻譯為 CREATE TABLE 指令。若資料表已存在，則會安全跳過。
        Base.metadata.create_all(bind=engine)
        
        print("[+] 成功！資料表 'habitats' 已重建或驗證完畢。")
        
    except Exception as e:
        print(f"[-] 初始化失敗，請檢查 .env 的連線設定或確認資料庫伺服器是否運行中: {e}")

# 提供直接執行的進入點
# 開發者在終端機輸入 `python init_db.py` 即可觸發初始化
if __name__ == "__main__":
    initialize()