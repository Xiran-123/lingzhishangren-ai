"""读取PPT全文文本"""
from pptx import Presentation
import sys

path = r"d:\Desktop\灵智尚人：面向数智时代的工科智能教学方案V1(1).pptx"
prs = Presentation(path)
print(f"总页数: {len(prs.slides)}")
for i, slide in enumerate(prs.slides, 1):
    texts = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            t = shape.text_frame.text.strip()
            if t:
                texts.append(t.replace("\n", " | "))
        if shape.shape_type == 19:  # table
            pass
    print(f"\n--- 第{i}页 ---")
    for t in texts:
        print(t[:300])
