import os
import json
import requests
import io
import sys
from typing import Dict, Any, Optional, Union, List
import glob


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


def calculate_score_with_log(xml_file_path: str, osc_file_path: str) -> tuple[float, List[str]]:
    """
    计算XML和OSC意图分析结果的匹配得分，并记录详细过程日志
    
    Args:
        xml_file_path: XML意图分析结果文件路径
        osc_file_path: OSC意图分析结果文件路径
        
    Returns:
        元组，包含匹配得分（百分比）和处理日志列表
    """
    # 创建一个StringIO对象来捕获print输出
    log_capture = io.StringIO()
    
    # 重定向stdout到log_capture
    old_stdout = sys.stdout
    sys.stdout = log_capture
    
    try:
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
                            judgment_request_msg = f"请求大模型判断: {key}, XML: {xml_content}, OSC: {osc_content}"
                            print(judgment_request_msg)
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
                        judgment_request_msg = f"请求大模型判断: {key}, XML: {xml_content}, OSC: {osc_content}"
                        print(judgment_request_msg)
                        if call_llm_judgment(xml_content, osc_content):
                            positive_matches += 1
                            print(f"大模型判断一致: {key}")
                        else:
                            print(f"大模型判断不一致: {key}")
        
        # 计算最终得分
        if total_valid_entries == 0:
            print("没有找到有效的匹配项进行评分")
            score = 0.0
        else:
            score = (positive_matches / total_valid_entries) * 100
            print(f"\n评分结果:")
            print(f"正例数量: {positive_matches}")
            print(f"总条目数: {total_valid_entries}")
            print(f"匹配得分: {score:.2f}%")
        
        # 获取捕获的日志
        log_content = log_capture.getvalue()
        log_lines = log_content.splitlines()
        
        # 合并相关的日志条目
        merged_logs = []
        i = 0
        while i < len(log_lines):
            line = log_lines[i].strip()
            if not line:  # 跳过空行
                i += 1
                continue
                
            # 如果是"请求大模型判断"的日志，尝试与下一行合并
            if line.startswith("请求大模型判断:") and i + 1 < len(log_lines):
                next_line = log_lines[i + 1].strip()
                if next_line.startswith("大模型判断一致:") or next_line.startswith("大模型判断不一致:"):
                    # 合并这两行
                    merged_line = f"{line} | {next_line}"
                    merged_logs.append(merged_line)
                    i += 2  # 跳过这两行
                    continue
            
            # 添加当前行
            merged_logs.append(line)
            i += 1
        
        return score, merged_logs
    finally:
        # 恢复原来的stdout
        sys.stdout = old_stdout


def find_matching_files(osc_base_path: str, xosc_base_path: str) -> List[Dict[str, str]]:
    """
    查找匹配的.osc和.xosc文件对
    
    Args:
        osc_base_path: osc文件根目录
        xosc_base_path: xosc文件根目录
        
    Returns:
        包含匹配文件对的列表
    """
    matching_pairs = []
    
    # 遍历osc目录下的所有子目录
    for root, dirs, files in os.walk(osc_base_path):
        # 获取相对于osc_base_path的相对路径
        rel_path = os.path.relpath(root, osc_base_path)
        
        # 构造xosc对应的目录路径
        xosc_dir = os.path.join(xosc_base_path, rel_path)
        
        if not os.path.exists(xosc_dir):
            print(f"警告: 对应的xosc目录不存在: {xosc_dir}")
            continue
            
        # 获取所有.osc文件
        osc_files = [f for f in files if f.endswith('.osc')]
        
        # 遍历.osc文件，查找对应的.xosc文件
        for osc_file in osc_files:
            base_name = osc_file[:-4]  # 去掉.osc扩展名
            xosc_file = base_name + '.xosc'
            
            osc_full_path = os.path.join(root, osc_file)
            xosc_full_path = os.path.join(xosc_dir, xosc_file)
            
            # 查找对应的JSON文件
            json_file = base_name + '.json'
            json_full_path = os.path.join(root, json_file)
            xosc_json_full_path = os.path.join(xosc_dir, json_file)
            
            if os.path.exists(xosc_full_path) and os.path.exists(json_full_path) and os.path.exists(xosc_json_full_path):
                # 添加JSON文件对进行评分
                matching_pairs.append({
                    'name': base_name,
                    'osc_json_path': json_full_path,
                    'xosc_json_path': xosc_json_full_path,
                    'osc_path': osc_full_path,
                    'xosc_path': xosc_full_path
                })
            else:
                if not os.path.exists(xosc_full_path):
                    print(f"警告: 找不到对应的xosc文件: {xosc_full_path}")
                if not os.path.exists(json_full_path):
                    print(f"警告: 找不到对应的osc json文件: {json_full_path}")
                if not os.path.exists(xosc_json_full_path):
                    print(f"警告: 找不到对应的xosc json文件: {xosc_json_full_path}")
    
    return matching_pairs


def main():
    # osc_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/01_法规测试场景/法规测试_osc"
    # xosc_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/01_法规测试场景/法规测试_xosc_matched"
    osc_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_osc"
    xosc_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xosc_matched"
    
    print("开始查找匹配的文件对...")
    matching_pairs = find_matching_files(osc_path, xosc_path)
    
    if not matching_pairs:
        print("未找到任何匹配的文件对！")
        return
    
    print(f"找到 {len(matching_pairs)} 个匹配的文件对")
    
    results = []
    
    for idx, pair in enumerate(matching_pairs):
        print(f"\n处理第 {idx+1}/{len(matching_pairs)} 个文件对: {pair['name']}")
        
        try:
            score, logs = calculate_score_with_log(pair['osc_json_path'], pair['xosc_json_path'])
            
            result = {
                'name': pair['name'],
                'osc_json_path': pair['osc_json_path'],
                'xosc_json_path': pair['xosc_json_path'],
                'osc_path': pair['osc_path'],
                'xosc_path': pair['xosc_path'],
                'score': score,
                'logs': logs
            }
            
            results.append(result)
            print(f"文件对 {pair['name']} 的得分为: {score:.2f}%")
            
        except Exception as e:
            print(f"处理文件对 {pair['name']} 时出错: {e}")
            # 添加失败记录
            result = {
                'name': pair['name'],
                'osc_json_path': pair['osc_json_path'],
                'xosc_json_path': pair['xosc_json_path'],
                'osc_path': pair['osc_path'],
                'xosc_path': pair['xosc_path'],
                'score': None,
                'error': str(e),
                'logs': [f"处理过程中发生错误: {e}"]
            }
            results.append(result)
    
    # 将结果保存到JSON文件
    output_file = "/C20545/jeremyj/pro/volkswagen_intention_eval/batch_evaluation_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n批量评分完成！结果已保存至: {output_file}")
    
    # 输出汇总统计
    successful_evaluations = [r for r in results if r['score'] is not None]
    failed_evaluations = [r for r in results if r['score'] is None]
    
    if successful_evaluations:
        avg_score = sum(r['score'] for r in successful_evaluations) / len(successful_evaluations)
        print(f"\n汇总统计:")
        print(f"成功处理: {len(successful_evaluations)} 个")
        print(f"处理失败: {len(failed_evaluations)} 个")
        print(f"平均得分: {avg_score:.2f}%")
    else:
        print("\n没有成功处理的文件")


if __name__ == "__main__":
    main()