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


def call_llm_judgment_with_reason(content1: str, content2: str,
                                   api_url: str = "http://10.160.199.227:8006/v1/chat/completions") -> tuple:
    """
    调用大模型API判断两个内容是否表达相同意思，并返回判断理由

    Args:
        content1: 第一个内容
        content2: 第二个内容
        api_url: API服务地址

    Returns:
        tuple: (is_match: bool, reason: str)
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }

    system_prompt = """请严格判断以下两个内容是否表达相同的意思。
要求：
1. 仅当下列条件满足时才判断为"一致"：两个内容表达的含义完全相同或高度相似
2. 当两个内容表达不同的概念、数值或类别时，必须判断为"不一致"
3. 特别注意：不同类型的概念（如"隧道"和"城市快速路"）应判断为"不一致"
4. 请用JSON格式输出判断结果，包含判断结论和不一致的原因说明"""

    user_content = f"""请判断以下两个内容是否表达相同的意思：

内容1: {content1}

内容2: {content2}

请以JSON格式输出判断结果：
{{"结论": "一致"或"不一致", "原因": "简要说明不一致的原因（如果一致则为空）"}}

请仅输出JSON，不要有其他解释文字。"""

    payload = {
        "model": "holo-model",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            # 解析JSON响应
            try:
                # 尝试提取JSON
                import re
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    json_str = json_match.group()
                    data = json.loads(json_str)
                    is_match = data.get("结论", "") == "一致"
                    reason = data.get("原因", "")
                    return is_match, reason
            except json.JSONDecodeError:
                pass
            # 如果解析失败，使用简单的判断
            is_match = "是" in content.strip() and "否" not in content.strip()
            return is_match, ""
        return False, ""
    except Exception as e:
        print(f"请求错误: {e}")
        return False, str(e)


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
    is_match, _ = call_llm_judgment_with_reason(content1, content2, api_url)
    return is_match


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


def merge_action_sequences(layer3_data: Dict, layer4_data: Dict) -> List[Dict]:
    """
    将第四层的动作序列合并到第三层参与者信息中

    Args:
        layer3_data: 第三层参与者信息层数据（列表）
        layer4_data: 第四层行为语义层数据（字典）

    Returns:
        合并后的参与者列表，每个参与者包含其动作序列（如果有）
    """
    merged_participants = []

    # 复制参与者信息
    for p in layer3_data:
        participant = dict(p)
        participant["动作序列"] = None  # 初始化为空
        merged_participants.append(participant)

    # 处理主车动作序列：找到参与者角色="主车"的项
    if "主车动作序列" in layer4_data:
        ego_action = layer4_data["主车动作序列"].get("内容")
        for p in merged_participants:
            if p.get("参与者角色") == "主车":
                p["动作序列"] = ego_action
                break

    # 处理他车他者动作序列：根据参与者ID匹配
    if "他车他者动作序列" in layer4_data:
        npc_actions = layer4_data["他车他者动作序列"].get("内容", [])
        if isinstance(npc_actions, list):
            for action_item in npc_actions:
                if isinstance(action_item, dict) and "参与者ID" in action_item:
                    participant_id = action_item["参与者ID"]
                    action_sequence = action_item.get("动作序列")
                    # 找到对应的参与者
                    for p in merged_participants:
                        if p.get("参与者ID") == participant_id:
                            p["动作序列"] = action_sequence
                            break

    return merged_participants


def extract_participants_for_matching(xml_layer3, xml_layer4, osc_layer3, osc_layer4):
    """
    提取并合并参与者信息，用于匹配计分

    Args:
        xml_layer3: XML第三层数据
        xml_layer4: XML第四层数据
        osc_layer3: OSC第三层数据
        osc_layer4: OSC第四层数据

    Returns:
        (xml_participants, osc_participants): 合并后的参与者列表
    """
    xml_participants = merge_action_sequences(xml_layer3, xml_layer4)
    osc_participants = merge_action_sequences(osc_layer3, osc_layer4)
    return xml_participants, osc_participants


def judge_same_participant(xml_p: Dict, osc_p: Dict,
                          api_url: str = "http://10.160.199.227:8006/v1/chat/completions") -> bool:
    """
    使用LLM判断两个参与者是否描述同一个实体（忽略ID，速度/距离可放宽）

    Args:
        xml_p: XML参与者信息
        osc_p: OSC参与者信息
        api_url: API服务地址

    Returns:
        True表示描述同一个参与者，False表示不是
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY"
    }

    # 构建比较内容（忽略参与者ID）
    def get_comparable_info(p):
        return {
            "参与者角色": p.get("参与者角色"),
            "参与者类型": p.get("参与者类型"),
            "相对主车方位": p.get("相对主车方位"),
            "车道关系": p.get("车道关系"),
            "初始速度_kmh": p.get("初始速度_kmh"),
            "相对主车距离_m": p.get("相对主车距离_m")
        }

    xml_info = get_comparable_info(xml_p)
    osc_info = get_comparable_info(osc_p)

    system_prompt = """请判断以下两个参与者信息是否描述的是同一个实体。
判断标准：
1. 参与者角色必须相同（如都是"主车"或都是"NPC车辆"）
2. 参与者类型应该相同（如都是"轿车"或都是"卡车"）
3. 相对位置（方位、车道关系）应该一致
4. 速度值和距离值可以有较大误差，不是主要判断依据
5. 参与者ID不参与判断（不同系统的命名方式可能不同）

请仅输出"是"或"否"："""

    user_content = f"""参与者1: {json.dumps(xml_info, ensure_ascii=False)}
参与者2: {json.dumps(osc_info, ensure_ascii=False)}

请判断这两个参与者是否描述的是同一个实体："""

    payload = {
        "model": "holo-model",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.0
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload)
        response.raise_for_status()
        result = response.json()
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            return "是" in content.strip() and "否" not in content.strip()
        return False
    except Exception as e:
        print(f"判断参与者是否相同时出错: {e}")
        return False


