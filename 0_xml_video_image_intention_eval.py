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


def encode_image_to_base64(image_path: str) -> str:
    """
    将图片文件编码为base64字符串

    Args:
        image_path: 图片文件路径

    Returns:
        base64编码的字符串
    """
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')


def call_vision_api_for_video(video_path: str, file_name: str, api_url: str = "http://10.160.199.227:8033/v1/chat/completions") -> Optional[Dict[str, Any]]:
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

    # 加载视频系统提示词
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
            print(f"无法解析视频API响应为JSON格式，文件: {file_name}")
            print(f"响应内容: {full_response[:200]}...")
            return None

    except requests.exceptions.RequestException as e:
        print(f"视频API请求错误，文件: {file_name}, 错误: {e}")
        return None


def call_vision_api_for_image(image_path: str, file_name: str, api_url: str = "http://localhost:8018/v1/chat/completions", model_id: str = "qwen3-vl-instruct") -> Optional[Dict[str, Any]]:
    """
    调用视觉大模型API进行图片分析

    Args:
        image_path: 图片文件路径
        file_name: 文件名，用于日志记录
        api_url: API服务地址
        model_id: 模型ID

    Returns:
        解析结果字典
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }

    # 加载图片系统提示词
    system_prompt_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/xml_image_system_prompt.txt"
    system_prompt = load_system_prompt(system_prompt_path)

    # 将图片编码为base64
    image_base64 = encode_image_to_base64(image_path)

    payload = {
        "model": model_id,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": f"正在分析图片: {file_name}"
                    }
                ]
            }
        ],
        "stream": True,
        "temperature": 0.0
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, stream=True, timeout=120)
        if response.status_code != 200:
            print(f"  图片API错误状态码: {response.status_code}, 响应: {response.text[:500]}")
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
            print(f"无法解析图片API响应为JSON格式，文件: {file_name}")
            print(f"响应内容: {full_response[:200]}...")
            return None

    except requests.exceptions.RequestException as e:
        print(f"图片API请求错误，文件: {file_name}, 错误: {e}")
        return None


def merge_results(video_result: Dict[str, Any], image_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    融合视频和图片的解析结果

    融合规则：
    - 速度值、距离值以image提取的为准
    - 意图信息以image提取的为准
    - 其他信息综合考虑，如果image提取的信息非常明确则以image为准，
      否则以video提取的结果做辅助

    Args:
        video_result: 视频解析结果
        image_result: 图片解析结果

    Returns:
        融合后的结果
    """
    if not image_result:
        return video_result
    if not video_result:
        return image_result

    merged = {}

    # 基本信息层：直接使用image结果
    if "基本信息层" in image_result:
        merged["基本信息层"] = image_result["基本信息层"]
    elif "基本信息层" in video_result:
        merged["基本信息层"] = video_result["基本信息层"]

    # 场景环境层：直接使用image结果
    if "场景环境层" in image_result:
        merged["场景环境层"] = image_result["场景环境层"]
    elif "场景环境层" in video_result:
        merged["场景环境层"] = video_result["场景环境层"]

    # 参与者信息层：以image为准，video做补充
    merged["参与者信息层"] = _merge_participants(
        video_result.get("参与者信息层", []),
        image_result.get("参与者信息层", [])
    )

    # 行为语义层：意图相关以image为准，其他综合考虑
    merged["行为语义层"] = _merge_behavior_semantics(
        video_result.get("行为语义层", {}),
        image_result.get("行为语义层", {})
    )

    # 意图推理层：以image为准
    if "意图推理层" in image_result:
        merged["意图推理层"] = image_result["意图推理层"]
    elif "意图推理层" in video_result:
        merged["意图推理层"] = video_result["意图推理层"]

    return merged


def _merge_participants(video_participants: List[Dict], image_participants: List[Dict]) -> List[Dict]:
    """
    融合参与者信息层
    """
    if not image_participants:
        return video_participants
    if not video_participants:
        return image_participants

    merged_participants = []
    image_ids = {p.get("参与者ID") for p in image_participants if isinstance(p, dict)}

    # 首先添加image中明确识别的参与者
    for img_p in image_participants:
        if isinstance(img_p, dict):
            merged_participants.append(img_p)

    # 补充video中有但image中没有的参与者
    for vid_p in video_participants:
        if isinstance(vid_p, dict):
            vid_id = vid_p.get("参与者ID")
            if vid_id and vid_id not in image_ids:
                # 标记为推测信息
                vid_p_copy = vid_p.copy()
                if "信息类型" in vid_p_copy:
                    vid_p_copy["信息类型"] = "推测信息"
                merged_participants.append(vid_p_copy)

    return merged_participants


