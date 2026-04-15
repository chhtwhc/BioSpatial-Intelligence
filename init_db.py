from sqlalchemy import text
from api.database import engine
from api.models import Base

def initialize():
    try:
        print("[*] 正在連線資料庫...")
        with engine.begin() as conn:
            # 確保 PostGIS 擴充功能已啟用
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            print("[+] PostGIS 擴充功能已就緒。")

        print("[*] 正在依照模型定義建立資料表...")
        # 這行會檢查 models.py，如果 habitats 表不存在，會自動建立
        Base.metadata.create_all(bind=engine)
        
        print("[+] 成功！資料表 'habitats' 已重建完畢。")
    except Exception as e:
        print(f"[-] 初始化失敗: {e}")

if __name__ == "__main__":
    initialize()