def match_participants_by_similarity(xml_participants: List[Dict], osc_participants: List[Dict]) -> tuple:
    """
    使用贪心算法匹配XML和OSC的参与者

    Args:
        xml_participants: XML参与者列表
        osc_participants: OSC参与者列表

    Returns:
        (matched_pairs, unmatched_xml_count, unmatched_osc_count)
        - matched_pairs: [(xml_p, osc_p, is_same_participant, is_content_match), ...]
        - unmatched_xml_count: XML中未匹配上的参与者数量
        - unmatched_osc_count: OSC中未匹配上的参与者数量
    """
    matched_pairs = []
    used_xml = set()
    used_osc = set()

    # 计算所有可能配对的相似度
    candidates = []
    for i, xml_p in enumerate(xml_participants):
        for j, osc_p in enumerate(osc_participants):
            is_same = judge_same_participant(xml_p, osc_p)
            if is_same:
                candidates.append((i, j, xml_p, osc_p))

    # 按相似度排序（这里简化为按索引顺序，实际上judge_same_participant返回的是bool）
    # 贪心选取：每次选最确定的匹配
    for i, j, xml_p, osc_p in candidates:
        if i not in used_xml and j not in used_osc:
            matched_pairs.append((xml_p, osc_p))
            used_xml.add(i)
            used_osc.add(j)

    unmatched_xml = len(xml_participants) - len(matched_pairs)
    unmatched_osc = len(osc_participants) - len(matched_pairs)

    return matched_pairs, unmatched_xml, unmatched_osc


