import os
import json
import requests
from typing import Dict, Any, Optional


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


def call_llm_api(xml_code: str, api_url: str = "http://10.160.199.227:8006/v1/chat/completions") -> Optional[Dict[str, Any]]:
    """
    调用大模型API进行意图分析
    
    Args:
        xml_code: XML代码内容
        api_url: API服务地址
        
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
                "content": xml_code
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
            print("无法解析API响应为JSON格式")
            return None

    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        return None


def main():
    xosc_file_path = "/C20545/jeremyj/pro/volkswagen_demo/osc_converter_ui/esmini/CQU/CQU_0031.xosc"
    
    if not os.path.exists(xosc_file_path):
        print(f"错误: XOSC文件不存在 - {xosc_file_path}")
        return

    # 读取XOSC文件内容
    xml_code = load_xosc_content(xosc_file_path)
    
    # 调用大模型API进行意图分析
    result = call_llm_api(xml_code)
    
    if result:
        print("意图分析结果:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        # 保存结果到文件
        output_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/xml_intention_analysis_result.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {output_path}")
    else:
        print("API调用失败")


if __name__ == "__main__":
    main()