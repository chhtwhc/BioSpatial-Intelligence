import numpy as np
import geopandas as gpd
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

    def train_from_samples(self, sample_geojson_path: str, image_path: str):
        """讀取使用者在 QGIS 標註的真實資料來訓練模型"""
        print(f"[*] 載入真實訓練標註資料: {sample_geojson_path}")
        samples_gdf = gpd.read_file(sample_geojson_path)
        
        # 假設標註檔案中有一個欄位叫做 'class_id'
        y_train = samples_gdf['class_id'].values
        
        # ------------------ 第一處：訓練時的特徵萃取 ------------------
        print("[*] 正在萃取訓練樣本的光學與紋理特徵 (Mean + Std)...")
        stats_R = zonal_stats(samples_gdf, image_path, band=1, stats="mean std", nodata=0)
        stats_G = zonal_stats(samples_gdf, image_path, band=2, stats="mean std", nodata=0)
        stats_B = zonal_stats(samples_gdf, image_path, band=3, stats="mean std", nodata=0)

        features = []
        for r, g, b in zip(stats_R, stats_G, stats_B):
            r_mean = r['mean'] if r['mean'] is not None else 128
            g_mean = g['mean'] if g['mean'] is not None else 128
            b_mean = b['mean'] if b['mean'] is not None else 128
            
            r_std = r['std'] if r['std'] is not None else 0
            g_std = g['std'] if g['std'] is not None else 0
            b_std = b['std'] if b['std'] is not None else 0
            
            # 將 6 個特徵組合起來餵給模型
            features.append([r_mean, g_mean, b_mean, r_std, g_std, b_std])
        # --------------------------------------------------------------

        X_train = np.array(features)
        
        print("[*] 開始訓練隨機森林模型...")
        self.model.fit(X_train, y_train)
        print(f"[+] 訓練完成！模型已學習了 {len(X_train)} 筆真實地貌特徵 (包含紋理)。")

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