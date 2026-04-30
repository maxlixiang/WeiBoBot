import os
import json

def load_json(file_path, default_value):
    """读取 JSON 文件，如果不存在或报错则返回默认值"""
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"读取 JSON 文件失败: {file_path}: {e}")
    return default_value

def save_json(file_path, data):
    """将数据安全地保存为 JSON 文件"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
