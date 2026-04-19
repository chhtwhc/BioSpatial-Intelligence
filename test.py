import torch

# 檢查 CUDA 是否可用
cuda_available = torch.cuda.is_available()
print(f"CUDA 是否可用: {cuda_available}")

if cuda_available:
    # 取得顯卡名稱與目前顯存狀態
    print(f"偵測到顯卡: {torch.cuda.get_device_name(0)}")
    print(f"顯卡記憶體總量: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")