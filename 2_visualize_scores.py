import json
import matplotlib.pyplot as plt
from pathlib import Path

plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# json_path = Path(__file__).parent / "data/02_CIDAS场景/batch_evaluation_results.json"
json_path = "/C20545/jeremyj/pro/volkswagen_intention_eval/data/CQU/v1.7.0/cqu_evaluation_results.json"

# 从路径中提取场景名称：volkswagen_intention_eval/data/{场景名}/...
scene_name = json_path.split('/volkswagen_intention_eval/data/')[1].split('/')[0]
# 清理可能的车版本号（如 v1.7.0）
scene_name = scene_name.split('/')[0]

with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

# 支持两种格式：dict with 'results' key, or direct list
results = data if isinstance(data, list) else data.get('results', data)

scores = [item['score'] for item in results]

bins = [0, 20, 40, 60, 80, 100]
labels = ['0-20%', '20-40%', '40-60%', '60-80%', '80-100%']
counts, bins_out, patches = plt.hist(scores, bins=bins)
counts = counts.astype(int)

colors = ['#ff6b6b', '#ffa94d', '#ffd43b', '#69db7c', '#4dabf7']

# Filter out zero-count slices
non_zero_indices = [i for i, c in enumerate(counts) if c > 0]
filtered_counts = [counts[i] for i in non_zero_indices]
filtered_labels = [labels[i] for i in non_zero_indices]
filtered_colors = [colors[i] for i in non_zero_indices]

fig, ax = plt.subplots(figsize=(10, 8))
wedges, texts, autotexts = ax.pie(
    filtered_counts,
    labels=filtered_labels,
    autopct=lambda p: f'{p:.1f}%\n({int(p*len(scores)/100)})',
    colors=filtered_colors,
    startangle=90,
    explode=[0.02] * len(filtered_counts)
)
ax.set_title(f'{scene_name}场景匹配得分分布 (共{len(scores)}个样本)', fontsize=14, pad=20)

for autotext in autotexts:
    autotext.set_fontsize(10)

plt.tight_layout()
plt.savefig(Path(__file__).parent / 'score_distribution_pie.png', dpi=150, bbox_inches='tight')
plt.show()

print(f"图表已保存至: {Path(__file__).parent / 'score_distribution_pie.png'}")
print(f"\n分数统计:")
print(f"  样本数: {len(scores)}")
print(f"  平均分: {sum(scores)/len(scores):.2f}%")
print(f"  最高分: {max(scores):.2f}%")
print(f"  最低分: {min(scores):.2f}%")
