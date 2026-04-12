import rasterio
import cv2
import numpy as np
import geopandas as gpd
from sqlalchemy import create_engine
from rasterio.features import shapes

# --- 1. 配置區 ---
INPUT_TIFF = "habitat_sample_100ha.tif"
DB_URL = "postgresql://postgres:Crazypig12345@localhost:5432/postgres"
engine = create_engine(DB_URL)

# 棲地名稱對照表 (請根據你觀察到的 K-Means 色塊自行調整對應)
HABITAT_MAP = {
    0: "水體/河流",
    1: "高植生/林地",
    2: "都市建物/人造設施",
    3: "裸露地/工地"
}

def run_integration_pipeline():
    try:
        print(f"[*] 啟動整合管線，讀取來源: {INPUT_TIFF}")
        
        with rasterio.open(INPUT_TIFF) as src:
            img = src.read([1, 2, 3])
            img = np.moveaxis(img, 0, -1)
            affine = src.transform
            crs = src.crs

            # A. 影像分類 (K-Means)
            print("[*] 執行影像分割...")
            data = img.reshape((-1, 3)).astype(np.float32)
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
            _, labels, _ = cv2.kmeans(data, 4, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
            segmented_img = labels.reshape(img.shape[:2]).astype(np.int32)

            # B. 向量化
            print("[*] 執行向量化轉換...")
            results = (
                {'properties': {'class_id': int(v)}, 'geometry': s}
                for i, (s, v) in enumerate(shapes(segmented_img, mask=None, transform=affine))
            )
            gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)

            # C. 資料清理與轉換
            # 移除碎屑並對應棲地名稱
            gdf['area'] = gdf.geometry.area
            gdf = gdf[gdf['area'] > 200] # 降低門檻，減少白洞
            gdf['habitat_type'] = gdf['class_id'].map(HABITAT_MAP)
            
            # 轉為 WGS84
            gdf = gdf.to_crs("EPSG:4326")
            
            # 只保留資料庫需要的欄位
            output_gdf = gdf[['habitat_type', 'geometry']].rename_geometry('geom')

        # D. 寫入 PostGIS
        print(f"[*] 正在將 {len(output_gdf)} 筆棲地資料寫入資料庫...")
        output_gdf.to_postgis(
            name='habitats',
            con=engine,
            if_exists='append', # 追加模式
            index=False
        )
        print("[+] 整合管線執行成功！資料已入庫。")

    except Exception as e:
        print(f"[-] 管線執行失敗: {e}")

if __name__ == "__main__":
    run_integration_pipeline()