import torch
import cv2
import numpy as np
import rasterio
from rasterio.features import shapes
import geopandas as gpd
from shapely.geometry import shape
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
import time

class SAMHabitatSegmenter:
    def __init__(self, checkpoint_path="weights/sam_vit_b_01ec64.pth", model_type="vit_b"):
        """初始化 SAM 模型並載入 GPU"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] 系統啟動：正在將 SAM 模型 ({model_type}) 載入至 {self.device.upper()}...")
        
        # 註冊並載入模型
        self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
        self.sam.to(device=self.device)
        
        # 使用自動遮罩生成器 (可根據航照圖複雜度調整參數)
        self.mask_generator = SamAutomaticMaskGenerator(
            model=self.sam,
            points_per_side=32, # 掃描點的密度，越高切得越細
            pred_iou_thresh=0.86,
            stability_score_thresh=0.92,
            min_mask_region_area=100 # 過濾掉極小的雜訊遮罩
        )
        print("[+] SAM 模型載入完成！")

    def process_image_to_polygons(self, input_file: str) -> gpd.GeoDataFrame:
        """讀取 GeoTIFF，使用 SAM 進行實體分割，並回傳 GeoDataFrame"""
        print(f"[*] 讀取影像進行智能分割: {input_file}")
        
        with rasterio.open(input_file) as src:
            img = src.read([1, 2, 3])
            img = np.moveaxis(img, 0, -1) # 轉為 (H, W, C)
            affine = src.transform
            crs = src.crs

        # SAM 模型預期輸入為 8-bit RGB 影像 (0-255)
        # 若是衛星圖 (如 Sentinel L2A) 數值範圍可能很大，需先做常規化
        # 確保影像矩陣在記憶體中是連續的 (解決 OpenCV 底層相容性問題)
        img_contiguous = np.ascontiguousarray(img)
        
        # 讓 OpenCV 自動分配記憶體，並加上 type: ignore 讓 Pylance 取消紅線警告
        img_8bit = cv2.normalize(img_contiguous, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8) # type: ignore

        print("[*] 正在執行 GPU 智能推論切割 (這將比 CPU 快上數十倍)...")
        start_time = time.time()
        
        # 核心 AI 推論：產出所有物件的遮罩
        masks = self.mask_generator.generate(img_8bit)
        
        print(f"[+] 推論完成！耗時: {time.time() - start_time:.2f} 秒。共找到 {len(masks)} 個獨立區域。")
        print("[*] 正在將 AI 遮罩轉換為具備座標系統的多邊形 (Raster to Vector)...")

        features = []
        for i, mask_data in enumerate(masks):
            # 提取二元遮罩矩陣
            segmentation_mask = mask_data["segmentation"].astype(np.uint8)
            
            # 利用 rasterio 將二元矩陣轉為地理幾何輪廓
            for geom, val in shapes(segmentation_mask, mask=segmentation_mask, transform=affine):
                if val == 1.0: # 確保只處理遮罩內部
                    features.append({
                        'geometry': shape(geom),
                        'properties': {
                            'sam_id': i,
                            'area_pixels': mask_data['area'],
                            # 預留給輕量分類器的欄位，目前先標為未分類
                            'habitat_type': '待分類 (SAM)', 
                        }
                    })

        # 建立 GeoDataFrame
        gdf = gpd.GeoDataFrame.from_features(features, crs=crs)

        # 系統級防呆與座標標準化：確保回傳的一律是 EPSG:4326
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 轉換成功！共生成 {len(gdf)} 個精確幾何多邊形。")
        return gdf

if __name__ == "__main__":
    from habitat_classifier import HabitatClassifier # 匯入剛寫好的分類器
    
    TEST_IMAGE = "../data/habitat_sample_nlsc.tif" 
    
    try:
        # 1. 啟動 SAM 切割器
        segmenter = SAMHabitatSegmenter()
        sam_gdf = segmenter.process_image_to_polygons(TEST_IMAGE)
        
        # 2. 啟動 機器學習分類器
        classifier = HabitatClassifier()
        final_gdf = classifier.predict(sam_gdf, TEST_IMAGE)
        
        # 3. 檢視最終成果
        print("\n====== 🚀 Ver 2.1 Model Tier 產出成果 ======")
        print(final_gdf[['sam_id', 'habitat_type', 'geometry']].head(10))
        
        # 印出分類統計
        print("\n[*] 棲地分類統計：")
        print(final_gdf['habitat_type'].value_counts())
        
        # 儲存為 GeoJSON
        final_gdf.to_file("ver2.1_final_output.geojson", driver="GeoJSON")
        print("\n[+] 成果已儲存為 ver2.1_final_output.geojson")
        
        # 確認座標系統是否為 EPSG:4326
        print("\n[*] 最終座標系統：")
        print(final_gdf.crs)
        
    except Exception as e:
        print(f"[-] 測試發生錯誤: {e}")