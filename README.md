# BioSpatial-Intelligence (Ver 2.1)

本專案是一個整合「衛星/航照影像自動化獲取」、「AI 空間實體分割與語意分類」以及「動態 WebGIS 統計視覺化」的端到端生態空間監測系統。系統採用嚴謹的模組化三層架構，旨在解決生態檢核中人工辨識耗時、空間資料標準不一的核心痛點。

---

## 📂 專案目錄結構

BioSpatial-Intelligence/
├── api/                # 邏輯層 (Logic Tier): FastAPI 後端服務
│   ├── main.py         # API 路由、業務邏輯與分析觸發入口
│   ├── models.py       # SQLAlchemy 與 GeoAlchemy2 空間資料模型
│   └── schemas.py      # Pydantic 資料驗證與 GeoJSON 規範定義
├── data/               # 資料層 (Data Tier): 數據管線與外部介接
│   ├── main_pipeline.py# 自動化分析管線總控 (ETL Orchestrator)
│   ├── sentinel_api_client.py # Sentinel-2 衛星影像自動抓取
│   ├── nlsc_api_client.py     # NLSC 航照正射影像自動抓取
│   ├── image_processor.py     # 基礎影像處理與 K-Means 驗證工具
│   └── database_manager.py    # PostGIS 空間資料存取與維護管理
├── model/              # AI 模型層: 核心辨識引擎
│   ├── sam_processor.py      # Segment Anything Model 實體分割與拓樸平整化
│   └── habitat_classifier.py # Random Forest 棲地屬性語意分類
├── frontend/           # 表現層 (Presentation Tier): Leaflet 互動介面
├── init_db.py          # 資料庫初始化：啟用 PostGIS 與自動建表
└── .env                # 環境變數配置 (資料庫連線金鑰)

---

## 🏗️ 三層架構深度解析

### 1. 資料層 (Data Tier) - 系統的數據引擎
這是本系統最核心的自動化部分，負責處理從「原始光學數據」到「地理空間特徵」的轉化過程：
* 影像自動化獲取 (Automated Acquisition)：
    * Sentinel-2：透過 Microsoft Planetary Computer 介接，支援雲遮蔽率篩選與動態 BBOX 裁切。
    * NLSC (國土測繪中心)：利用 WMS 服務獲取 20cm/50cm 極高解析度正射影像。
* 全自動分析管線 (main_pipeline.py)：
    * 負責調度 Data Tier 的獲取模組與 Model Tier 的分析模組。
    * 實作完整的 ETL 流程：輸入座標 -> 影像下載 -> AI 分割/分類 -> 幾何清洗 -> 入庫 PostGIS。
* 空間資料庫管理 (database_manager.py)：
    * 確保所有產出的幾何物件均符合 EPSG:4326 標準。
    * 管理資料庫事務 (Transactions)，支援多邊形的 Append、Truncate 與 Reset 操作。

### 2. 邏輯層 (Logic Tier) - 空間運算核心
* FastAPI 驅動：提供高效能的非同步 API，供前端執行即時分析請求。
* 空間精確度運算：
    * 即時投影轉換：傳輸使用 WGS84，但計算面積時，後端會自動下達 ST_Transform(geom, 3826) 指令，轉為 TWD97 投影以符合台灣法定面積計算精確度。
    * 動態過濾：利用 PostGIS 的空間索引 (GIST) 實現高效的 BBOX 範圍查詢。

### 3. 表現層 (Presentation Tier) - 生態監測儀表板
* 動態 WebGIS：基於 Leaflet.js，支援多底圖切換（衛星影像/標準地圖）。
* 互動式分析：使用者可在地圖上框選區域，直接觸發後端 main_pipeline.py 的 AI 分析流程。
* 自動化統計：根據當前地圖視野，動態統計各棲地類型的面積（ha）與占比。

---

## 🤖 AI 推論鏈 (Model Tier)

系統整合了當前最強大的零樣本分割與經典機器學習技術：
1.  SAM (Segment Anything Model)：
    * 由 Meta 開發的基礎模型，執行實體分割。
    * 本系統實作了「畫家演算法 (Painter's Algorithm)」進行幾何平整化，解決遮罩重疊導致的面積重算問題。
2.  Random Forest 分類器：
    * 萃取區域內的多光譜均值 (Mean) 與標準差 (Std) 作為紋理特覽。
    * 自動標註「林地」、「水體」、「建物」、「裸露地」、「草生地」等五大類生態屬性。

---

## 📍 工程規範與標準

* 空間參考系統 (CRS)：
    * 存儲與 API 傳輸：EPSG:4326 (WGS84)。
    * 科學面積計算：EPSG:3826 (TWD97)。
* 環境規範：
    * 採用 venv 隔離開發環境，金鑰資訊嚴格保存於 .env 並透過 .gitignore 排除。

---

## 🚀 未來開發藍圖 (Ver 2.2)

本專案的下一個里程碑將聚焦於「線上應用程式化」：
* SaaS 化部署：將現有的三層架構容器化 (Dockerized)，部署至雲端服務 (如 GCP 或 AWS)。
* 全雲端操作：使用者只需透過瀏覽器，無需安裝任何本地開發環境或資料庫，即可在全球任何角落進行生態空間分析。
* 使用者帳戶體系：支援分析結果的雲端儲存與跨裝置同步。