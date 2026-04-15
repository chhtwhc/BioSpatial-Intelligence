import os
import argparse
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# --- 1. 環境變數與全域常數 ---
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Crazypig12345") 
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

DB_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def get_engine(db_url: str = DB_URL) -> Engine:
    """取得資料庫連線引擎"""
    return create_engine(db_url)

# ⚠️ 加入 clear_old_data 參數，預設為 False，保護真實資料不被誤刪
def save_gdf_to_postgis(gdf: gpd.GeoDataFrame, table_name: str, db_url: str = DB_URL, clear_old_data: bool = False) -> None:
    """將 GeoDataFrame 寫入 PostGIS 資料庫"""
    engine = get_engine(db_url)
    try:
        print(f"[*] 正在連線至資料庫並準備寫入 {len(gdf)} 筆資料至 '{table_name}'...")
        
        columns_to_keep = ['habitat_type', 'geom']
        gdf_clean = gdf[[col for col in columns_to_keep if col in gdf.columns]]
        
        # 若有明確下達指令，才清空資料表
        if clear_old_data:
            with engine.begin() as conn:
                print("[!] 警告：正在清空現有資料表...")
                conn.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;"))
            
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
    """產生模擬棲地測試資料"""
    p1 = Polygon([(120.66, 24.15), (120.67, 24.15), (120.67, 24.16), (120.66, 24.16), (120.66, 24.15)])
    p2 = Polygon([(120.68, 24.17), (120.69, 24.17), (120.685, 24.18), (120.68, 24.17)])
    p3 = Polygon([(120.65, 24.13), (120.66, 24.13), (120.66, 24.14), (120.65, 24.14), (120.65, 24.13)])

    data = {
        'habitat_type': ['次生林', '草生地', '水體'],
        'geom': [MultiPolygon([p1]), MultiPolygon([p2]), MultiPolygon([p3])]
    }
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