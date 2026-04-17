import sys
import argparse

from sentinel_api_client import fetch_satellite_image
# 新增匯入 NLSC 模組
from nlsc_api_client import fetch_nlsc_image  
from image_processor import process_image_to_polygons
from database_manager import save_gdf_to_postgis

# --- 配置區 ---
BBOX_TARGET = [120.701, 24.180, 120.711, 24.190]
TARGET_TABLE = "habitats"

HABITAT_MAP = {
    0: "水體/河流",
    1: "高植生/林地",
    2: "都市建物/人造設施",
    3: "裸露地/工地"
}

# 增加 source 參數
def run_integration_pipeline(clear_old_data: bool = False, source: str = "sentinel"):
    try:
        print(f"====== 🚀 啟動 {source.upper()} 棲地分析自動化管線 ======")
        
        # 步驟 1: 取得衛星/航照影像 (策略模式切換)
        print(f"\n>>> 步驟 1: 獲取 {source.upper()} 影像")
        if source == "sentinel":
            tif_path = fetch_satellite_image(bbox=BBOX_TARGET)
        elif source == "nlsc":
            tif_path = fetch_nlsc_image(bbox=BBOX_TARGET)
        else:
            print("[-] 錯誤的影像來源。")
            sys.exit(1)

        if not tif_path:
            print("[-] 無法取得影像，管線提前終止。")
            sys.exit(1)

        # 步驟 2: 影像分割與向量化
        print("\n>>> 步驟 2: 影像處理與向量化")
        # 影像處理器不需修改，因為兩者現在都會輸出標準 GeoTIFF
        gdf, _ = process_image_to_polygons(input_file=tif_path, k=4, min_area_sqm=200.0)

        # 步驟 3: 資料清理與業務邏輯對應
        print("\n>>> 步驟 3: 屬性映射與清理")
        gdf['habitat_type'] = gdf['class_id'].map(HABITAT_MAP)
        
        # 將 CLI 傳入的 source 參數寫入 DataFrame 中
        gdf['source'] = source
        
        output_gdf = gdf[['habitat_type', 'source', 'geometry']].rename_geometry('geom')

        # 步驟 4: 寫入資料庫
        print("\n>>> 步驟 4: 資料入庫")
        save_gdf_to_postgis(gdf=output_gdf, table_name=TARGET_TABLE, clear_old_data=clear_old_data)
        
        print("\n🎉 整合管線全部執行成功！")

    except Exception as e:
        print(f"\n❌ 管線執行發生未預期錯誤: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="執行多源影像處理至 PostGIS 的自動化管線")
    parser.add_argument("--reset", action="store_true", help="執行前清空資料庫中的舊資料表")
    # 新增 --source 參數，限制只能輸入 sentinel 或 nlsc
    parser.add_argument("--source", type=str, choices=["sentinel", "nlsc"], default="sentinel", help="選擇影像來源 (預設: sentinel)")
    args = parser.parse_args()
    
    run_integration_pipeline(clear_old_data=args.reset, source=args.source)