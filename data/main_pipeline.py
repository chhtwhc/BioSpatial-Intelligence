import sys
import os
import argparse
from typing import List, Tuple

# 動態將專案根目錄加入 Python 系統路徑，確保能同時讀取 data 與 model 模組
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from data.sentinel_api_client import fetch_satellite_image
from data.nlsc_api_client import fetch_nlsc_image  
from data.database_manager import save_gdf_to_postgis

# 👉 匯入 Ver 2.1 全新的 AI 引擎
from model.sam_processor import SAMHabitatSegmenter
from model.habitat_classifier import HabitatClassifier

# --- 配置區 ---
DEFAULT_BBOX = [121.450, 25.080, 121.460, 25.090] # 測試用預設 BBOX
TARGET_TABLE = "habitats"

def run_integration_pipeline(bbox: List[float], source: str = "sentinel", clear_old_data: bool = False) -> Tuple[bool, str]:
    """
    [Ver 2.1 終極版] 接收動態 BBOX -> 下載影像 -> SAM 分割 -> RF 分類 -> 入庫 PostGIS
    """
    try:
        print(f"====== 🚀 啟動 {source.upper()} AI 空間分析管線 ======")
        print(f"[*] 分析範圍 (BBOX): {bbox}")
        
        # 步驟 1: 取得衛星/航照影像
        print(f"\n>>> 步驟 1: 獲取 {source.upper()} 影像")
        image_filename = f"data/temp_analysis_{source}.tif"
        
        if source == "sentinel":
            tif_path = fetch_satellite_image(bbox=bbox, output_filename=image_filename)
        elif source == "nlsc":
            tif_path = fetch_nlsc_image(bbox=bbox, output_filename=image_filename)
        else:
            return False, "不支援的影像來源"

        if not tif_path:
            return False, "無法取得影像資料，管線提前終止。"

        # 步驟 2: 啟動 SAM 模型進行精準分割
        print("\n>>> 步驟 2: 啟動 SAM 實體分割 (Instance Segmentation)")
        segmenter = SAMHabitatSegmenter()
        sam_gdf = segmenter.process_image_to_polygons(tif_path)

        if len(sam_gdf) == 0:
            return False, "該範圍內未偵測到有效棲地 (產出 0 個多邊形)。"

        # 步驟 3: 啟動分類器並載入真實經驗
        print("\n>>> 步驟 3: 啟動 Random Forest 語意分類 (Semantic Classification)")
        classifier = HabitatClassifier()
        # 精確指向你的標註檔位置
        training_data_path = os.path.join(project_root, "model", "data", "training_samples.gpkg") 
        
        # 自動尋找該目錄下所有符合模式的 .tif 影像
        search_dir = os.path.join(project_root, "model", "data")
        
        # 動態抓取所有 habitat_sample_nlsc_ 開頭的 .tif 檔案
        reference_images = [
            os.path.join(search_dir, f) 
            for f in os.listdir(search_dir) 
            if f.startswith("habitat_sample_nlsc_") and f.endswith(".tif")
        ]
        
        print(f"[*] 成功在資料夾中偵測到 {len(reference_images)} 張參考影像用於訓練。")
        
        if len(reference_images) == 0:
            return False, "在 model/data/ 下找不到任何訓練底圖，請檢查檔名是否以 temp_analysis_nlsc_ 開頭"
        
        # 呼叫訓練函數 (傳入 List)
        classifier.train_from_samples(training_data_path, reference_images)
        
        final_gdf = classifier.predict(sam_gdf, tif_path)

        # 步驟 4: 資料清理與入庫
        print("\n>>> 步驟 4: 幾何轉換與 PostGIS 入庫")
        final_gdf['source'] = source 
        output_gdf = final_gdf[['habitat_type', 'source', 'geometry']].rename_geometry('geom')

        save_gdf_to_postgis(gdf=output_gdf, table_name=TARGET_TABLE, clear_old_data=clear_old_data)
        
        success_msg = f"分析成功！共產出 {len(output_gdf)} 個高精度棲地多邊形。"
        print(f"\n🎉 {success_msg}")
        return True, success_msg

    except Exception as e:
        error_msg = f"管線執行發生未預期錯誤: {e}"
        print(f"\n❌ {error_msg}")
        return False, error_msg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="執行 Ver 2.1 自動化分析管線")
    parser.add_argument("--source", type=str, choices=["sentinel", "nlsc"], default="nlsc")
    args = parser.parse_args()
    
    success, msg = run_integration_pipeline(bbox=DEFAULT_BBOX, source=args.source)
    if not success:
        sys.exit(1)