def _merge_behavior_semantics(video_behavior: Dict, image_behavior: Dict) -> Dict:
    """
    融合行为语义层
    """
    if not image_behavior:
        return video_behavior
    if not video_behavior:
        return image_behavior

    merged = {}

    # 主车动作序列：以image为准
    if "主车动作序列" in image_behavior:
        merged["主车动作序列"] = image_behavior["主车动作序列"]
    elif "主车动作序列" in video_behavior:
        merged["主车动作序列"] = video_behavior["主车动作序列"]

    # 他车他者动作序列：以image为准
    if "他车他者动作序列" in image_behavior:
        merged["他车他者动作序列"] = image_behavior["他车他者动作序列"]
    elif "他车他者动作序列" in video_behavior:
        merged["他车他者动作序列"] = video_behavior["他车他者动作序列"]

    # 触发条件：以image为准
    if "触发条件" in image_behavior:
        merged["触发条件"] = image_behavior["触发条件"]
    elif "触发条件" in video_behavior:
        merged["触发条件"] = video_behavior["触发条件"]

    # 时序关系：以image为准
    if "时序关系" in image_behavior:
        merged["时序关系"] = image_behavior["时序关系"]
    elif "时序关系" in video_behavior:
        merged["时序关系"] = video_behavior["时序关系"]

    # 终止条件：以image为准
    if "终止条件" in image_behavior:
        merged["终止条件"] = image_behavior["终止条件"]
    elif "终止条件" in video_behavior:
        merged["终止条件"] = video_behavior["终止条件"]

    # 约束条件：以image为准
    if "约束条件" in image_behavior:
        merged["约束条件"] = image_behavior["约束条件"]
    elif "约束条件" in video_behavior:
        merged["约束条件"] = video_behavior["约束条件"]

    return merged


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


def find_corresponding_png(mp4_path: str, image_base_path: str) -> Optional[str]:
    """
    根据mp4文件路径找到对应名称的png图片

    Args:
        mp4_path: mp4文件路径
        image_base_path: 图片基础路径

    Returns:
        对应的png文件路径，如果不存在则返回None
    """
    base_name = os.path.splitext(os.path.basename(mp4_path))[0]
    mp4_dir = os.path.dirname(mp4_path)
    # 相对路径
    rel_dir = os.path.relpath(mp4_dir, "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xosc_matched")
    png_path = os.path.join(image_base_path, rel_dir, f"{base_name}.png")

    if os.path.exists(png_path):
        return png_path
    return None


def main():
    # 设置基础路径
    video_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xosc_matched"
    image_base_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xml"

    if not os.path.exists(video_base_path):
        print(f"错误: 视频文件目录不存在 - {video_base_path}")
        return

    # 查找所有.mp4文件
    print("正在扫描MP4视频文件...")
    mp4_files = find_all_mp4_files(video_base_path)
    print(f"找到 {len(mp4_files)} 个MP4视频文件")

    # 统计处理成功的数量
    success_count = 0
    skip_count = 0
    fail_count = 0

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
                skip_count += 1
                continue

            # 查找对应的png图片
            png_path = find_corresponding_png(video_path, image_base_path)
            if not png_path:
                print(f"  未找到对应的PNG图片文件: {base_name}.png")
                fail_count += 1
                continue

            print(f"  对应图片: {png_path}")

            # 调用视觉大模型API进行视频分析
            print(f"  正在分析视频...")
            video_result = call_vision_api_for_video(video_path, file_name)

            # 调用视觉大模型API进行图片分析
            print(f"  正在分析图片...")
            image_result = call_vision_api_for_image(png_path, f"{base_name}.png")

            if video_result and image_result:
                # 融合视频和图片的结果
                merged_result = merge_results(video_result, image_result)

                # 保存结果到对应目录
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(merged_result, f, ensure_ascii=False, indent=2)

                print(f"  成功处理: {file_name} -> {json_filename}")
                success_count += 1
            elif video_result:
                # 只有视频结果时保存视频结果
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(video_result, f, ensure_ascii=False, indent=2)
                print(f"  部分成功(仅视频): {file_name} -> {json_filename}")
                success_count += 1
            elif image_result:
                # 只有图片结果时保存图片结果
                with open(json_output_path, 'w', encoding='utf-8') as f:
                    json.dump(image_result, f, ensure_ascii=False, indent=2)
                print(f"  部分成功(仅图片): {file_name} -> {json_filename}")
                success_count += 1
            else:
                print(f"  处理失败: {file_name}")
                fail_count += 1

            # 添加延迟以避免API请求过于频繁
            time.sleep(1)

        except Exception as e:
            print(f"  处理文件时出错 {video_path}: {e}")
            fail_count += 1

    print(f"\n处理完成!")
    print(f"成功处理: {success_count} 个")
    print(f"跳过: {skip_count} 个")
    print(f"失败: {fail_count} 个")
    print(f"共 {len(mp4_files)} 个文件")
    print(f"结果已保存到对应的目录中")


if __name__ == "__main__":
    main()
