import os

# 資料庫設定：優先讀取環境變數，若無則提供本地開發的預設值（請勿在預設值放真實線上密碼）
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "Crazypig12345") # 建議本地開發用，上 GitHub 前切記透過 .env 覆蓋
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# CORS 設定
ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "*"  # MVP 階段預設全開
]