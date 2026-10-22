"""提取申报书docx全文（段落+表格）"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document

path = r"d:\Users\李昊\Documents\微信存储\xwechat_files\wxid_jlveug714l0x22_4498\temp\RWTemp\2026-10\8525706e3f4eb2102ad9b72aefefd5cd\附件2 2026年度“人工智能+”虚拟仿真实验教学项目申报书 - 副本 (2).docx"
doc = Document(path)

lines = []
for para in doc.paragraphs:
    t = para.text.strip()
    if t:
        lines.append(t)

for ti, table in enumerate(doc.tables):
    lines.append(f"\n===== 表格{ti+1} =====")
    seen = set()
    for row in table.rows:
        cells = []
        for c in row.cells:
            txt = c.text.strip().replace('\n', ' ')
            if txt and (c._tc, txt) not in seen:
                cells.append(txt)
        if cells:
            lines.append(" | ".join(cells))

out = "\n".join(lines)
with open(r"d:\PythonProject3\.venv\_declare.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(f"总字符数: {len(out)}, 段落数: {len(lines)}")
