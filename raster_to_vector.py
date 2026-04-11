import pystac_client
import planetary_computer
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds  # 翻譯座標
import matplotlib.pyplot as plt
from rasterio.plot import show
import os
import time

def fetch_100ha_habitat_final():
    # 1. API 連線設定
    print("[*] 正在連線至 Microsoft Planetary Computer...")
    catalog = pystac_client.Client.open(
        "https://planetarycomputer.microsoft.com/api/stac/v1",
        modifier=planetary_computer.sign_inplace,
    )

    # 2. 定義 100 公頃範圍 (1km x 1km) - 旱溪都市交界處
    bbox = [120.701, 24.180, 120.711, 24.190]

    # 3. 執行搜尋 (加入重試邏輯)
    print("[*] 正在搜尋影像 (加入自動重試機制)...")
    
    max_retries = 3
    items = None
    
    for i in range(max_retries):
        try:
            search = catalog.search(
                collections=["sentinel-2-l2a"],
                bbox=bbox,
                datetime="2026-01-01/2026-04-12",
                query={"eo:cloud_cover": {"lt": 10}},
                max_items=1 # 只要找到一張就停下來
            )
            items = search.item_collection()
            if items: break
        
        except Exception as e:
            print(f"[!] 第 {i+1} 次嘗試失敗，原因: {e}")
            if i < max_retries - 1:
                print("[*] 等待 5 秒後重試...")
                time.sleep(10) # 稍微休息一下再發請求
            else:
                print("[-] 已達最大重試次數，請稍後再試。")
                return

    selected_item = items[0]
    print(f"[+] 成功獲取影像！拍攝日期: {selected_item.datetime.date()}")

    # 4. 讀取與處理影像
    image_url = selected_item.assets["visual"].href

    with rasterio.open(image_url) as src:
        # --- 🌟 核心修正：座標系對齊 ---
        native_crs = src.crs  # 獲取衛星圖的原生座標系 (通常是 UTM)
        print(f"[*] 影像原生座標系: {native_crs}")

        # 將我們的經緯度 BBOX 轉換為衛星圖的原生座標值 (公尺)
        native_bbox = transform_bounds("EPSG:4326", native_crs, *bbox)
        
        # 根據轉換後的座標，計算正確的像素視窗 (Window)
        window = from_bounds(*native_bbox, transform=src.transform)
        
        # 讀取影像資料 (RGB 三個頻道)
        subset = src.read([1, 2, 3], window=window)

        # 檢查是否成功讀取到內容
        if subset.shape[1] == 0 or subset.shape[2] == 0:
            print("[-] 裁切失敗：計算出的視窗大小為 0。請檢查 BBOX。")
            return

        print(f"[+] 成功裁切！影像維度: {subset.shape} (頻道, 高, 寬)")

        # 5. 更新地理中繼資料並存檔
        new_transform = src.window_transform(window)
        out_meta = src.meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": subset.shape[1],
            "width": subset.shape[2],
            "transform": new_transform,
            "crs": src.crs
        })

        output_filename = "habitat_sample_100ha.tif"
        with rasterio.open(output_filename, "w", **out_meta) as dest:
            dest.write(subset)
        
        print(f"[+] 資料夾已生成檔案: {os.path.abspath(output_filename)}")

    # 6. 畫圖確認
    plt.figure(figsize=(8, 8))
    show(subset, title=f"Taichung Habitat Sample ({selected_item.datetime.date()})")
    plt.show()

if __name__ == "__main__":
    fetch_100ha_habitat_final()