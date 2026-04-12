import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
from sqlalchemy import create_engine
import pandas as pd

# --- 1. 資料庫連線配置 ---
# 注意：若你在 Docker 啟動時設定了不同密碼，請修改 'password'
DB_URL = "postgresql://postgres:Crazypig12345@localhost:5432/postgres"
engine = create_engine(DB_URL)

def generate_habitat_data():
    print("[*] 正在產生模擬棲地圖資...")
    
    # 手動定義三個位於台灣中部的多邊形 (經緯度座標)
    # 次生林 (正方形)
    p1 = Polygon([(120.66, 24.15), (120.67, 24.15), (120.67, 24.16), (120.66, 24.16), (120.66, 24.15)])
    # 草生地 (三角形)
    p2 = Polygon([(120.68, 24.17), (120.69, 24.17), (120.685, 24.18), (120.68, 24.17)])
    # 水體 (長方形)
    p3 = Polygon([(120.65, 24.13), (120.66, 24.13), (120.66, 24.14), (120.65, 24.14), (120.65, 24.13)])

    # 封裝成清單
    data = {
        'habitat_type': ['次生林', '草生地', '水體'],
        'geom': [MultiPolygon([p1]), MultiPolygon([p2]), MultiPolygon([p3])]
    }

    # 建立 GeoDataFrame 並指定座標系為 WGS84 (EPSG:4326)
    gdf = gpd.GeoDataFrame(data, crs="EPSG:4326", geometry='geom')
    
    # 💡 專業技巧：計算面積 (公頃)
    # 我們先轉投影到 TWD97 (EPSG:3826, 單位是公尺) 計算面積，再換算成公頃
    gdf['area_ha'] = gdf.to_crs(epsg=3826).area / 10000 
    
    return gdf

def save_to_postgis(gdf):
    try:
        print(f"[*] 正在連線至資料庫並寫入 {len(gdf)} 筆資料...")
        
        # 使用 to_postgis 直接寫入
        # if_exists='append' 表示保留資料表，僅增加資料
        gdf.to_postgis(
            name='habitats', 
            con=engine, 
            if_exists='append', 
            index=False
        )
        
        print("[+] 成功！資料已正式存入 Docker 內的 PostGIS。")
        
    except Exception as e:
        print(f"[-] 寫入過程發生錯誤: {e}")
        print("💡 請確認：1. Docker 是否啟動 2. 密碼是否正確 3. 是否已安裝 psycopg2-binary")

if __name__ == "__main__":
    # 執行流程
    mock_gdf = generate_habitat_data()
    save_to_postgis(mock_gdf)