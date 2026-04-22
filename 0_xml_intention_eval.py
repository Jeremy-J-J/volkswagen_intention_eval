import os
import json
import requests
import time
import re
from typing import Dict, Any, Optional, List
from pathlib import Path


def load_xosc_content(file_path: str) -> str:
    """
    读取XOSC文件内容
    
    Args:
        file_path: XOSC文件路径
        
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


def extract_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    从响应文本中提取JSON部分
    
    Args:
        response_text: 响应文本
        
    Returns:
        解析后的JSON对象，如果失败则返回None
    """
    # 尝试直接解析整个响应
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        pass

    # 寻找第一个和最后一个大括号
    start_idx = response_text.find('{')
    end_idx = response_text.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
        json_str = response_text[start_idx:end_idx+1]
        try:
            # 尝试解析提取的JSON部分
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
            
        # 如果仍然失败，尝试修复常见的JSON问题
        try:
            # 尝试修复不完整的JSON
            fixed_json_str = json_str
            # 修复可能的问题，比如多余的逗号等
            fixed_json_str = re.sub(r',(\s*[}\]])', r'\1', fixed_json_str)  # 移除末尾逗号
            return json.loads(fixed_json_str)
        except json.JSONDecodeError:
            pass
    
    return None


def call_llm_api(xml_code: str, file_name: str, api_url: str = "http://10.160.199.227:8006/v1/chat/completions", max_retries: int = 1) -> Optional[Dict[str, Any]]:
    """
    调用大模型API进行意图分析
    
    Args:
        xml_code: XML代码内容
        file_name: 文件名，用于日志记录
        api_url: API服务地址
        max_retries: 最大重试次数
        
    Returns:
        解析结果字典
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }
    
    # 加载系统提示词
    system_prompt_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/xml_system_prompt.txt"
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
                "content": f"正在分析文件: {file_name}\n\nXML代码:\n{xml_code}"
            }
        ],
        "stream": True,
        "temperature": 0.0,
        "max_tokens": 8192,
        "extra_body": {"top_k": 1}
    }

    # 尝试多次请求直到成功或达到最大重试次数
    for attempt in range(max_retries + 1):
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
            result = extract_json_from_response(full_response)
            if result:
                return result
            else:
                print(f"无法解析API响应为JSON格式，文件: {file_name}")
                print(f"响应内容: {full_response}...")  # 只打印前500个字符
                if attempt < max_retries:
                    print(f"第{attempt + 1}次尝试失败，准备重试...")
                    time.sleep(2)  # 重试前等待2秒
                else:
                    print(f"已达到最大重试次数({max_retries + 1})，放弃处理文件: {file_name}")
                    
        except requests.exceptions.RequestException as e:
            print(f"请求错误，文件: {file_name}, 错误: {e}")
            if attempt < max_retries:
                print(f"第{attempt + 1}次尝试失败，准备重试...")
                time.sleep(2)  # 重试前等待2秒
            else:
                print(f"已达到最大重试次数({max_retries + 1})，放弃处理文件: {file_name}")
    
    return None


def find_all_xosc_files(base_path: str) -> List[str]:
    """
    递归查找指定路径下所有的.xosc文件
    
    Args:
        base_path: 基础路径
        
    Returns:
        所有.xosc文件路径列表
    """
    xosc_files = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.xosc'):
                xosc_files.append(os.path.join(root, file))
    return xosc_files


def main():
    # 设置XOSC文件基础路径
    xosc_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/CQU/CQU_xml"
    
    if not os.path.exists(xosc_base_path):
        print(f"错误: XOSC文件目录不存在 - {xosc_base_path}")
        return

    # 查找所有.xosc文件
    print("正在扫描XOSC文件...")
    xosc_files = find_all_xosc_files(xosc_base_path)
    print(f"找到 {len(xosc_files)} 个XOSC文件")

    # 统计处理成功的数量
    success_count = 0
    skipped_count = 0

    # 逐个处理每个XOSC文件
    for idx, xosc_file_path in enumerate(xosc_files):
        # 获取文件名（不含路径）
        file_name = os.path.basename(xosc_file_path)
        # 构造对应的JSON文件名
        json_filename = file_name.replace('.xosc', '.json')
        
        # 获取XOSC文件所在目录，用于保存对应的JSON结果
        xosc_dir = os.path.dirname(xosc_file_path)
        json_output_path = os.path.join(xosc_dir, json_filename)
        
        # 检查是否已存在同名JSON文件
        if os.path.exists(json_output_path):
            print(f"跳过 ({idx + 1}/{len(xosc_files)}): {file_name} (已存在)")
            skipped_count += 1
            continue
        
        print(f"正在处理 ({idx + 1}/{len(xosc_files)}): {xosc_file_path}")
        
        try:
            # 读取XOSC文件内容
            xml_code = load_xosc_content(xosc_file_path)
            
            # 调用大模型API进行意图分析（最多重试1次）
            result = call_llm_api(xml_code, file_name)
            
            if result:
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
            print(f"✗ 处理文件时出错 {xosc_file_path}: {e}")

    print(f"\n处理完成! 成功处理 {success_count} 个XOSC文件，跳过 {skipped_count} 个已存在结果的文件，共 {len(xosc_files)} 个文件")
    print(f"结果已保存到对应的目录中，与原始.xosc文件同名")


if __name__ == "__main__":
    main()