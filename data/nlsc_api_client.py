"""
BioSpatial-Intelligence - 國土測繪中心 (NLSC) 航照影像獲取模組
檔案位置: data/nlsc_api_client.py

模組用途：
1. 介接內政部國土測繪中心 WMS 服務，自動抓取高解析度「臺灣通用正射影像 (PHOTO2)」。
2. 處理 WMS 服務的不穩定性，內建網路請求重試機制與錯誤回報。
3. 執行空間賦址 (Georeferencing)：將回傳的純 PNG 圖片，利用 Affine Transform 轉換為帶有空間參考 (EPSG:4326) 的 GeoTIFF 檔案。

維護提示：
NLSC 伺服器偶爾會進行維護或阻擋過於頻繁的請求。若未來遭遇連線頻繁拒絕 (HTTP 403/429)，可能需要在請求中加入適當的 User-Agent 或擴長等待時間 (time.sleep)。
"""

import os
import time
import requests
from typing import List, Optional
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from PIL import Image
from io import BytesIO

def fetch_nlsc_image(
    bbox: List[float], 
    output_filename: str = "data/habitat_sample_nlsc.tif",
    width: int = 1024,
    height: int = 1024
) -> Optional[str]:
    """
    從 NLSC WMS 服務獲取正射影像，並將其賦予空間座標存為 GeoTIFF。
    
    參數:
    - bbox: 分析範圍 [min_lon, min_lat, max_lon, max_lat] (EPSG:4326)。
    - output_filename: 輸出的 GeoTIFF 檔案路徑。
    - width/height: 請求回傳影像的像素解析度 (越大越精細，但也越耗頻寬)。
    
    回傳:
    - 成功時回傳檔案絕對路徑字串，失敗則回傳 None。
    """
    print("[*] 正在連線至 NLSC 國土測繪圖資服務雲 (WMS)...")
    wms_url = "https://maps.nlsc.gov.tw/S_Maps/wms"
    
    # 組合 OGC WMS 請求參數
    # 🌟 核心細節：這裡強制使用 VERSION 1.1.1，因為 1.3.0 版本的 CRS:84 / EPSG:4326 在某些伺服器實作上會要求 BBOX 為 (lat, lon) 順序。
    # 1.1.1 版本確保了我們傳入的 (min_lon, min_lat, max_lon, max_lat) 不會被伺服器誤判導致抓取到海上的空白圖。
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": "PHOTO2",  # 目標圖層：臺灣通用正射影像
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "WIDTH": width,
        "HEIGHT": height,
        "FORMAT": "image/png"
    }

    max_retries = 3
    img_data = None

    # 網路請求防護機制
    for i in range(max_retries):
        try:
            response = requests.get(wms_url, params=params, timeout=15)
            response.raise_for_status()
            
            # 防呆檢查：伺服器出錯時可能會回傳 XML 錯誤文件而非圖片。檢查 Content-Type 以防後續處理崩潰。
            if "image" not in response.headers.get("Content-Type", ""):
                print(f"[-] 伺服器回傳非影像格式，可能超出服務範圍、座標錯誤或系統維護中。")
                return None
                
            img_data = response.content
            break
        except Exception as e:
            print(f"[!] 第 {i+1} 次嘗試失敗，原因: {e}")
            if i < max_retries - 1:
                print("[*] 等待 5 秒後重試...")
                time.sleep(5)
            else:
                print("[-] 已達最大重試次數，無法取得 NLSC 影像。")
                return None

    if not img_data:
        return None

    print("[*] 成功獲取影像！準備轉換為帶有空間參考的 GeoTIFF...")
    
    try:
        # 將二進位資料讀取為 PIL 圖片，並強制轉換為 RGB (去除可能存在的透明通道 Alpha)
        img = Image.open(BytesIO(img_data)).convert("RGB")
        img_arr = np.array(img)
        
        # 轉換陣列維度：
        # PIL/OpenCV 預設格式為 (Height, Width, Bands)
        # Rasterio 寫入時嚴格要求格式為 (Bands, Height, Width)，故須進行軸置換 (Moveaxis)。
        img_arr = np.moveaxis(img_arr, -1, 0)
    except Exception as e:
        print(f"[-] 圖片解析失敗: {e}")
        return None

    # 核心空間運算：計算空間轉換矩陣 (Affine Transform)
    # 利用邊界座標與影像長寬，計算出「每個像素代表多少地理距離」，確保產出的 GeoTIFF 能疊加在正確的地圖位置上。
    transform = from_bounds(*bbox, width, height)

    os.makedirs(os.path.dirname(output_filename) or ".", exist_ok=True)

    try:
        # 將 Numpy 矩陣寫入硬碟，正式成為空間圖資
        with rasterio.open(
            output_filename,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=3,           # 波段數 (RGB = 3)
            dtype=img_arr.dtype,
            crs='EPSG:4326',   # 寫入系統法定座標系統
            transform=transform
        ) as dest:
            dest.write(img_arr)
            
        filepath = os.path.abspath(output_filename)
        print(f"[+] 成功產出 NLSC GeoTIFF 影像: {filepath}")
        return filepath
    except Exception as e:
        print(f"[-] 寫入 GeoTIFF 發生錯誤: {e}")
        return None

# 模組內部測試區塊
if __name__ == "__main__":
    # 單獨測試抓圖功能 (與 Sentinel 使用相同的臺中測試 BBOX)
    test_bbox = [121.517544,24.851316,121.574535,24.893677] 
    result_path = fetch_nlsc_image(bbox=test_bbox)
    
    if result_path:
        import matplotlib.pyplot as plt
        from rasterio.plot import show
        with rasterio.open(result_path) as src:
            plt.figure(figsize=(8, 8))
            # 視覺化時加入 transform 矩陣，讓圖表坐標軸顯示真實經緯度而非像素位置
            show(src.read(), title="NLSC Habitat Sample (PHOTO2)", transform=src.transform)
            plt.show()