"""
BioSpatial-Intelligence - 系統組態中心 (Configuration Management)
檔案位置: api/config.py

模組用途：
1. 整合全域參數，包含資料庫連線字串、外部 API 授權碼及安全性配置。
2. 實作環境變數優先機制，支援從 .env 檔案或作業系統環境中自動載入配置。
3. 定義 CORS (跨來源資源共用) 政策，確保後端 API 僅與受信任的前端網域通訊。

維護提示：
1. 嚴禁在此檔案中直接寫入真實的生產環境密碼。應透過系統環境變數傳入。
2. 修改 ALLOWED_ORIGINS 時，請務必確認前端部署的 URL 是否已更新。
"""

import os
from pathlib import Path

# 定義專案根路徑，便於定位 local 儲存的影像與資料夾
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------
# 資料庫連線配置 (Database Connectivity)
# ---------------------------------------------------------

# 優先順序：系統環境變數 > 預設本地測試字串
# 格式：postgresql://[使用者]:[密碼]@[主機]:[埠號]/[資料庫名稱]
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:password@localhost:5432/biospatial_db"
)

# ---------------------------------------------------------
# 安全性與跨網域配置 (CORS Settings)
# ---------------------------------------------------------

# 允許存取本 API 的前端來源列表。
# 增加新網域時請確保包含通訊協定 (http/https) 與埠號。
ALLOWED_ORIGINS = [
    "http://localhost:5500",  # Live Server 預設開發埠
    "http://127.0.0.1:5500",
    "http://localhost:3000",  # React/Vue 常用的開發埠
]

# ---------------------------------------------------------
# 外部服務 API 金鑰 (External Service Keys)
# ---------------------------------------------------------

# Sentinel-2 衛星影像抓取授權 (需於 Copernicus Data Space 申請)
SENTINEL_USERNAME = os.getenv("SENTINEL_USERNAME", "your_username")
SENTINEL_PASSWORD = os.getenv("SENTINEL_PASSWORD", "your_password")

# 內政部 NLSC 圖資服務配置
# 此處保留擴充性，若未來 NLSC 改為付費授權或需 API Key 時於此填寫
NLSC_API_KEY = os.getenv("NLSC_API_KEY", "")

# ---------------------------------------------------------
# 影像處理參數 (Image Processing Parameters)
# ---------------------------------------------------------

# AI 分割模型 (SAM) 的路徑設定
# 模型權重檔案應放置於專案根目錄下的 models 夾內
SAM_CHECKPOINT_PATH = str(BASE_DIR / "models" / "sam_vit_h_4b8939.pth")
MODEL_TYPE = "vit_h" # 可依硬體效能切換 vit_l 或 vit_b

# 分析管線中間產物的儲存位置
TEMP_DATA_DIR = BASE_DIR / "data" / "temp"
os.makedirs(TEMP_DATA_DIR, exist_ok=True) # 自動偵測並建立資料夾