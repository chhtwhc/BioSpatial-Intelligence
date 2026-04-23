"""
BioSpatial-Intelligence - 傳統視覺基礎分割工具 (K-Means Baseline)
檔案位置: data/image_processor.py

模組用途：
1. 實作非監督式學習 (K-Means) 進行影像像素分群，作為 AI 引擎導入前的實驗性基線。
2. 展示從光學網格資料 (Raster) 提取幾何輪廓 (Vector) 的經典 GIS 轉換演算法。
3. 透過動態投影轉換 (至 EPSG:3826) 進行高精度的物理面積過濾，剔除空間雜訊。

維護提示：
此模組目前定位為實驗性或備用工具。若系統未來需要在無 GPU 運算資源的環境下，進行快速、粗略的地貌輪廓掃描，可呼叫此模組替代 SAM 引擎。
"""

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
    讀取衛星或航照圖，執行 K-Means 色彩分群，並將結果轉換為具有空間參考的 GeoDataFrame。
    
    參數:
    - input_file: GeoTIFF 影像的路徑。
    - k: K-Means 的分群數量 (預設 4 類，對應基本的地貌色塊)。
    - min_area_sqm: 最小保留面積 (平方公尺)，預設 200.0，用於過濾極小斑塊 (Salt-and-Pepper Noise)。
    
    回傳:
    - (向量圖資 GeoDataFrame, 分類標籤的二維整數矩陣)
    """
    print(f"[*] 讀取影像進行特徵分析: {input_file}")
    
    # ---------------------------------------------------------
    # 1. 影像讀取與前處理
    # ---------------------------------------------------------
    with rasterio.open(input_file) as src:
        # 讀取前三個波段 (通常為 RGB)
        img = src.read([1, 2, 3])
        # 轉換維度：從 Rasterio 的 (C, H, W) 轉為 OpenCV 需要的 (H, W, C)
        img = np.moveaxis(img, 0, -1)
        affine = src.transform
        crs = src.crs

        print(f"[*] 執行 K-Means 分群 (k={k})...")
        # 將三維影像展平為二維陣列 (像素總數, 3通道)，並轉為 float32 以符合 cv2.kmeans 精度要求
        data = img.reshape((-1, 3)).astype(np.float32)
        
        # 定義停止條件：當達到最高迭代次數 (10) 或中心點移動距離小於閾值 (1.0) 時停止
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        
        # 執行 OpenCV 高效能 K-Means 分群
        _, labels, _ = cv2.kmeans(data, k, None, criteria, 10, cv2.KMEANS_RANDOM_CENTERS)
        
        # 將一維標籤陣列還原回原始影像的長寬維度
        segmented_img = labels.reshape(img.shape[:2]).astype(np.int32)

        print("[*] 正在提取幾何輪廓 (Raster to Vector)...")
        
        # ---------------------------------------------------------
        # 2. 網格轉向量 (Raster to Vector)
        # ---------------------------------------------------------
        # 利用 rasterio.features.shapes 走訪相鄰的同色像素塊，生成幾何邊界
        results = (
            {'properties': {'class_id': int(v)}, 'geometry': s}
            for i, (s, v) in enumerate(shapes(segmented_img, mask=None, transform=affine))
        )

        gdf = gpd.GeoDataFrame.from_features(list(results), crs=crs)
        
        # ---------------------------------------------------------
        # 3. 空間雜訊過濾與座標標準化
        # ---------------------------------------------------------
        # 若影像本身未帶有 CRS，優先賦予原始影像的投影
        if gdf.crs is None:
            gdf.set_crs(crs, inplace=True)

        # 核心精確度控制：
        # 由於 WGS84 (經緯度) 無法直接精確計算公制面積，我們將其暫時投影至 TWD97 (EPSG:3826) 臺灣平面坐標系
        gdf_projected = gdf.to_crs("EPSG:3826")
        
        # 計算精確物理面積 (平方公尺)，並賦值回原本的 GDF
        gdf['area_sqm'] = gdf_projected.geometry.area
        
        # 雜訊過濾：剔除面積過小 (如小於 200 平方公尺) 的碎屑多邊形，優化前端渲染與後續儲存
        gdf = gdf[gdf['area_sqm'] > min_area_sqm].drop(columns=['area_sqm'])

        # 確保最終輸出格式符合系統規範的全球標準 EPSG:4326
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 成功提取！共生成 {len(gdf)} 個棲地多邊形。")
        return gdf, segmented_img

# 模組內部單元測試區塊
if __name__ == "__main__":
    # 單獨測試影像處理功能，確保模組具備獨立執行能力
    INPUT_TIFF = "habitat_sample_100ha.tif"
    try:
        final_gdf, label_map = process_image_to_polygons(INPUT_TIFF)
        
        # 建立並排圖表進行視覺對比：左側為像素分群結果，右側為向量多邊形
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
        
        ax1.imshow(label_map)
        ax1.set_title("K-Means Segmentation (Raster)")
        
        # 利用 GeoPandas 內建的繪圖功能展示幾何輪廓
        final_gdf.plot(column='class_id', ax=ax2, legend=True, cmap='viridis')
        ax2.set_title("Vectorized Polygons (GeoDataFrame)")
        
        plt.show()
    except Exception as e:
        print(f"[-] 測試失敗: {e}")