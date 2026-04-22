import os
import json
import requests
import time
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path


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


def encode_video_to_base64(video_path: str) -> str:
    """
    将视频文件编码为base64字符串

    Args:
        video_path: 视频文件路径

    Returns:
        base64编码的字符串
    """
    with open(video_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_vision_api(video_path: str, file_name: str, api_url: str = "http://10.160.199.227:8033/v1/chat/completions") -> Optional[Dict[str, Any]]:
    """
    调用视觉大模型API进行视频分析

    Args:
        video_path: 视频文件路径
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
    system_prompt_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/xml_video_system_prompt.txt"
    system_prompt = load_system_prompt(system_prompt_path)

    # 将视频编码为base64
    video_base64 = encode_video_to_base64(video_path)

    payload = {
        "model": "holo-model",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": f"正在分析视频: {file_name}"
                    }
                ]
            }
        ],
        "stream": True,
        "temperature": 0.0,
        "extra_body": {"top_k": 1}
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=300)
        if response.status_code != 200:
            print(f"  API错误状态码: {response.status_code}, 响应: {response.text[:500]}")
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


def find_all_mp4_files(base_path: str) -> List[str]:
    """
    递归查找指定路径下所有的.mp4文件

    Args:
        base_path: 基础路径

    Returns:
        所有.mp4文件路径列表
    """
    mp4_files = []
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.mp4'):
                mp4_files.append(os.path.join(root, file))
    return mp4_files


def main():
    # 设置视频文件基础路径
    video_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xosc_matched"

    if not os.path.exists(video_base_path):
        print(f"错误: 视频文件目录不存在 - {video_base_path}")
        return

    # 查找所有.mp4文件
    print("正在扫描MP4视频文件...")
    mp4_files = find_all_mp4_files(video_base_path)
    print(f"找到 {len(mp4_files)} 个MP4视频文件")

    # 统计处理成功的数量
    success_count = 0

    # 逐个处理每个视频文件
    for idx, video_path in enumerate(mp4_files):
        print(f"正在处理 ({idx + 1}/{len(mp4_files)}): {video_path}")

        try:
            # 获取文件名（不含路径）
            file_name = os.path.basename(video_path)

            # 构造对应的JSON文件名
            base_name = os.path.splitext(file_name)[0]
            json_filename = f"{base_name}.json"

            # 获取视频文件所在目录，用于保存对应的JSON结果
            video_dir = os.path.dirname(video_path)
            json_output_path = os.path.join(video_dir, json_filename)

            # 检查是否已存在处理结果
            if os.path.exists(json_output_path):
                print(f"  跳过已存在的文件: {json_filename}")
                continue

            # 调用视觉大模型API进行视频分析
            result = call_vision_api(video_path, file_name)

            if result:
                # 保存结果到对应目录
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                print(f"  成功处理: {file_name} -> {json_filename}")
                success_count += 1
            else:
                print(f"  处理失败: {file_name}")

            # 添加延迟以避免API请求过于频繁
            time.sleep(1)

        except Exception as e:
            print(f"  处理文件时出错 {video_path}: {e}")

    print(f"\n处理完成! 成功处理 {success_count} 个视频文件，共 {len(mp4_files)} 个文件")
    print(f"结果已保存到对应的目录中，文件添加了video标识后缀")


if __name__ == "__main__":
    main()