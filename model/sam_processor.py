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

class SAMHabitatSegmenter:
    # 將 checkpoint_path 預設值改為 None，讓我們在程式內部動態決定
    def __init__(self, checkpoint_path=None, model_type="vit_b"):
        """初始化 SAM 模型並載入 GPU"""
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[*] 系統啟動：正在將 SAM 模型 ({model_type}) 載入至 {self.device.upper()}...")
        
        # 動態取得絕對路徑，免疫 uvicorn 執行位置的問題
        if checkpoint_path is None:
            # 取得 sam_processor.py 所在的資料夾路徑 (即 model/)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # 組合出正確的權重檔絕對路徑
            checkpoint_path = os.path.join(current_dir, "weights", f"sam_{model_type}_01ec64.pth")
            
        print(f"[*] 準備載入權重檔: {checkpoint_path}")
        
        # 註冊並載入模型
        self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
        self.sam.to(device=self.device)
        
        # 全域測繪參數 (解決大面積空白問題)
        self.mask_generator = SamAutomaticMaskGenerator(
            model=self.sam,
            points_per_side=64,           # 掃描網格變密 4 倍
            pred_iou_thresh=0.6,          # 容忍更多邊界稍模糊的地貌
            stability_score_thresh=0.80,  # 讓模型不用那麼有把握也敢輸出遮罩
            min_mask_region_area=10,      # 保留較小的斑塊
            crop_n_layers=1,              # 啟動影像分塊掃描，強迫放大檢視細節
            crop_n_points_downscale_factor=2
        )
        print("[+] SAM 模型載入完成！")

    def process_image_to_polygons(self, input_file: str) -> gpd.GeoDataFrame:
        """讀取 GeoTIFF，使用 SAM 進行實體分割，並回傳無重疊的 GeoDataFrame"""
        print(f"[*] 讀取影像進行智能分割: {input_file}")
        
        with rasterio.open(input_file) as src:
            img = src.read([1, 2, 3])
            img = np.moveaxis(img, 0, -1) # 轉為 (H, W, C)
            affine = src.transform
            crs = src.crs

        # 🌟 亮點 2：底層記憶體管理 (解決 OpenCV Layout incompatible 報錯)
        img_contiguous = np.ascontiguousarray(img)
        img_8bit = cv2.normalize(img_contiguous, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8) # type: ignore

        print("[*] 正在執行 GPU 智能推論切割 (這將比 CPU 快上數十倍)...")
        start_time = time.time()
        
        masks = self.mask_generator.generate(img_8bit)
        
        print(f"[+] 推論完成！耗時: {time.time() - start_time:.2f} 秒。共找到 {len(masks)} 個原始遮罩。")
        print("[*] 正在執行「空間拓樸平整化 (Flattening)」消除重疊區域...")

        # 🌟 亮點 3：畫家演算法 (消除俄羅斯娃娃重疊現象)
        # 依照面積由大到小排序 (大背景在底層，小細節在上層覆蓋)
        masks_sorted = sorted(masks, key=lambda x: x['area'], reverse=True)
        
        # 建立一張與原圖相同的空白畫布
        height, width = img_8bit.shape[:2]
        master_mask = np.zeros((height, width), dtype=np.int32)
        
        # 將遮罩依序疊加覆蓋
        for i, mask_data in enumerate(masks_sorted, start=1):
            bool_mask = mask_data["segmentation"]
            master_mask[bool_mask] = i  # 小物件會直接蓋掉大物件的衝突像素
            
        print("[*] 正在將平整化後的遮罩轉換為唯一幾何多邊形 (Raster to Vector)...")
        features = []
        
        # 將整張 master_mask 一次性轉為不重疊的多邊形
        for geom, val in shapes(master_mask, mask=(master_mask > 0), transform=affine):
            val = int(val)
            if val > 0: 
                original_data = masks_sorted[val - 1]
                features.append({
                    'geometry': shape(geom),
                    'properties': {
                        'sam_id': val,
                        'area_pixels': original_data['area'],
                        'habitat_type': '待分類 (SAM)', 
                    }
                })

        gdf = gpd.GeoDataFrame.from_features(features, crs=crs)

        # 🌟 核心修正：自動修復無效幾何 + 過濾極小碎片
        # 1. 修復自相交的多邊形 (ST_MakeValid 的 Python 版)
        gdf['geometry'] = gdf['geometry'].buffer(0) 
        
        # 2. 過濾掉面積過小的碎片 (避免 ST_Simplify 報錯)
        # 在 EPSG:4326 下，0.00000001 約為 0.1 平方公尺
        gdf = gdf[gdf.geometry.area > 1e-8] 
        
        # 3. 確保只保留 Polygon 或 MultiPolygon (移除可能產生的線或點)
        gdf = gdf[gdf.geometry.type.isin(['Polygon', 'MultiPolygon'])]

        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        print(f"[+] 轉換成功！共生成 {len(gdf)} 個精確幾何多邊形。")
        return gdf

if __name__ == "__main__":
    from habitat_classifier import HabitatClassifier 
    
    # 請確保資料夾結構與影像檔名符合你的本機環境
    TEST_IMAGE = "./data/habitat_sample_nlsc_6.tif" 
    
    try:
        # 1. 啟動 SAM 切割器
        segmenter = SAMHabitatSegmenter()
        sam_gdf = segmenter.process_image_to_polygons(TEST_IMAGE)
        
        # 2. 啟動機器學習分類器並載入你的 QGIS 真實標註檔
        classifier = HabitatClassifier()
        # 注意：假設你剛才在 QGIS 中存成 training_samples.gpkg
        classifier.train_from_samples("./data/training_samples.gpkg", TEST_IMAGE) 
        
        # 3. 進行預測
        final_gdf = classifier.predict(sam_gdf, TEST_IMAGE)
        
        # 4. 檢視最終成果
        print("\n====== 🚀 Ver 2.1 Model Tier 產出成果 ======")
        print(final_gdf[['sam_id', 'habitat_type', 'geometry']].head(10))
        
        print("\n[*] 棲地分類統計：")
        print(final_gdf['habitat_type'].value_counts())
        
        # 儲存成果供 QGIS 視覺化檢查
        final_gdf.to_file("ver2.1_final_output.geojson", driver="GeoJSON")
        print("\n[+] 成果已儲存為 ver2.1_final_output.geojson")
        
    except Exception as e:
        print(f"[-] 測試發生錯誤: {e}")