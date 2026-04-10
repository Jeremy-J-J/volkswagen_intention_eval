import json
import requests
from typing import Dict, Any, Optional, Union


def load_json_file(file_path: str) -> Dict[str, Any]:
    """
    读取JSON文件内容
    
    Args:
        file_path: JSON文件路径
        
    Returns:
        解析后的字典对象
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def call_llm_judgment(content1: str, content2: str, 
                     api_url: str = "http://10.160.199.227:8006/v1/chat/completions") -> bool:
    """
    调用大模型API判断两个内容是否表达相同意思
    
    Args:
        content1: 第一个内容
        content2: 第二个内容
        api_url: API服务地址
        
    Returns:
        判断结果，True表示一致，False表示不一致
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }
    
    system_prompt = """请严格判断以下两个内容是否表达相同的意思。
要求：
1. 仅当下列条件满足时才输出"是"：两个内容表达的含义完全相同或高度相似
2. 当两个内容表达不同的概念、数值或类别时，必须输出"否"
3. 特别注意：不同类型的概念（如"隧道"和"城市快速路"）应判断为"否"
4. 输出仅包含"是"或"否"，不要有其他解释文字。"""

    user_content = f"""请判断以下两个内容是否表达相同的意思：
内容1: {content1}
内容2: {content2}

请仅输出"是"或"否"："""
    
    payload = {
        "model": "holo-model",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": user_content
            }
        ],
        "temperature": 0.0
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result = response.json()
        # 提取大模型的判断结果
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            # 判断是否包含"是"字
            return "是" in content.strip() and "否" not in content.strip()
        else:
            print(f"API返回格式不正确: {result}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"请求错误: {e}")
        return False
    except Exception as e:
        print(f"解析API响应错误: {e}")
        return False


def normalize_content(content: Any) -> str:
    """
    将内容标准化为字符串形式，以便比较
    
    Args:
        content: 任意类型的内容
        
    Returns:
        标准化的字符串
    """
    if isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)
    elif isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False)
    else:
        return str(content)


def calculate_score(xml_file_path: str, osc_file_path: str) -> float:
    """
    计算XML和OSC意图分析结果的匹配得分
    
    Args:
        xml_file_path: XML意图分析结果文件路径
        osc_file_path: OSC意图分析结果文件路径
        
    Returns:
        匹配得分（百分比）
    """
    # 读取两个JSON文件
    xml_data = load_json_file(xml_file_path)
    osc_data = load_json_file(osc_file_path)
    
    # 统计变量
    total_valid_entries = 0  # 进入计分的总条目数
    positive_matches = 0     # 正确匹配的数量
    
    # 遍历XML数据，以XML为准进行匹配
    for layer_name, layer_content in xml_data.items():
        if layer_name not in osc_data:
            print(f"警告: OSC中缺少层级 '{layer_name}'")
            continue
            
        xml_layer = layer_content
        osc_layer = osc_data[layer_name]
        
        # 如果是列表类型的层级（如参与者信息层）
        if isinstance(xml_layer, list):
            # 按索引进行比较
            min_len = min(len(xml_layer), len(osc_layer))
            
            for i in range(min_len):
                xml_item = xml_layer[i]
                osc_item = osc_layer[i]
                
                # 遍历每个项目中的键
                for key in xml_item:
                    if key == "信息类型":
                        continue  # 信息类型单独处理
                        
                    if key not in osc_item:
                        continue  # OSC中没有这个键，跳过
                        
                    xml_info_type = xml_item.get("信息类型", "未涉及")
                    osc_info_type = osc_item.get("信息类型", "未涉及")
                    
                    # 规则1: 如果有一方为"未涉及"，则跳过该条
                    if xml_info_type == "未涉及" or osc_info_type == "未涉及":
                        continue
                    
                    # 进入正式计分
                    total_valid_entries += 1
                    
                    xml_content = normalize_content(xml_item[key])
                    osc_content = normalize_content(osc_item[key])
                    
                    # 情况一: 内容完全一致
                    if xml_content == osc_content:
                        positive_matches += 1
                        print(f"完全匹配: {key} - {xml_content}")
                    else:
                        # 情况二: 请求大模型判断一致性
                        print(f"请求大模型判断: {key}, XML: {xml_content}, OSC: {osc_content}")
                        if call_llm_judgment(xml_content, osc_content):
                            positive_matches += 1
                            print(f"大模型判断一致: {key}")
                        else:
                            print(f"大模型判断不一致: {key}")
        else:
            # 如果是字典类型的层级
            for key in xml_layer:
                if key not in osc_layer:
                    continue  # OSC中没有这个键，跳过
                
                xml_entry = xml_layer[key]
                osc_entry = osc_layer[key]
                
                xml_info_type = xml_entry.get("信息类型", "未涉及")
                osc_info_type = osc_entry.get("信息类型", "未涉及")
                
                # 规则1: 如果有一方为"未涉及"，则跳过该条
                if xml_info_type == "未涉及" or osc_info_type == "未涉及":
                    print(f"跳过未涉及项: {key}")
                    continue
                
                # 进入正式计分
                total_valid_entries += 1
                
                xml_content = normalize_content(xml_entry.get("内容", ""))
                osc_content = normalize_content(osc_entry.get("内容", ""))
                
                # 情况一: 内容完全一致
                if xml_content == osc_content:
                    positive_matches += 1
                    print(f"完全匹配: {key} - {xml_content}")
                else:
                    # 情况二: 请求大模型判断一致性
                    print(f"请求大模型判断: {key}, XML: {xml_content}, OSC: {osc_content}")
                    if call_llm_judgment(xml_content, osc_content):
                        positive_matches += 1
                        print(f"大模型判断一致: {key}")
                    else:
                        print(f"大模型判断不一致: {key}")
    
    # 计算最终得分
    if total_valid_entries == 0:
        print("没有找到有效的匹配项进行评分")
        return 0.0
    
    score = (positive_matches / total_valid_entries) * 100
    print(f"\n评分结果:")
    print(f"正例数量: {positive_matches}")
    print(f"总条目数: {total_valid_entries}")
    print(f"匹配得分: {score:.2f}%")
    
    return score


def main():
    xml_file_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/xml_intention_analysis_result.json"
    osc_file_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/osc_intention_analysis_result.json"
    
    print("开始计算XML和OSC意图分析结果的匹配得分...")
    score = calculate_score(xml_file_path, osc_file_path)
    print(f"最终匹配得分为: {score:.2f}%")


if __name__ == "__main__":
    main()