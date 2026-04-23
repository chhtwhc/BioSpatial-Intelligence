"""
BioSpatial-Intelligence - 硬體環境與 GPU 加速檢測工具 (Environment Diagnostics)
檔案位置: test.py

模組用途：
1. 作為系統部署後的快速健康檢查 (Health Check) 腳本。
2. 驗證 PyTorch 是否能正確識別底層的 NVIDIA GPU 與 CUDA 驅動程式。
3. 輸出硬體規格 (顯卡型號與 VRAM 容量)，供維運人員評估是否能支撐高解析度的 SAM 影像切割。

維護提示：
若執行此腳本顯示 CUDA 不可用 (False)，請依次檢查：
1. 實體主機是否有 NVIDIA 顯示卡。
2. NVIDIA 驅動程式 (Driver) 是否已正確安裝 (可於終端機輸入 `nvidia-smi` 指令檢查)。
3. 安裝的 PyTorch 版本是否與系統的 CUDA 版本匹配 (請避免安裝到純 CPU 版本的 PyTorch)。
"""

import torch

def run_diagnostics():
    print("====== 🚀 BioSpatial-Intelligence 硬體環境診斷 ======")
    
    # 1. 檢查 CUDA 核心是否可用
    # 這項指標決定了 model/sam_processor.py 將使用 GPU (極快) 還是 CPU (極慢) 進行推論
    cuda_available = torch.cuda.is_available()
    print(f"[*] CUDA 硬體加速狀態: {'✅ 啟用 (可用)' if cuda_available else '❌ 未啟用 (不可用)'}")

    if cuda_available:
        # 2. 取得顯卡詳細資訊
        # 獲取第 0 張 (預設) 顯示卡的硬體名稱
        device_name = torch.cuda.get_device_name(0)
        
        # 獲取總顯示記憶體 (VRAM)，並轉換為 GB 單位
        # 效能評估標準：SAM 的 vit_h 模型至少需要約 8GB 以上的 VRAM，vit_b 則約需 4GB
        total_memory_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
        
        print(f"[+] 偵測到主要運算顯卡: {device_name}")
        print(f"[+] 顯卡記憶體 (VRAM) 總量: {total_memory_gb:.2f} GB")
        print("=====================================================")
        print("✅ 系統硬體已準備就緒，您可以安全地啟動 AI 空間分析管線。")
    else:
        print("[-] 警告：未能偵測到可用的 CUDA 環境。")
        print("    系統將強制降級使用 CPU 進行推論，這將導致分析耗時大幅增加。")
        print("    請確認是否已安裝正確的 NVIDIA 驅動程式與 PyTorch-CUDA 版本。")
        print("=====================================================")

if __name__ == "__main__":
    run_diagnostics()