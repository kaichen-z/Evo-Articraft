"""把「与人工标注的比对」小节插入（或刷新到）报告 HTML，正文其他部分不动。

用法: python patch_comparison.py [报告文件名, 默认 p2-xuge.html]
幂等：已存在该小节时先移除旧的再插入新的。
"""

from __future__ import annotations

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from report_common import OUT, load_results, build_human_comparison

name = sys.argv[1] if len(sys.argv) > 1 else "p2-xuge.html"
path = OUT / name
html = path.read_text(encoding="utf-8")

results, _ = load_results()
section = build_human_comparison(results)

# 幂等：移除旧比对节
html, removed = re.subn(
    r"<section>\s*<h2>补充：与人工标注的比对</h2>.*?</section>\s*",
    "", html, count=1, flags=re.S)

# 插到「四、想提的问题」之前
html, n = re.subn(r"(<section>\s*<h2>四、)",
                  lambda m: section + "\n" + m.group(1), html, count=1)

if n == 0:
    print("未找到插入锚点（四、想提的问题）——文件未修改")
    sys.exit(1)

path.write_text(html, encoding="utf-8")
print(f"{'刷新' if removed else '插入'}比对小节 -> {path}")
