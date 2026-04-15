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
    從 Planetary Computer 抓取 Sentinel-2 影像並裁切儲存。
    """
    print("[*] 正在連線至 Microsoft Planetary Computer...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    print("[*] 正在搜尋影像 (加入自動重試機制)...")
    max_retries = 3
    items = None
    
    for i in range(max_retries):
        try:
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime=date_range,
                query={"eo:cloud_cover": {"lt": 10}},
                max_items=1 
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
        print("[-] 找不到符合條件的影像。")
        return None

    selected_item = items[0]
    print(f"[+] 成功獲取影像！拍攝日期: {selected_item.datetime.date()}")

    image_url = selected_item.assets["visual"].href

    with rasterio.open(image_url) as src:
        native_crs = src.crs
        native_bbox = transform_bounds("EPSG:4326", native_crs, *bbox)
        window = from_bounds(*native_bbox, transform=src.transform)
        subset = src.read([1, 2, 3], window=window)

        if subset.shape[1] == 0 or subset.shape[2] == 0:
            print("[-] 裁切失敗：計算出的視窗大小為 0。請檢查 BBOX。")
            return None

        new_transform = src.window_transform(window)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": subset.shape[1],
            "width": subset.shape[2],
            "transform": new_transform,
            "crs": src.crs
        })

        with rasterio.open(output_filename, "w", **out_meta) as dest:
            dest.write(subset)
        
        filepath = os.path.abspath(output_filename)
        print(f"[+] 成功產出影像: {filepath}")
        return filepath

if __name__ == "__main__":
    # 單獨測試抓圖功能
    test_bbox = [120.701, 24.180, 120.711, 24.190]
    result_path = fetch_satellite_image(bbox=test_bbox)
    
    if result_path:
        with rasterio.open(result_path) as src:
            plt.figure(figsize=(8, 8))
            show(src.read(), title="Taichung Habitat Sample")
            plt.show()