import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine, text
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
        
        # ⚠️ 修改點 1：將 if_exists 改為 'replace'，覆蓋掉之前錯誤的資料表
        gdf.to_postgis(
            name=table_name, 
            con=engine, 
            if_exists='replace', 
            index=False
        )
        
        # ⚠️ 額外動作：因為 to_postgis(replace) 預設不會把 id 設為 Primary Key，
        # 我們需要補上一句 SQL 告訴資料庫 id 是主鍵，這樣 SQLAlchemy 才不會報錯。
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN id SERIAL PRIMARY KEY;"))
            
        print(f"[+] 成功！資料已正式存入 PostGIS ({table_name})，並已設定主鍵。")
    except Exception as e:
        print(f"[-] 寫入過程發生錯誤: {e}")

def seed_test_data() -> gpd.GeoDataFrame:
    """產生模擬棲地圖資"""
    print("[*] 正在產生模擬棲地測試資料...")
    
    p1 = Polygon([(120.66, 24.15), (120.67, 24.15), (120.67, 24.16), (120.66, 24.16), (120.66, 24.15)])
    p2 = Polygon([(120.68, 24.17), (120.69, 24.17), (120.685, 24.18), (120.68, 24.17)])
    p3 = Polygon([(120.65, 24.13), (120.66, 24.13), (120.66, 24.14), (120.65, 24.14), (120.65, 24.13)])

    data = {
        # ⚠️ 修改點 2：明確加入 id 欄位
        'id': [1, 2, 3],
        'habitat_type': ['次生林', '草生地', '水體'],
        'geom': [MultiPolygon([p1]), MultiPolygon([p2]), MultiPolygon([p3])]
    }

    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326", geometry='geom')
    gdf['area_ha'] = gdf.to_crs(epsg=3826).area / 10000 
    return gdf

if __name__ == "__main__":
    print("[!] 進入測試模式：即將寫入假資料...")
    mock_gdf = seed_test_data()
    save_gdf_to_postgis(mock_gdf, table_name='habitats')