def calculate_score_with_log(xml_file_path: str, osc_file_path: str) -> tuple[float, List[str]]:
    """
    计算XML和OSC意图分析结果的匹配得分，并记录详细过程日志

    第三层（参与者信息层）：使用参与者整体匹配（动作序列已合并到参与者中）
    其他层：第一、二、四、五层保持逐项匹配逻辑

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

            # 第三层（参与者信息层）：使用参与者整体匹配逻辑
            if layer_name == "参与者信息层":
                # 提取第四层的行为语义数据（用于合并动作序列）
                xml_layer4 = xml_data.get("行为语义层", {})
                osc_layer4 = osc_data.get("行为语义层", {})

                # 提取并合并参与者信息
                xml_participants, osc_participants = extract_participants_for_matching(
                    xml_layer, xml_layer4, osc_layer, osc_layer4
                )

                print(f"第三层参与者匹配: XML有{len(xml_participants)}个参与者, OSC有{len(osc_participants)}个参与者")

                # 使用贪心算法匹配参与者
                matched_pairs, unmatched_xml, unmatched_osc = match_participants_by_similarity(
                    xml_participants, osc_participants
                )

                print(f"成功匹配的对数: {len(matched_pairs)}, XML未匹配: {unmatched_xml}, OSC未匹配: {unmatched_osc}")

                # 对每个匹配对进行整体内容判断
                for xml_p, osc_p in matched_pairs:
                    xml_id = xml_p.get("参与者ID", "未知")
                    osc_id = osc_p.get("参与者ID", "未知")
                    total_valid_entries += 1

                    xml_content = normalize_content(xml_p)
                    osc_content = normalize_content(osc_p)

                    if xml_content == osc_content:
                        positive_matches += 1
                        print(f"参与者完全匹配: XML[{xml_id}] vs OSC[{osc_id}]")
                    else:
                        print(f"请求大模型判断参与者: XML[{xml_id}] vs OSC[{osc_id}]")
                        is_match, reason = call_llm_judgment_with_reason(xml_content, osc_content)
                        if is_match:
                            positive_matches += 1
                            print(f"大模型判断一致: XML[{xml_id}] vs OSC[{osc_id}]")
                        else:
                            reason_text = f" (原因: {reason})" if reason else ""
                            print(f"大模型判断不一致: XML[{xml_id}] vs OSC[{osc_id}]{reason_text}")

                # 未匹配上的参与者计为不匹配
                for _ in range(unmatched_xml + unmatched_osc):
                    total_valid_entries += 1
                    # 不匹配不得分，所以positive_matches不增加

                continue  # 第三层处理完成，跳过下面的通用逻辑

            # 其他层：保持原来的逐项匹配逻辑
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
                            print(f"完全匹配: {layer_name}/{key} - {xml_content}")
                        else:
                            # 情况二: 请求大模型判断一致性
                            judgment_request_msg = f"请求大模型判断: {layer_name}/{key}, XML: {xml_content}, OSC: {osc_content}"
                            print(judgment_request_msg)
                            if call_llm_judgment(xml_content, osc_content):
                                positive_matches += 1
                                print(f"大模型判断一致: {layer_name}/{key}")
                            else:
                                print(f"大模型判断不一致: {layer_name}/{key}")
            else:
                # 如果是字典类型的层级
                for key in xml_layer:
                    if key not in osc_layer:
                        continue  # OSC中没有这个键，跳过

                    # 跳过第四层的主车动作序列和他车他者动作序列（已合并到第三层）
                    if layer_name == "行为语义层" and key in ("主车动作序列", "他车他者动作序列"):
                        print(f"跳过{key}: 已合并到第三层参与者信息中")
                        continue

                    xml_entry = xml_layer[key]
                    osc_entry = osc_layer[key]

                    xml_info_type = xml_entry.get("信息类型", "未涉及")
                    osc_info_type = osc_entry.get("信息类型", "未涉及")

                    # 规则1: 如果有一方为"未涉及"，则跳过该条
                    if xml_info_type == "未涉及" or osc_info_type == "未涉及":
                        print(f"跳过未涉及项: {layer_name}/{key}")
                        continue

                    # 进入正式计分
                    total_valid_entries += 1

                    xml_content = normalize_content(xml_entry.get("内容", ""))
                    osc_content = normalize_content(osc_entry.get("内容", ""))

                    # 情况一: 内容完全一致
                    if xml_content == osc_content:
                        positive_matches += 1
                        print(f"完全匹配: {layer_name}/{key} - {xml_content}")
                    else:
                        # 情况二: 请求大模型判断一致性
                        judgment_request_msg = f"请求大模型判断: {layer_name}/{key}, XML: {xml_content}, OSC: {osc_content}"
                        print(judgment_request_msg)
                        if call_llm_judgment(xml_content, osc_content):
                            positive_matches += 1
                            print(f"大模型判断一致: {layer_name}/{key}")
                        else:
                            print(f"大模型判断不一致: {layer_name}/{key}")

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

            # 情况一：请求大模型判断（标准格式）
            if line.startswith("请求大模型判断:") and i + 1 < len(log_lines):
                next_line = log_lines[i + 1].strip()
                if next_line.startswith("大模型判断一致:") or next_line.startswith("大模型判断不一致:"):
                    result = next_line.replace("大模型判断一致:", "→一致").replace("大模型判断不一致:", "→不一致")
                    merged_line = f"{line} | {result}"
                    merged_logs.append(merged_line)
                    i += 2
                    continue

            # 情况二：参与者匹配判断
            if line.startswith("请求大模型判断参与者:") and i + 1 < len(log_lines):
                next_line = log_lines[i + 1].strip()
                if next_line.startswith("大模型判断一致:") or next_line.startswith("大模型判断不一致:"):
                    result = next_line.replace("大模型判断一致:", "→一致").replace("大模型判断不一致:", "→不一致")
                    merged_line = f"{line} | {result}"
                    merged_logs.append(merged_line)
                    i += 2
                    continue

            # 添加当前行
            merged_logs.append(line)
            i += 1

        # 在第三层参与者匹配的日志前后添加分隔
        final_logs = []
        in_layer3_section = False
        layer3_started = False
        for line in merged_logs:
            if "第三层参与者匹配:" in line:
                if final_logs and final_logs[-1] != "":
                    final_logs.append("")  # 上面空一行
                layer3_started = True
                in_layer3_section = True
                final_logs.append(line)
            elif in_layer3_section and line.startswith("跳过主车动作序列"):
                final_logs.append("")  # 下面空一行
                final_logs.append(line)
                in_layer3_section = False
            else:
                final_logs.append(line)

        return score, final_logs
    finally:
        # 恢复原来的stdout
        sys.stdout = old_stdout


def detect_directory_mode(base_path1: str, base_path2: str) -> str:
    """
    检测目录匹配模式

    Args:
        base_path1: 第一个目录路径
        base_path2: 第二个目录路径

    Returns:
        "subdir": 子文件夹模式（两个目录都有相同的子文件夹结构）
        "flat": 扁平模式（文件直接在目录中，文件名对应匹配）
        "mixed": 混合模式（无法确定）
    """
    entries1 = os.listdir(base_path1)
    entries2 = os.listdir(base_path2)

    # 检查是否有子文件夹
    subdirs1 = [e for e in entries1 if os.path.isdir(os.path.join(base_path1, e))]
    subdirs2 = [e for e in entries2 if os.path.isdir(os.path.join(base_path2, e))]

    # 如果两个目录都有相同的子文件夹名，认为是子文件夹模式
    common_subdirs = set(subdirs1) & set(subdirs2)
    if common_subdirs:
        return "subdir"

    # 如果有共同的子文件夹但不完全匹配，检查是否大部分匹配
    if subdirs1 and subdirs2 and len(common_subdirs) > 0:
        return "subdir"

    # 否则是扁平模式
    return "flat"


def find_matching_files_flat(base_path1: str, base_path2: str, json_suffix: str = ".json") -> List[Dict[str, str]]:
    """
    查找扁平目录模式下的匹配文件对（文件名直接对应）

    Args:
        base_path1: 第一个目录路径（对应XML/JSON）
        base_path2: 第二个目录路径（对应OSC/JSON）
        json_suffix: JSON文件后缀

    Returns:
        包含匹配文件对的列表
    """
    matching_pairs = []

    # 获取所有JSON文件
    files1 = [f for f in os.listdir(base_path1) if f.endswith(json_suffix)]
    files2 = [f for f in os.listdir(base_path2) if f.endswith(json_suffix)]

    # 找出共同的基础名
    basenames1 = set(f[:-len(json_suffix)] for f in files1)
    basenames2 = set(f[:-len(json_suffix)] for f in files2)
    common_basenames = basenames1 & basenames2

    for base_name in common_basenames:
        json_file1 = base_name + json_suffix
        json_file2 = base_name + json_suffix

        path1 = os.path.join(base_path1, json_file1)
        path2 = os.path.join(base_path2, json_file2)

        matching_pairs.append({
            'name': base_name,
            'path1': path1,
            'path2': path2,
            'mode': 'flat'
        })

    return matching_pairs


def find_matching_files_subdir(base_path1: str, base_path2: str, json_suffix: str = ".json") -> List[Dict[str, str]]:
    """
    查找子文件夹模式下的匹配文件对

    Args:
        base_path1: 第一个目录路径
        base_path2: 第二个目录路径
        json_suffix: JSON文件后缀

    Returns:
        包含匹配文件对的列表
    """
    matching_pairs = []

    # 获取所有子文件夹
    subdirs1 = [d for d in os.listdir(base_path1) if os.path.isdir(os.path.join(base_path1, d))]

    for subdir in subdirs1:
        subdir_path1 = os.path.join(base_path1, subdir)
        subdir_path2 = os.path.join(base_path2, subdir)

        if not os.path.exists(subdir_path2):
            print(f"警告: 对应的目录不存在: {subdir_path2}")
            continue

        # 在子文件夹中查找匹配的JSON文件
        files1 = [f for f in os.listdir(subdir_path1) if f.endswith(json_suffix)]

        for file1 in files1:
            base_name = file1[:-len(json_suffix)]
            file2 = base_name + json_suffix

            path1 = os.path.join(subdir_path1, file1)
            path2 = os.path.join(subdir_path2, file2)

            if os.path.exists(path2):
                matching_pairs.append({
                    'name': f"{subdir}/{base_name}",
                    'path1': path1,
                    'path2': path2,
                    'mode': 'subdir',
                    'subdir': subdir
                })
            else:
                print(f"警告: 找不到对应的文件: {path2}")

    return matching_pairs


def find_matching_files(base_path1: str, base_path2: str, json_suffix: str = ".json") -> List[Dict[str, str]]:
    """
    查找匹配的文件对，自动检测目录模式

    Args:
        base_path1: 第一个目录路径（对应XML/JSON）
        base_path2: 第二个目录路径（对应OSC/JSON）
        json_suffix: JSON文件后缀

    Returns:
        包含匹配文件对的列表
    """
    mode = detect_directory_mode(base_path1, base_path2)

    if mode == "subdir":
        print(f"检测到子文件夹模式")
        return find_matching_files_subdir(base_path1, base_path2, json_suffix)
    else:
        print(f"检测到扁平目录模式")
        return find_matching_files_flat(base_path1, base_path2, json_suffix)


def main():
    # 配置区域 - 修改这里的路径和模式设置
    configs = [
        # {
        #     'enabled': True,
        #     'name': 'CIDAS场景',
        #     'path1': "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_osc",
        #     'path2': "/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xosc_matched",
        #     'output': "/C20545/jeremyj/pro/volkswagen_intention_eval/cidas_evaluation_results.json"
        # },
        {
            'enabled': True,
            'name': 'CQU场景',
            'path1': "/C20545/jeremyj/pro/volkswagen_intention_eval/data/CQU/CQU_xml",
            'path2': "/C20545/jeremyj/pro/volkswagen_intention_eval/data/CQU/v1.7.0/osc_output",
            'output': "/C20545/jeremyj/pro/volkswagen_intention_eval/cqu_evaluation_results.json"
        },
    ]

    all_results = []

    for config in configs:
        if not config.get('enabled', True):
            continue

        print(f"\n{'='*60}")
        print(f"处理数据集: {config['name']}")
        print(f"{'='*60}")

        path1 = config['path1']
        path2 = config['path2']
        output_file = config['output']

        print("开始查找匹配的文件对...")
        matching_pairs = find_matching_files(path1, path2)

        if not matching_pairs:
            print("未找到任何匹配的文件对！")
            continue

        print(f"找到 {len(matching_pairs)} 个匹配的文件对")

        results = []

        for idx, pair in enumerate(matching_pairs):
            print(f"\n处理第 {idx+1}/{len(matching_pairs)} 个文件对: {pair['name']}")

            try:
                score, logs = calculate_score_with_log(pair['path1'], pair['path2'])

                result = {
                    'name': pair['name'],
                    'path1': pair['path1'],
                    'path2': pair['path2'],
                    'mode': pair.get('mode', 'unknown'),
                    'score': score,
                    'logs': logs
                }

                results.append(result)
                print(f"文件对 {pair['name']} 的得分为: {score:.2f}%")

            except Exception as e:
                print(f"处理文件对 {pair['name']} 时出错: {e}")
                result = {
                    'name': pair['name'],
                    'path1': pair['path1'],
                    'path2': pair['path2'],
                    'mode': pair.get('mode', 'unknown'),
                    'score': None,
                    'error': str(e),
                    'logs': [f"处理过程中发生错误: {e}"]
                }
                results.append(result)

        # 将结果保存到JSON文件
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                'config': config,
                'results': results
            }, f, ensure_ascii=False, indent=2)

        print(f"\n批量评分完成！结果已保存至: {output_file}")

        # 输出汇总统计
        successful_evaluations = [r for r in results if r['score'] is not None]
        failed_evaluations = [r for r in results if r['score'] is None]

        if successful_evaluations:
            avg_score = sum(r['score'] for r in successful_evaluations) / len(successful_evaluations)
            print(f"\n汇总统计 ({config['name']}):")
            print(f"成功处理: {len(successful_evaluations)} 个")
            print(f"处理失败: {len(failed_evaluations)} 个")
            print(f"平均得分: {avg_score:.2f}%")

        all_results.extend(results)

    if len(configs) > 1:
        print(f"\n{'='*60}")
        print("总体汇总")
        print(f"{'='*60}")
        successful = [r for r in all_results if r['score'] is not None]
        if successful:
            avg = sum(r['score'] for r in successful) / len(successful)
            print(f"总处理: {len(all_results)} 个")
            print(f"成功: {len(successful)} 个")
            print(f"失败: {len(all_results) - len(successful)} 个")
            print(f"总体平均得分: {avg:.2f}%")


if __name__ == "__main__":
    main()