"""
BioSpatial-Intelligence - 棲地語意分類引擎 (Semantic Classification)
檔案位置: model/habitat_classifier.py

模組用途：
1. 負責讀取專家標註的 Ground Truth (如 GeoPackage)，建立訓練資料集。
2. 實作特徵工程 (Feature Engineering)：利用 rasterstats 萃取多邊形範圍內的光譜統計特徵 (均值、標準差)。
3. 訓練並調用 Random Forest 機器學習模型，為 SAM 產出的未知多邊形賦予生態類別 (如次生林、草生地)。

維護提示：
若未來光學影像加入近紅外光 (NIR) 波段，請務必在 _extract_features 函式中新增對應的 NDVI 計算特徵，以大幅提升植被分類準確度。
"""

import os
import numpy as np
import pandas as pd
import geopandas as gpd
from rasterstats import zonal_stats
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
import joblib
from typing import List, Union

class HabitatClassifier:
    def __init__(self, model_save_path: str = "models/rf_habitat_model.joblib"):
        """
        初始化隨機森林分類器。
        
        參數說明：
        - n_estimators=100：建立 100 棵決策樹進行多數決，平衡運算速度與準確度。
        - class_weight='balanced'：自動調整權重。在生態數據中，水體或裸地的樣本通常遠少於林地，此參數可避免模型過度偏袒大樣本類別。
        """
        self.model_save_path = model_save_path
        self.rf_model = RandomForestClassifier(
            n_estimators=100, 
            random_state=42, 
            class_weight='balanced',
            n_jobs=-1 # 啟用所有 CPU 核心進行平行運算
        )
        self.is_trained = False

    def _extract_features(self, gdf: gpd.GeoDataFrame, raster_path: str) -> pd.DataFrame:
        """
        核心特徵工程：分區統計 (Zonal Statistics)。
        將空間多邊形覆蓋在光柵影像上，計算每個多邊形內部的像素統計值，作為機器學習的 X (特徵)。
        """
        print(f"[*] 正在萃取影像特徵 (Zonal Stats): {os.path.basename(raster_path)}")
        
        # 提取統計特徵：均值 (反映主色調)、標準差 (反映紋理複雜度，例如樹冠層的標準差通常大於水體)
        # band_num=1通常代表 Red, 2=Green, 3=Blue (依 rasterio 讀取順序)
        stats = ['mean', 'std']
        
        feature_list = []
        for band in [1, 2, 3]:
            # rasterstats 會自動處理多邊形與像素網格的空間交集計算
            z_stats = zonal_stats(
                gdf, 
                raster_path, 
                stats=stats, 
                band=band, 
                nodata=0
            )
            # 將結果轉為 DataFrame，並重新命名欄位 (例如: b1_mean, b1_std)
            df_band = pd.DataFrame(z_stats).rename(
                columns={s: f'b{band}_{s}' for s in stats}
            )
            feature_list.append(df_band)
            
        # 將三個波段的特徵水平合併
        features_df = pd.concat(feature_list, axis=1)
        
        # 防呆機制：若多邊形太小 (小於一個像素)，zonal_stats 可能回傳 None，需補值避免模型報錯
        imputer = SimpleImputer(strategy='mean')
        features_df_imputed = pd.DataFrame(
            imputer.fit_transform(features_df), 
            columns=features_df.columns
        )
        
        return features_df_imputed

    def train_from_samples(self, ground_truth_path: str, raster_paths: Union[str, List[str]]) -> None:
        """
        讀取專家標註資料並訓練模型。若已有訓練好的模型則直接載入，以節省時間。
        """
        # 檢查是否已有訓練好的模型緩存
        if os.path.exists(self.model_save_path):
            print(f"[*] 偵測到已存在的模型權重，正在載入: {self.model_save_path}")
            self.rf_model = joblib.load(self.model_save_path)
            self.is_trained = True
            return

        print("[*] 啟動模型訓練流程...")
        # 確保輸入的 raster_paths 是一維陣列
        if isinstance(raster_paths, str):
            raster_paths = [raster_paths]

        # 載入 Ground Truth (通常為 GeoPackage 格式)
        gt_gdf = gpd.read_file(ground_truth_path)
        
        # 確保訓練資料也是標準 WGS84 投影
        if gt_gdf.crs != "EPSG:4326":
            gt_gdf = gt_gdf.to_crs("EPSG:4326")

        if 'habitat_type' not in gt_gdf.columns:
            raise ValueError("訓練資料必須包含 'habitat_type' (棲地類型) 欄位。")

        # 這裡簡化處理：假設所有訓練樣本都對應到第一張參考影像
        # 在更複雜的架構中，應針對每筆樣本記錄其對應的影像來源
        X = self._extract_features(gt_gdf, raster_paths[0])
        y = gt_gdf['habitat_type']

        print(f"[*] 正在擬合 (Fit) Random Forest 分類器，樣本數: {len(X)}")
        self.rf_model.fit(X, y)
        self.is_trained = True

        # 儲存模型以便未來直接調用
        os.makedirs(os.path.dirname(self.model_save_path) or ".", exist_ok=True)
        joblib.dump(self.rf_model, self.model_save_path)
        print("[+] 模型訓練完成並已儲存。")

    def predict(self, target_gdf: gpd.GeoDataFrame, raster_path: str) -> gpd.GeoDataFrame:
        """
        針對 SAM 切割出的未知多邊形，進行特徵萃取與分類推論。
        """
        if not self.is_trained:
            raise RuntimeError("模型尚未訓練！請先執行 train_from_samples()。")

        print("[*] 正在進行棲地語意推論 (Inference)...")
        
        # 1. 對目標多邊形提取特徵
        X_target = self._extract_features(target_gdf, raster_path)
        
        # 2. 執行分類預測
        predictions = self.rf_model.predict(X_target)
        
        # 3. 將預測結果寫回原始 GeoDataFrame
        result_gdf = target_gdf.copy()
        result_gdf['habitat_type'] = predictions
        
        print(f"[+] 推論完成！成功分類 {len(result_gdf)} 個實體。")
        return result_gdf