"""
BioSpatial-Intelligence - SAM 實體分割引擎 (Instance Segmentation)
檔案位置: model/sam_processor.py

模組用途：
1. 載入 Segment Anything Model (SAM) 權重，配置全景自動遮罩生成器。
2. 執行 GPU 加速推論，從光學影像中切割出所有潛在的物理實體邊界。
3. 實作「畫家演算法 (Painter's Algorithm)」解決遮罩重疊，並進行網格轉向量 (Raster to Vector) 與拓樸修復。

維護提示：
若系統發生 OOM (Out of Memory) 錯誤，請調降 SamAutomaticMaskGenerator 中的 points_per_side，或改用較小的模型權重 (如 vit_b 代替 vit_h)。
"""

import torch
import cv2
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
import time
import os
import scipy.ndimage as ndimage

class SAMHabitatSegmenter:
    def __init__(self, checkpoint_path=None, model_type="vit_b"):
        """
        初始化 SAM 模型並將其載入至最佳運算設備。
        """
        # 動態偵測運算硬體，優先使用 NVIDIA GPU (CUDA)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] 系統啟動：正在將 SAM 模型 ({model_type}) 載入至 {self.device.upper()}...")
        
        # 動態路徑解析：確保無論在哪個目錄執行腳本，都能正確找到 weights 資料夾
        if checkpoint_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            checkpoint_path = os.path.join(current_dir, "weights", f"sam_{model_type}_01ec64.pth")
            
        print(f"[*] 準備載入權重檔: {checkpoint_path}")
        
        # 註冊並載入底層神經網路
        self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
        self.sam.to(device=self.device)
        
        # 配置全域測繪參數：此設定針對「生態地貌」進行了優化
        self.mask_generator = SamAutomaticMaskGenerator(
            model=self.sam,
            points_per_side=64,           # 提高掃描網格密度 (預設通常為32)，以捕捉細小棲地
            pred_iou_thresh=0.5,          # 降低 IoU 閾值，容忍生態交界處(如林緣)的模糊邊界
            stability_score_thresh=0.8,  # 降低穩定度閾值，鼓勵模型輸出更多潛在區塊
            min_mask_region_area=10,      # 過濾掉極小面積的雜訊斑塊
            crop_n_layers=1,              # 啟動影像分塊掃描 (Image Cropping)，強迫模型放大檢視細節
            crop_n_points_downscale_factor=2
        )
        print("[+] SAM 模型載入完成！")

    def process_image_to_polygons(self, input_file: str) -> gpd.GeoDataFrame:
        """
        核心處理管線：讀取 GeoTIFF -> SAM 分割 -> 拓樸平整化 -> 輸出 GeoDataFrame。
        """
        print(f"[*] 讀取影像進行智能分割: {input_file}")
        
        with rasterio.open(input_file) as src:
            img = src.read([1, 2, 3])
            img = np.moveaxis(img, 0, -1) # 將通道維度移至最後 (C, H, W) -> (H, W, C)
            affine = src.transform
            crs = src.crs

        # 🌟 記憶體底層優化：
        # np.ascontiguousarray 確保記憶體區塊連續，這是 OpenCV/C++ 底層函式庫順利運作的前提，
        # 可避免「Layout incompatible」的嚴重報錯。
        img_contiguous = np.ascontiguousarray(img)
        img_8bit = cv2.normalize(img_contiguous, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8) # type: ignore

        print("[*] 正在執行 GPU 智能推論切割...")
        start_time = time.time()
        
        # 執行模型推論，回傳包含眾多 dict 的 list (每個 dict 代表一個遮罩)
        masks = self.mask_generator.generate(img_8bit)
        
        print(f"[+] 推論完成！耗時: {time.time() - start_time:.2f} 秒。共找到 {len(masks)} 個原始遮罩。")
        print("[*] 正在執行「空間拓樸平整化 (Flattening)」消除重疊區域...")

        # 🌟 畫家演算法 (Painter's Algorithm)：解決 SAM 遮罩相互重疊 (俄羅斯娃娃效應) 的問題
        # 1. 依照遮罩面積由大到小排序。大面積視為背景 (Bottom)，小面積視為前景 (Top)。
        masks_sorted = sorted(masks, key=lambda x: x['area'], reverse=True)
        
        # 2. 建立一張與原圖尺寸相同的空白整數陣列 (畫布)
        height, width = img_8bit.shape[:2]
        master_mask = np.zeros((height, width), dtype=np.int32)
        
        # 3. 依序將遮罩「畫」上去。小物件(後畫)會直接覆蓋掉大物件(先畫)的衝突像素，形成絕對平整的單一圖層。
        for i, mask_data in enumerate(masks_sorted, start=1):
            bool_mask = mask_data["segmentation"]
            master_mask[bool_mask] = i  
        
        print("[*] 正在執行背景空隙填補以達成 0 縫隙拓樸...")
        # 找出所有未被 SAM 覆蓋的背景像素 (值為 0)
        invalid_pixels = (master_mask == 0)
        if invalid_pixels.any():
            # 利用距離轉換，找出距離每個 0 像素最近的非 0 像素索引
            distances, indices = ndimage.distance_transform_edt(  # type: ignore
                invalid_pixels, 
                return_distances=True, 
                return_indices=True
            )
            # 強制將背景像素替換為最近鄰物件的 ID
            master_mask = master_mask[tuple(indices)]
            
        print("[*] 正在將平整化後的遮罩轉換為唯一幾何多邊形 (Raster to Vector)...")
        features = []
        
        # 利用 rasterio.features.shapes 走訪陣列，將像素色塊提取為向量多邊形
        for geom, val in shapes(master_mask, mask=(master_mask > 0), transform=affine):
            val = int(val)
            if val > 0: 
                original_data = masks_sorted[val - 1]
                features.append({
                    'geometry': shape(geom),
                    'properties': {
                        'sam_id': val,
                        'area_pixels': original_data['area'],
                        'habitat_type': '待分類 (SAM)', # 預設標籤，等待後續 RF 分類器處理
                    }
                })

        gdf = gpd.GeoDataFrame.from_features(features, crs=crs)

        # 🌟 幾何拓樸修復 (Geometry Validation)
        # 1. 修復自相交 (Self-intersection)：使用 buffer(0) 是一個經典的 GIS 技巧，
        #    它能強制 Shapely 重新計算並合併多邊形頂點，解決「Bowtie (蝴蝶結)」形狀的無效幾何錯誤。
        gdf['geometry'] = gdf['geometry'].buffer(0) 
        
        # 2. 空間雜訊過濾：過濾掉面積小於 10^-8 度的極小碎屑 (EPSG:4326下約為 0.1 平方公尺)，
        #    防止後續進行 ST_Simplify 時因面積過小而導致資料庫運算報錯。
        gdf = gdf[gdf.geometry.area > 1e-8] 
        
        # 3. 型態約束：只保留 Polygon 或 MultiPolygon，剃除退化成的 LineString 或 Point。
        gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

        # 確保輸出結果統一為系統標準的 WGS84 座標
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 轉換成功！共生成 {len(gdf)} 個精確幾何多邊形。")
        return gdf

# 模組內部單元測試與檢核區塊
if __name__ == "__main__":
    from habitat_classifier import HabitatClassifier 
    
    # 請確保資料夾結構與影像檔名符合你的本機環境
    TEST_IMAGE = "./data/habitat_sample_nlsc_6.tif" 
    
    try:
        segmenter = SAMHabitatSegmenter()
        sam_gdf = segmenter.process_image_to_polygons(TEST_IMAGE)
        
        classifier = HabitatClassifier()
        classifier.train_from_samples("./data/training_samples.gpkg", TEST_IMAGE) 
        final_gdf = classifier.predict(sam_gdf, TEST_IMAGE)
        
        print("\n====== 🚀 Ver 2.1 Model Tier 產出成果 ======")
        print(final_gdf[['sam_id', 'habitat_type', 'geometry']].head(10))
        
        final_gdf.to_file("ver2.1_final_output.geojson", driver="GeoJSON")
        print("\n[+] 成果已儲存為 ver2.1_final_output.geojson")
        
    except Exception as e:
        print(f"[-] 測試發生錯誤: {e}")