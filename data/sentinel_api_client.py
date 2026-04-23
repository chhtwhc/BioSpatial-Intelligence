"""
BioSpatial-Intelligence - Sentinel-2 衛星影像獲取模組
檔案位置: data/sentinel_api_client.py

模組用途：
1. 介接 Microsoft Planetary Computer STAC API，自動搜尋指定時間與空間範圍內的 Sentinel-2 L2A 影像。
2. 執行自動化過濾，排除雲遮蔽率 (Cloud Cover) 高於 10% 的劣質影像。
3. 利用 Rasterio 實作「視窗裁切 (Windowed Reading)」，僅下載 BBOX 範圍內的像素，節省頻寬與記憶體。

維護提示：
若未來需要更改光譜波段 (例如加入近紅外光 NIR 進行 NDVI 計算)，需修改 subset = src.read([...]) 的波段索引。
"""

import os
import time
from typing import List, Optional

import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds
import matplotlib.pyplot as plt
from rasterio.plot import show

def fetch_satellite_image(
    bbox: List[float], 
    date_range: str = "2026-01-01/2026-04-12",
    output_filename: str = "data/habitat_sample_100ha.tif" # 強制存入 data/ 內
) -> Optional[str]:
    """
    從雲端 STAC 目錄獲取並裁切 Sentinel-2 影像。
    
    參數:
    - bbox: 分析範圍 [min_lon, min_lat, max_lon, max_lat] (必須為 EPSG:4326 經緯度)
    - date_range: 搜尋的時間區間，格式為 "YYYY-MM-DD/YYYY-MM-DD"
    - output_filename: 輸出的 GeoTIFF 檔案路徑
    
    回傳:
    - 成功時回傳檔案絕對路徑字串，失敗則回傳 None。
    """
    print("[*] 正在連線至 Microsoft Planetary Computer STAC API...")
    
    # 建立 STAC 客戶端，並使用 planetary_computer 提供的修飾器自動處理存取權杖 (Token)
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    print("[*] 正在搜尋影像 (加入自動重試機制以應對網路不穩)...")
    max_retries = 3
    items = None
    
    # 網路重試機制：確保在呼叫外部 API 遇到短暫斷線時不會直接崩潰
    for i in range(max_retries):
        try:
            # 建構 STAC 查詢條件
            search = catalog.search(
                collections=["sentinel-2-l2a"], # L2A 代表已完成大氣校正的底層地表反射率產品
                bbox=bbox,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": 10}}, # 核心過濾器：要求雲量少於 10% (lt = less than)
                max_items=1 # 只取最新或最符合條件的第一張
            )
            items = search.item_collection()
            if items: 
                break
        except Exception as e:
            print(f"[!] 第 {i+1} 次嘗試失敗，原因: {e}")
            if i < max_retries - 1:
                print("[*] 等待 10 秒後重試...")
                time.sleep(10)
            else:
                print("[-] 已達最大重試次數，請稍後再試。")
                return None

    if not items:
        print("[-] 找不到符合條件的影像 (可能該區間全被雲層遮蔽)。")
        return None

    selected_item = items[0]
    print(f"[+] 成功獲取影像中繼資料！拍攝日期: {selected_item.datetime.date()}")

    # 取得真色彩 (Visual, RGB) 波段的雲端 COG (Cloud Optimized GeoTIFF) 連結
    image_url = selected_item.assets["visual"].href

    # 核心邏輯：空間視窗裁切 (Windowed Reading)
    with rasterio.open(image_url) as src:
        native_crs = src.crs # 取得影像原生的投影座標系統 (通常是 UTM 投影)
        
        # 步驟 1：投影轉換。將我們傳入的經緯度 (EPSG:4326) 轉換為影像所在的 UTM 座標範圍
        native_bbox = transform_bounds("EPSG:4326", native_crs, *bbox)
        
        # 步驟 2：計算讀取視窗。告知 Rasterio 只讀取該 BBOX 範圍內的像素矩陣
        window = from_bounds(*native_bbox, transform=src.transform)
        
        # 步驟 3：執行讀取。[1, 2, 3] 對應 R, G, B 波段
        subset = src.read([1, 2, 3], window=window)

        # 防呆機制：若計算出的像素長寬為 0，代表 BBOX 超出影像邊界
        if subset.shape[1] == 0 or subset.shape[2] == 0:
            print("[-] 裁切失敗：計算出的視窗大小為 0。請檢查 BBOX 是否正確。")
            return None

        # 更新中繼資料 (Metadata)，以便正確寫入新的 GeoTIFF
        new_transform = src.window_transform(window)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": subset.shape[1],
            "width": subset.shape[2],
            "transform": new_transform,
            "crs": src.crs
        })

        # 將裁切後的矩陣儲存至本地端
        with rasterio.open(output_filename, "w", **out_meta) as dest:
            dest.write(subset)
        
        filepath = os.path.abspath(output_filename)
        print(f"[+] 成功產出影像: {filepath}")
        return filepath

# 模組內部測試區塊
if __name__ == "__main__":
    # 單獨測試抓圖功能 (預設為台中市區一小塊範圍)
    test_bbox = [120.701, 24.180, 120.711, 24.190]
    result_path = fetch_satellite_image(bbox=test_bbox)
    
    if result_path:
        with rasterio.open(result_path) as src:
            plt.figure(figsize=(8, 8))
            show(src.read(), title="Taichung Habitat Sample")
            plt.show()