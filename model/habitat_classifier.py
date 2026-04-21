import numpy as np
import geopandas as gpd
import os
from rasterstats import zonal_stats
from sklearn.ensemble import RandomForestClassifier

class HabitatClassifier:
    def __init__(self):
        print("[*] 正在初始化輕量棲地分類器 (Random Forest)...")
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        
        # 已包含新增的「草生地」
        self.target_names = {
            0: "水體/河流", 
            1: "高植生/林地", 
            2: "都市建物/人造設施", 
            3: "裸露地/工地",
            4: "草生地"
        }

    def train_from_samples(self, sample_geojson_path: str, image_paths):
        """讀取真實資料來訓練模型，全面支援「單一影像」或「多張影像清單」"""
        print(f"[*] 載入真實訓練標註資料: {sample_geojson_path}")
        samples_gdf = gpd.read_file(sample_geojson_path)
        
        # 系統防呆：如果傳進來的是單一字串，自動包裝成 List
        if isinstance(image_paths, str):
            image_paths = [image_paths]
            
        all_features = []
        all_labels = []
        
        print(f"[*] 準備從 {len(image_paths)} 張影像中萃取光學與紋理特徵...")
        
        # 遍歷所有的訓練底圖
        for img_path in image_paths:
            
            # 如果檔案不存在就跳過，避免整條管線中斷
            if not os.path.exists(img_path):
                print(f"  [!] 警告：找不到影像 {img_path}，已自動跳過。")
                continue
            
            print(f"  -> 正在處理底圖: {os.path.basename(img_path)}")
            stats_R = zonal_stats(samples_gdf, img_path, band=1, stats="mean std", nodata=0)
            stats_G = zonal_stats(samples_gdf, img_path, band=2, stats="mean std", nodata=0)
            stats_B = zonal_stats(samples_gdf, img_path, band=3, stats="mean std", nodata=0)

            # 逐一檢查每個多邊形
            for r, g, b, label in zip(stats_R, stats_G, stats_B, samples_gdf['class_id']):
                # 🌟 核心過濾器：如果 r['mean'] 不是 None，代表這個多邊形確實落在這張影像上！
                if r['mean'] is not None: 
                    r_mean = r['mean']
                    r_std = r['std'] if r['std'] is not None else 0
                    g_mean = g['mean']
                    g_std = g['std'] if g['std'] is not None else 0
                    b_mean = b['mean']
                    b_std = b['std'] if b['std'] is not None else 0
                    
                    all_features.append([r_mean, g_mean, b_mean, r_std, g_std, b_std])
                    all_labels.append(label)

        X_train = np.array(all_features)
        y_train = np.array(all_labels)
        
        print(f"[*] 開始訓練隨機森林模型 (有效訓練樣本數: {len(X_train)})...")
        self.model.fit(X_train, y_train)
        print("[+] 訓練完成！模型已成功吸收所有區域的地貌特徵。")

    def predict(self, gdf: gpd.GeoDataFrame, image_path: str) -> gpd.GeoDataFrame:
        """接收 SAM 產出的 GeoDataFrame，萃取影像特徵並進行分類"""
        
        # ------------------ 第二處：預測時的特徵萃取 ------------------
        # 注意這裡使用的是 SAM 傳進來的 'gdf'
        print("[*] 正在對 SAM 產生的多邊形進行特徵萃取 (Mean + Std)...")
        stats_R = zonal_stats(gdf, image_path, band=1, stats="mean std", nodata=0)
        stats_G = zonal_stats(gdf, image_path, band=2, stats="mean std", nodata=0)
        stats_B = zonal_stats(gdf, image_path, band=3, stats="mean std", nodata=0)

        features = []
        for r, g, b in zip(stats_R, stats_G, stats_B):
            r_mean = r['mean'] if r['mean'] is not None else 128
            g_mean = g['mean'] if g['mean'] is not None else 128
            b_mean = b['mean'] if b['mean'] is not None else 128
            
            r_std = r['std'] if r['std'] is not None else 0
            g_std = g['std'] if g['std'] is not None else 0
            b_std = b['std'] if b['std'] is not None else 0
            
            features.append([r_mean, g_mean, b_mean, r_std, g_std, b_std])
        # --------------------------------------------------------------

        X_predict = np.array(features)
        
        print("[*] 正在執行語意分類預測...")
        predictions = self.model.predict(X_predict)
        
        gdf['habitat_type'] = [self.target_names[p] for p in predictions]
        print(f"[+] 分類完成！共標註了 {len(gdf)} 個棲地屬性。")
        return gdf