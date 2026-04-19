import sys
import os
import argparse
from typing import List, Tuple

# 動態將當前 data/ 目錄加入 Python 系統路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from sentinel_api_client import fetch_satellite_image
from nlsc_api_client import fetch_nlsc_image  
from image_processor import process_image_to_polygons
from database_manager import save_gdf_to_postgis

# --- 配置區 ---
# 將原本寫死的 BBOX_TARGET 改為終端機測試用的預設值
DEFAULT_BBOX = [120.701, 24.180, 120.711, 24.190]
TARGET_TABLE = "habitats"

HABITAT_MAP = {
    0: "水體/河流", 
    1: "高植生/林地", 
    2: "都市建物/人造設施", 
    3: "裸露地/農田",
    4: "草生地"
}

def run_integration_pipeline(bbox: List[float], source: str = "sentinel", clear_old_data: bool = False) -> Tuple[bool, str]:
    """
    [Ver 2.1 修改] 接收動態 BBOX 並執行分析管線
    回傳值: (是否成功: bool, 系統訊息: str)
    """
    try:
        print(f"====== 🚀 啟動 {source.upper()} 動態 ROI 分析 ======")
        print(f"[*] 分析範圍 (BBOX): {bbox}")
        
        # 步驟 1: 取得衛星/航照影像
        print(f"\n>>> 步驟 1: 獲取 {source.upper()} 影像")
        if source == "sentinel":
            tif_path = fetch_satellite_image(bbox=bbox)
        elif source == "nlsc":
            tif_path = fetch_nlsc_image(bbox=bbox)
        else:
            return False, "不支援的影像來源"

        if not tif_path:
            return False, "無法取得影像資料，管線提前終止。"

        # 步驟 2: 影像分割與向量化
        print("\n>>> 步驟 2: 影像處理與向量化")
        gdf, _ = process_image_to_polygons(input_file=tif_path, k=4, min_area_sqm=200.0)

        # 防呆機制：如果畫的範圍太小或都是雜訊，導致沒有多邊形
        if len(gdf) == 0:
            return False, "該範圍內未偵測到符合條件的有效棲地 (產出 0 個多邊形)。"

        # 步驟 3: 資料清理與業務邏輯對應
        print("\n>>> 步驟 3: 屬性映射與清理")
        gdf['habitat_type'] = gdf['class_id'].map(HABITAT_MAP)
        gdf['source'] = source 
        output_gdf = gdf[['habitat_type', 'source', 'geometry']].rename_geometry('geom')

        # 步驟 4: 寫入資料庫
        print("\n>>> 步驟 4: 資料入庫")
        save_gdf_to_postgis(gdf=output_gdf, table_name=TARGET_TABLE, clear_old_data=clear_old_data)
        
        success_msg = f"分析成功！共產出 {len(output_gdf)} 個棲地多邊形。"
        print(f"\n🎉 {success_msg}")
        return True, success_msg

    except Exception as e:
        error_msg = f"管線執行發生未預期錯誤: {e}"
        print(f"\n❌ {error_msg}")
        return False, error_msg

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="執行多源影像處理至 PostGIS 的自動化管線")
    parser.add_argument("--reset", action="store_true", help="執行前清空資料庫中的舊資料表")
    parser.add_argument("--source", type=str, choices=["sentinel", "nlsc"], default="sentinel", help="選擇影像來源 (預設: sentinel)")
    args = parser.parse_args()
    
    # 向下相容：如果在終端機執行，自動代入 DEFAULT_BBOX 進行測試
    success, msg = run_integration_pipeline(
        bbox=DEFAULT_BBOX, 
        source=args.source,
        clear_old_data=args.reset 
    )
    
    if not success:
        sys.exit(1)