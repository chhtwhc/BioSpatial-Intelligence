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
    從內政部國土測繪中心 (NLSC) WMS 服務抓取正射影像並儲存為 GeoTIFF。
    """
    print("[*] 正在連線至 NLSC 國土測繪圖資服務雲 (WMS)...")
    wms_url = "https://maps.nlsc.gov.tw/S_Maps/wms"
    
    # 組合 WMS 請求參數 (使用 VERSION 1.1.1 確保 BBOX 為 lon,lat 順序)
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": "PHOTO2",  # 臺灣通用正射影像
        "STYLES": "",
        "SRS": "EPSG:4326",
        "BBOX": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
        "WIDTH": width,
        "HEIGHT": height,
        "FORMAT": "image/png"
    }

    max_retries = 3
    img_data = None

    for i in range(max_retries):
        try:
            response = requests.get(wms_url, params=params, timeout=15)
            response.raise_for_status()
            
            # 檢查回傳內容是否確實為影像 (防止伺服器回傳 XML 錯誤訊息)
            if "image" not in response.headers.get("Content-Type", ""):
                print(f"[-] 伺服器回傳非影像格式，可能超出範圍或服務異常。")
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
        # 讀取 PNG 圖片並轉為 numpy array
        img = Image.open(BytesIO(img_data)).convert("RGB")
        img_arr = np.array(img)
        # rasterio 寫入時需要 (bands, height, width) 格式
        img_arr = np.moveaxis(img_arr, -1, 0)
    except Exception as e:
        print(f"[-] 圖片解析失敗: {e}")
        return None

    # 核心邏輯：計算空間轉換矩陣 (Affine Transform)
    transform = from_bounds(*bbox, width, height)

    os.makedirs(os.path.dirname(output_filename) or ".", exist_ok=True)

    try:
        # 將 numpy array 寫入為符合系統規範的 GeoTIFF
        with rasterio.open(
            output_filename,
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=3,
            dtype=img_arr.dtype,
            crs='EPSG:4326',
            transform=transform
        ) as dest:
            dest.write(img_arr)
            
        filepath = os.path.abspath(output_filename)
        print(f"[+] 成功產出 NLSC GeoTIFF 影像: {filepath}")
        return filepath
    except Exception as e:
        print(f"[-] 寫入 GeoTIFF 發生錯誤: {e}")
        return None

if __name__ == "__main__":
    # 單獨測試抓圖功能 (與 Sentinel 使用相同的臺中測試 BBOX)
    test_bbox = [120.701, 24.180, 120.711, 24.190]
    result_path = fetch_nlsc_image(bbox=test_bbox)
    
    if result_path:
        import matplotlib.pyplot as plt
        from rasterio.plot import show
        with rasterio.open(result_path) as src:
            plt.figure(figsize=(8, 8))
            show(src.read(), title="NLSC Habitat Sample (PHOTO2)", transform=src.transform)
            plt.show()