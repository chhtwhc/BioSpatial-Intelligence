import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

# --- 1. 全域常數 ---
DEFAULT_DB_URL = "postgresql://postgres:Crazypig12345@localhost:5432/postgres"

def get_engine(db_url: str = DEFAULT_DB_URL) -> Engine:
    """取得資料庫連線引擎"""
    return create_engine(db_url)

def save_gdf_to_postgis(gdf: gpd.GeoDataFrame, table_name: str, db_url: str = DEFAULT_DB_URL) -> None:
    """將 GeoDataFrame 寫入 PostGIS 資料庫"""
    engine = get_engine(db_url)
    try:
        print(f"[*] 正在連線至資料庫並寫入 {len(gdf)} 筆資料至 '{table_name}'...")
        # if_exists='append' 表示追加資料
        gdf.to_postgis(
            name=table_name, 
            con=engine, 
            if_exists='append', 
            index=False
        )
        print(f"[+] 成功！資料已正式存入 PostGIS ({table_name})。")
    except Exception as e:
        print(f"[-] 寫入過程發生錯誤: {e}")
        print("💡 請確認：1. Docker 是否啟動 2. 密碼是否正確 3. 是否已安裝 psycopg2-binary")

def seed_test_data() -> gpd.GeoDataFrame:
    """
    產生模擬棲地圖資 (僅供測試使用)。
    此函式已與主邏輯分離，需手動呼叫才會執行。
    """
    print("[*] 正在產生模擬棲地測試資料...")
    
    p1 = Polygon([(120.66, 24.15), (120.67, 24.15), (120.67, 24.16), (120.66, 24.16), (120.66, 24.15)])
    p2 = Polygon([(120.68, 24.17), (120.69, 24.17), (120.685, 24.18), (120.68, 24.17)])
    p3 = Polygon([(120.65, 24.13), (120.66, 24.13), (120.66, 24.14), (120.65, 24.14), (120.65, 24.13)])

    data = {
        'habitat_type': ['次生林', '草生地', '水體'],
        'geom': [MultiPolygon([p1]), MultiPolygon([p2]), MultiPolygon([p3])]
    }

    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326", geometry='geom')
    gdf['area_ha'] = gdf.to_crs(epsg=3826).area / 10000 
    return gdf

if __name__ == "__main__":
    # 測試模式：直接執行此檔案時，才會注入假資料
    print("[!] 進入測試模式：即將寫入假資料...")
    mock_gdf = seed_test_data()
    save_gdf_to_postgis(mock_gdf, table_name='habitats')