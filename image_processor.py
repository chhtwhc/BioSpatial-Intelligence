from typing import Tuple
import rasterio
from rasterio.features import shapes
import numpy as np
import cv2
import geopandas as gpd
import matplotlib.pyplot as plt

def process_image_to_polygons(
    input_file: str, 
    k: int = 4, 
    min_area_sqm: float = 200.0
) -> Tuple[gpd.GeoDataFrame, np.ndarray]:
    """
    讀取衛星圖，執行 K-Means 分群，並轉換為 GeoDataFrame。
    回傳 (向量圖資 GDF, 分類標籤矩陣)。
    """
    print(f"[*] 讀取影像進行特徵分析: {input_file}")
    with rasterio.open(input_file) as src:
        img = src.read([1, 2, 3])
        img = np.moveaxis(img, 0, -1)
        affine = src.transform
        crs = src.crs

        print(f"[*] 執行 K-Means 分群 (k={k})...")
        data = img.reshape((-1, 3)).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, _ = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        segmented_img = labels.reshape(img.shape[:2]).astype(np.int32)

        print("[*] 正在提取幾何輪廓 (Raster to Vector)...")
        results = (
            {'properties': {'class_id': int(v)}, 'geometry': s}
            for i, (s, v) in enumerate(shapes(segmented_img, mask=None, transform=affine))
        )

        gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)
        
        # 移除極小碎屑
        gdf['area'] = gdf.geometry.area
        gdf = gdf[gdf['area'] > min_area_sqm].drop(columns=['area'])

        # 座標標準化
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 成功提取！共生成 {len(gdf)} 個棲地多邊形。")
        return gdf, segmented_img

if __name__ == "__main__":
    # 單獨測試影像處理功能
    INPUT_TIFF = "habitat_sample_100ha.tif"
    try:
        final_gdf, label_map = process_image_to_polygons(INPUT_TIFF)
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
        ax1.imshow(label_map)
        ax1.set_title("K-Means Segmentation")
        final_gdf.plot(column='class_id', ax=ax2, legend=True, cmap='viridis')
        ax2.set_title("Vectorized Polygons")
        plt.show()
    except Exception as e:
        print(f"[-] 測試失敗: {e}")