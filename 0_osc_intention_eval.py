import os
import json
import requests
import time
from typing import Dict, Any, Optional, List
from pathlib import Path


def load_osc_content(file_path: str) -> str:
    """
    读取OSC文件内容
    
    Args:
        file_path: OSC文件路径
        
    Returns:
        文件内容字符串
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def load_system_prompt(file_path: str) -> str:
    """
    读取系统提示词内容
    
    Args:
        file_path: 系统提示词文件路径
        
    Returns:
        系统提示词字符串
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()


def call_llm_api(dsl_code: str, file_name: str, api_url: str = "http://10.160.199.227:8006/v1/chat/completions") -> Optional[Dict[str, Any]]:
    """
    调用大模型API进行意图分析
    
    Args:
        dsl_code: DSL代码内容
        file_name: 文件名，用于日志记录
        api_url: API服务地址
        
    Returns:
        解析结果字典
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }
    
    # 加载系统提示词
    system_prompt_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/osc_system_prompt.txt"
    system_prompt = load_system_prompt(system_prompt_path)
    
    payload = {
        "model": "holo-model",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"正在分析文件: {file_name}\n\nDSL代码:\n{dsl_code}"
            }
        ],
        "stream": True,
        "temperature": 0.0,
        "extra_body": {"top_k": 1}
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True)
        response.raise_for_status()

        full_response = ""
        for chunk in response.iter_lines(decode_unicode=True):
            if chunk:
                # 处理流式响应
                chunk_str = chunk.strip()
                if chunk_str.startswith("data: "):
                    chunk_data = chunk_str[6:]  # Remove "data: " prefix
                    if chunk_data == "[DONE]":
                        break
                    try:
                        json_chunk = json.loads(chunk_data)
                        if "choices" in json_chunk and len(json_chunk["choices"]) > 0:
                            delta = json_chunk["choices"][0].get("delta", {})
                            content = delta.get("content", "")
                            full_response += content
                    except json.JSONDecodeError:
                        continue

        # 尝试解析完整的JSON响应
        try:
            # 从完整响应中提取JSON部分
            start_idx = full_response.find('{')
            end_idx = full_response.rfind('}')
            if start_idx != -1 and end_idx != -1:
                json_str = full_response[start_idx:end_idx+1]
                result = json.loads(json_str)
                return result
        except json.JSONDecodeError:
            print(f"无法解析API响应为JSON格式，文件: {file_name}")
            print(f"响应内容: {full_response[:200]}...")
            return None

    except requests.exceptions.RequestException as e:
        print(f"请求错误，文件: {file_name}, 错误: {e}")
        return None


def find_all_osc_files(base_path: str) -> List[str]:
    """
    递归查找指定路径下所有的.osc文件
    
    Args:
        base_path: 基础路径
        
    Returns:
        所有.osc文件路径列表
    """
    osc_files = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.osc'):
                osc_files.append(os.path.join(root, file))
    return osc_files


def main():
    # 设置OSC文件基础路径
    # osc_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/01_法规测试场景/法规测试_osc"
    osc_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS-osc-0416"
    # osc_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/CQU/v1.7.0/osc_output"
    
    if not os.path.exists(osc_base_path):
        print(f"错误: OSC文件目录不存在 - {osc_base_path}")
        return

    # 查找所有.osc文件
    print("正在扫描OSC文件...")
    osc_files = find_all_osc_files(osc_base_path)
    print(f"找到 {len(osc_files)} 个OSC文件")

    # 统计处理成功的数量
    success_count = 0
    skip_count = 0

    # 逐个处理每个OSC文件
    for idx, osc_file_path in enumerate(osc_files):
        # 获取文件名（不含路径）
        file_name = os.path.basename(osc_file_path)
        # 构造对应的JSON文件名
        json_filename = file_name.replace('.osc', '.json')
        # 获取OSC文件所在目录，用于保存对应的JSON结果
        osc_dir = os.path.dirname(osc_file_path)
        json_output_path = os.path.join(osc_dir, json_filename)

        # 如果JSON结果文件已存在，跳过
        if os.path.exists(json_output_path):
            print(f"跳过 ({idx + 1}/{len(osc_files)}): {file_name} (已存在)")
            skip_count += 1
            continue

        print(f"正在处理 ({idx + 1}/{len(osc_files)}): {osc_file_path}")

        try:
            # 读取OSC文件内容
            dsl_code = load_osc_content(osc_file_path)
            
            # 调用大模型API进行意图分析
            result = call_llm_api(dsl_code, file_name)
            
            if result:
                # 不再添加文件路径信息到结果中，直接保存原始结果
                # 保存结果到对应目录，使用同名JSON文件
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                
                print(f"✓ 成功处理: {file_name} -> {json_filename}")
                success_count += 1
            else:
                print(f"✗ 处理失败: {file_name}")

            # 添加延迟以避免API请求过于频繁
            time.sleep(1)

        except Exception as e:
            print(f"✗ 处理文件时出错 {osc_file_path}: {e}")

    print(f"\n处理完成! 成功处理 {success_count} 个OSC文件，跳过 {skip_count} 个已存在文件，共 {len(osc_files)} 个文件")
    print(f"结果已保存到对应的目录中，与原始.osc文件同名")


if __name__ == "__main__":
    main()