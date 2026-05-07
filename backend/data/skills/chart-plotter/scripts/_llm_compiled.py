import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import os

# 创建输出目录
os.makedirs('outputs', exist_ok=True)

# 门尺寸
width, height = 3, 4
stick_length = 8
diagonal = np.sqrt(width**2 + height**2)

fig, ax = plt.subplots(figsize=(12, 8))

# 画门（蓝色矩形）
door = patches.Rectangle((0, 0), width, height, linewidth=3, edgecolor='blue', facecolor='lightblue', alpha=0.5, label='门 (3m × 4m)')
ax.add_patch(door)

# 画门的对角线（绿色）
ax.plot([0, width], [0, height], 'g-', linewidth=3, label=f'门对角线 ({diagonal}m)')

# 画木棍（红色，放在门下方对比）
ax.plot([0, stick_length], [-1.5, -1.5], 'r-', linewidth=6, label=f'木棍 ({stick_length}m)')
ax.plot([0, stick_length], [-1.5, -1.5], 'r-', linewidth=6, solid_capstyle='round')

# 标注尺寸
ax.annotate('', xy=(width, -0.3), xytext=(0, -0.3), arrowprops=dict(arrowstyle='<->', color='blue', lw=2))
ax.text(width/2, -0.6, '3m', ha='center', fontsize=12, color='blue', fontweight='bold')

ax.annotate('', xy=(width+0.3, height), xytext=(width+0.3, 0), arrowprops=dict(arrowstyle='<->', color='blue', lw=2))
ax.text(width+0.6, height/2, '4m', ha='center', fontsize=12, color='blue', fontweight='bold', rotation=90)

# 标注对角线长度
ax.text(width/2-0.3, height/2+0.3, f'对角线={diagonal}m', fontsize=11, color='green', fontweight='bold', rotation=np.arctan(height/width)*180/np.pi)

# 标注木棍长度
ax.text(stick_length/2, -2.2, '木棍长度 = 8m', ha='center', fontsize=12, color='red', fontweight='bold')

# 添加结论文本框
conclusion = f'结论：门的对角线 = √(3²+4²) = {diagonal}m\n木棍长度 = {stick_length}m\n因为 {stick_length}m > {diagonal}m，所以木棍无法通过！'
props = dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.8)
ax.text(5.5, 3, conclusion, fontsize=13, verticalalignment='top', bbox=props, fontweight='bold')

# 设置图形属性
ax.set_xlim(-0.5, 10)
ax.set_ylim(-3, 5)
ax.set_aspect('equal')
ax.grid(True, alpha=0.3)
ax.set_xlabel('宽度 (米)', fontsize=12)
ax.set_ylabel('高度 (米)', fontsize=12)
ax.set_title('木棍能否通过门？几何示意图', fontsize=16, fontweight='bold')
ax.legend(loc='upper right', fontsize=11)

plt.tight_layout()
plt.savefig('outputs/door_stick_diagram.svg', format='svg', dpi=300, bbox_inches='tight')
plt.savefig('outputs/door_stick_diagram.png', dpi=300, bbox_inches='tight')
print('示意图已保存到 outputs/door_stick_diagram.svg 和 outputs/door_stick_diagram.png')
print(f'\n分析结果：')
print(f'门尺寸：宽{width}m × 高{height}m')
print(f'门对角线长度 = √({width}² + {height}²) = √{width**2 + height**2} = {diagonal}m')
print(f'木棍长度 = {stick_length}m')
print(f'因为 {stick_length}m > {diagonal}m，所以木棍无法通过门！')