import os
from dotenv import load_dotenv

# 🌟 核心改動：在讀取任何變數前，先載入 .env 檔案
# load_dotenv() 會尋找專案根目錄下的 .env 並將其內容載入系統環境變數
load_dotenv()


DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "your_password_here") 
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "postgres")

# 建構資料庫連線字串
SQLALCHEMY_DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# CORS 設定
ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "*"  # MVP 階段
]