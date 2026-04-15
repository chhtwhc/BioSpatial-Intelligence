import sys
import argparse

# ⚠️ 修改點 1：因為這個腳本已經在 data/ 裡面，改用相對路徑匯入 (或同層直接匯入)
from sentinel_api_client import fetch_satellite_image
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

def run_integration_pipeline(clear_old_data: bool = False):
    try:
        print("====== 🚀 啟動 Sentinel 棲地分析自動化管線 ======")
        
        # 步驟 1: 取得衛星影像
        print("\n>>> 步驟 1: 獲取衛星圖")
        tif_path = fetch_satellite_image(bbox=BBOX_TARGET)
        if not tif_path:
            print("[-] 無法取得影像，管線提前終止。")
            sys.exit(1)

        # 步驟 2: 影像分割與向量化
        print("\n>>> 步驟 2: 影像處理與向量化")
        gdf, _ = process_image_to_polygons(input_file=tif_path, k=4, min_area_sqm=200.0)

        # 步驟 3: 資料清理與業務邏輯對應
        print("\n>>> 步驟 3: 屬性映射與清理")
        gdf['habitat_type'] = gdf['class_id'].map(HABITAT_MAP)
        # 只保留資料庫需要的欄位，並將幾何欄位重新命名為 'geom' 以符合 PostGIS 慣例
        output_gdf = gdf[['habitat_type', 'geometry']].rename_geometry('geom')

        # 步驟 4: 寫入資料庫
        print("\n>>> 步驟 4: 資料入庫")
        # ⚠️ 修改點 2：直接呼叫 save_gdf_to_postgis，讓它自己去抓預設的連線設定，並傳入清空參數
        save_gdf_to_postgis(gdf=output_gdf, table_name=TARGET_TABLE, clear_old_data=clear_old_data)
        
        print("\n🎉 整合管線全部執行成功！")

    except Exception as e:
        print(f"\n❌ 管線執行發生未預期錯誤: {e}")

if __name__ == "__main__":
    # ⚠️ 修改點 3：加入指令列參數，讓 PM 或開發者決定是否要清空舊資料
    parser = argparse.ArgumentParser(description="執行 Sentinel 影像處理至 PostGIS 的自動化管線")
    parser.add_argument("--reset", action="store_true", help="執行前清空資料庫中的舊資料表")
    args = parser.parse_args()
    
    run_integration_pipeline(clear_old_data=args.reset)