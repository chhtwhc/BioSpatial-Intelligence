import rasterio
from rasterio.features import shapes
import numpy as np
import cv2
import geopandas as gpd
from shapely.geometry import shape
import matplotlib.pyplot as plt

def process_raster_to_vector(input_file, k=4):
    print(f"[*] 讀取影像: {input_file}")
    with rasterio.open(input_file) as src:
        # 1. 讀取資料並轉換為 KMeans 格式 (H, W, C)
        img = src.read([1, 2, 3]) # 讀取 RGB
        img = np.moveaxis(img, 0, -1) # 轉為 OpenCV 格式 (100, 100, 3)
        affine = src.transform
        crs = src.crs

        # 2. 影像分類 (K-Means)
        print(f"[*] 執行 K-Means 分群 (k={k})...")
        data = img.reshape((-1, 3)).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, _ = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # 轉回 2D 標籤圖
        segmented_img = labels.reshape(img.shape[:2]).astype(np.int32)

        # 3. 網格轉向量 (Raster to Vector)
        print("[*] 正在提取幾何輪廓...")
        results = (
            {'properties': {'class_id': int(v)}, 'geometry': s}
            for i, (s, v) in enumerate(shapes(segmented_img, mask=None, transform=affine))
        )

        # 4. 建立 GeoDataFrame 並清理數據
        gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)
        
        # 移除極小碎屑 (面積小於 500 平方公尺的區塊，增加圖資整潔度)
        gdf['area'] = gdf.geometry.area
        gdf = gdf[gdf['area'] > 500].drop(columns=['area'])

        # 5. 座標標準化：轉回專案規範的 EPSG:4326
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 成功轉化！產出 {len(gdf)} 個棲地多邊形。")
        return gdf, segmented_img

if __name__ == "__main__":
    INPUT_TIFF = "habitat_sample_100ha.tif"
    
    final_gdf, label_map = process_raster_to_vector(INPUT_TIFF)

    # 顯示分類後的色塊圖與向量邊界
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
    ax1.imshow(label_map)
    ax1.set_title("K-Means Segmentation")
    
    final_gdf.plot(column='class_id', ax=ax2, legend=True, cmap='viridis')
    ax2.set_title("Vectorized Polygons")
    plt.show()

    # 預覽資料表內容
    print(final_gdf.head())