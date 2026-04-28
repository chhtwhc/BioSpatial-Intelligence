"""
BioSpatial-Intelligence - 空間資料庫管理模組 (PostGIS DB Manager)
檔案位置: data/database_manager.py

模組用途：
1. 提供 GeoDataFrame 直接寫入 PostGIS 的高階封裝介面。
2. 管理寫入前的事務處理 (Transaction)，支援安全追加 (Append) 或強制重置 (Truncate)。
3. 內建模擬資料產生器與 CLI 介面，方便開發初期在缺乏真實影像時進行系統整合測試。

維護提示：
執行 clear_old_data=True 會觸發 TRUNCATE CASCADE，請確保前端或管線呼叫時具備足夠的權限控管。
"""

import os
import argparse
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

# 確保載入環境變數中的資料庫憑證，避免將機密寫死在程式碼中
load_dotenv(override=True)

# --- 1. 環境變數與全域常數 ---
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Your_Password_Here") 
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

# 組合 SQLAlchemy 標準連線字串
DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_engine(db_url: str = DB_URL) -> Engine:
    """取得資料庫連線引擎"""
    return create_engine(db_url)

def save_gdf_to_postgis(gdf: gpd.GeoDataFrame, table_name: str, db_url: str = DB_URL, clear_old_data: bool = False) -> None:
    """
    將 GeoDataFrame 寫入 PostGIS 資料庫。
    
    參數:
    - gdf: 包含幾何與屬性資料的 GeoDataFrame。
    - table_name: 目標資料表名稱 (例如 'habitats')。
    - db_url: 資料庫連線字串。
    - clear_old_data: [危險操作] 預設為 False。若為 True，寫入前將清空整張資料表。
    """
    engine = get_engine(db_url)
    try:
        print(f"[*] 正在連線至資料庫並準備寫入 {len(gdf)} 筆資料至 '{table_name}'...")
        
        # 欄位清洗：確保寫入的欄位與 models.py 定義的 Schema 一致
        # 捨棄運算過程中產生的暫時性特徵欄位，防止資料庫寫入報錯
        columns_to_keep = ['habitat_type', 'source', 'geom']
        gdf_clean = gdf[[col for col in columns_to_keep if col in gdf.columns]]
        
        # 覆寫保護機制：若有明確下達指令，才透過 SQLAlchemy 事務清空資料表
        if clear_old_data:
            with engine.begin() as conn:
                print("[!] 警告：正在清空現有資料表...")
                # 使用 RESTART IDENTITY 確保自動遞增的 ID 回歸至 1
                conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;"))
            
        # 核心寫入動作：利用 GeoPandas 內建的 to_postgis 函式
        # if_exists='append' 代表將資料附加至現有表中
        gdf_clean.to_postgis(
            name=table_name, 
            con=engine, 
            if_exists='append', 
            index=False
        )
            
        print(f"[+] 成功！資料已正式以 EPSG:4326 存入 PostGIS ({table_name})。")
    except Exception as e:
        print(f"[-] 寫入過程發生錯誤: {e}")

def seed_test_data() -> gpd.GeoDataFrame:
    """
    產生模擬棲地測試資料。
    用於在沒有 Sentinel/NLSC 影像的情況下，驗證資料庫寫入與 API 讀取邏輯。
    """
    p1 = Polygon([(120.66, 24.15), (120.67, 24.15), (120.67, 24.16), (120.66, 24.16), (120.66, 24.15)])
    p2 = Polygon([(120.68, 24.17), (120.69, 24.17), (120.685, 24.18), (120.68, 24.17)])
    p3 = Polygon([(120.65, 24.13), (120.66, 24.13), (120.66, 24.14), (120.65, 24.14), (120.65, 24.13)])

    data = {
        'habitat_type': ['次生林', '草生地', '水體'],
        'geom': [MultiPolygon([p1]), MultiPolygon([p2]), MultiPolygon([p3])]
    }
    # 強制設定為 EPSG:4326 以符合系統全域標準
    return gpd.GeoDataFrame(data, crs="EPSG:4326", geometry='geom')

# --- 2. 終端機指令介面 (CLI) ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BioSpatial Intelligence 資料庫寫入管理工具")
    parser.add_argument("--mock", action="store_true", help="寫入模擬測試資料 (假資料)")
    parser.add_argument("--reset", action="store_true", help="寫入前先清空資料庫中的舊資料 (危險操作)")
    args = parser.parse_args()

    if args.mock:
        print("[!] 測試模式啟動：準備產生假資料。")
        mock_gdf = seed_test_data()
        save_gdf_to_postgis(mock_gdf, table_name='habitats', clear_old_data=args.reset)
    else:
        print("[i] 提示：此模組通常應由 main_pipeline.py 呼叫作為函式庫使用。")
        print("若要強制產生並寫入假資料進行測試，請執行: python data/database_manager.py --mock")
        print("若要清空舊資料並寫入假資料，請執行: python data/database_manager.py --mock --reset")