"""
BioSpatial-Intelligence - 自動化整合分析管線 (ETL & AI Inference Pipeline)
檔案位置: data/main_pipeline.py

模組用途：
1. 擔任系統總控 (Orchestrator)，依序觸發：影像獲取 -> 實體分割 -> 語意分類 -> 空間入庫。
2. 管理各子模組之間的資料傳遞 (例如將 TIFF 路徑交給 SAM，將 GeoDataFrame 交給分類器)。
3. 實作全域錯誤處理機制，確保管線在任一節點失敗時能安全中斷，並回報明確的錯誤訊息給表現層。

維護提示：
此模組高度解耦。若未來需要抽換 AI 模型（例如將 SAM 升級為其他視覺基礎模型），或加入新的衛星資料源（如 Planet），只需在此處增修呼叫邏輯，無需改動底層核心。
"""

import sys
import os
import argparse
from typing import List, Tuple

# 動態將專案根目錄加入 Python 系統路徑
# 確保無論是透過 FastAPI 呼叫或直接在終端機執行，都能正確載入模組
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

# 匯入各功能模組
from data.sentinel_api_client import fetch_satellite_image
from data.nlsc_api_client import fetch_nlsc_image  
from data.database_manager import save_gdf_to_postgis

# 匯入 AI 引擎 (Ver 2.1)
from model.sam_processor import SAMHabitatSegmenter
from model.habitat_classifier import HabitatClassifier

# --- 全域配置區 ---
DEFAULT_BBOX = [121.450, 25.080, 121.460, 25.090] # 測試用預設 BBOX
TARGET_TABLE = "habitats"

def run_integration_pipeline(bbox: List[float], source: str = "sentinel", clear_old_data: bool = False) -> Tuple[bool, str]:
    """
    [Ver 2.1 終極版] 端到端 (End-to-End) 空間特徵萃取管線
    
    參數:
    - bbox: 分析範圍 [min_lon, min_lat, max_lon, max_lat] (EPSG:4326)
    - source: 影像來源 ("sentinel" 或 "nlsc")
    - clear_old_data: 寫入前是否強制清空資料庫中的舊有圖資
    
    回傳:
    - (成功與否布林值, 系統狀態訊息字串)
    """
    try:
        print(f"====== 🚀 啟動 {source.upper()} AI 空間分析管線 ======")
        print(f"[*] 分析範圍 (BBOX): {bbox}")
        
        # ---------------------------------------------------------
        # 步驟 1: 資料獲取 (Data Acquisition)
        # 根據指定來源，抓取涵蓋 BBOX 範圍的高解析度影像，並存為 GeoTIFF
        # ---------------------------------------------------------
        print(f"\n>>> 步驟 1: 獲取 {source.upper()} 影像")
        image_filename = f"data/temp_analysis_{source}.tif"
        
        if source == "sentinel":
            tif_path = fetch_satellite_image(bbox=bbox, output_filename=image_filename)
        elif source == "nlsc":
            tif_path = fetch_nlsc_image(bbox=bbox, output_filename=image_filename)
        else:
            return False, "不支援的影像來源，請指定 sentinel 或 nlsc"

        if not tif_path:
            return False, "無法取得影像資料，管線提前終止 (可能因雲覆蓋率過高或超出服務範圍)。"

        # ---------------------------------------------------------
        # 步驟 2: 實體分割 (Instance Segmentation)
        # 利用 Segment Anything Model 萃取影像中的純幾何輪廓，產出未分類的多邊形集合
        # ---------------------------------------------------------
        print("\n>>> 步驟 2: 啟動 SAM 實體分割 (Instance Segmentation)")
        segmenter = SAMHabitatSegmenter()
        sam_gdf = segmenter.process_image_to_polygons(tif_path)

        if len(sam_gdf) == 0:
            return False, "該範圍內未偵測到有效棲地邊界 (產出 0 個多邊形)。"

        # ---------------------------------------------------------
        # 步驟 3: 語意分類 (Semantic Classification)
        # 動態載入訓練底圖萃取光譜/紋理特徵，訓練 Random Forest 模型，並對剛才的輪廓進行屬性標註
        # ---------------------------------------------------------
        print("\n>>> 步驟 3: 啟動 Random Forest 語意分類 (Semantic Classification)")
        classifier = HabitatClassifier()
        
        # 指向專家標註檔 (Ground Truth) 位置
        training_data_path = os.path.join(project_root, "model", "data", "training_samples.gpkg") 
        
        # 動態抓取訓練用參考影像清單
        search_dir = os.path.join(project_root, "model", "data")
        reference_images = [
            os.path.join(search_dir, f) 
            for f in os.listdir(search_dir) 
            if f.startswith("habitat_sample_nlsc_") and f.endswith(".tif")
        ]
        
        print(f"[*] 成功偵測到 {len(reference_images)} 張參考影像用於訓練特徵萃取。")
        
        if len(reference_images) == 0:
            return False, "在 model/data/ 下找不到任何訓練底圖，無法建立分類模型。"
        
        # 啟動就地訓練 (Fit) 與推論 (Predict)
        classifier.train_from_samples(training_data_path, reference_images)
        final_gdf = classifier.predict(sam_gdf, tif_path)

        # ---------------------------------------------------------
        # 步驟 4: 幾何清洗與空間入庫 (Transform & Load)
        # 確保屬性表符合資料庫 Schema，並寫入 PostGIS
        # ---------------------------------------------------------
        print("\n>>> 步驟 4: 幾何轉換與 PostGIS 入庫")
        final_gdf['source'] = source 
        # 只保留資料庫所需欄位，並將預設幾何欄位重新命名為 'geom' 以匹配 SQLAlchemy 定義
        output_gdf = final_gdf[['habitat_type', 'source', 'geometry']].rename_geometry('geom')

        save_gdf_to_postgis(gdf=output_gdf, table_name=TARGET_TABLE, clear_old_data=clear_old_data)
        
        success_msg = f"分析成功！共產出 {len(output_gdf)} 個高精度棲地多邊形。"
        print(f"\n🎉 {success_msg}")
        return True, success_msg

    except Exception as e:
        error_msg = f"管線執行發生未預期錯誤: {e}"
        print(f"\n❌ {error_msg}")
        return False, error_msg

# 提供 CLI 執行入口，方便進行後端單元測試
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="執行 Ver 2.1 自動化分析管線")
    parser.add_argument("--source", type=str, choices=["sentinel", "nlsc"], default="nlsc", help="指定影像來源")
    args = parser.parse_args()
    
    success, msg = run_integration_pipeline(bbox=DEFAULT_BBOX, source=args.source)
    if not success:
        sys.exit(1)