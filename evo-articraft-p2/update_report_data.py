"""只更新报告 HTML 里的「案例数据区」，不碰任何手工编辑过的正文。

替换范围（且仅此三类）：
  1. 结果表 <tbody>…</tbody>
  2. 证据列表 <div class="ev-list">…</div>
  3. 四个统计块的数字（<div class="stat"><b>…</b> 按出现顺序），以及
     三处固定措辞里的数字：「N 工具故障」「单轮 N 秒」「其中 N 条为穿透」
其余文本一律不动。每处替换是否命中都会打印出来。
"""

from __future__ import annotations

import re
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from report_common import OUT, load_results, compute_stats, build_rows, build_evidence

RUNTIME_S = 21   # 本轮墙钟秒数（runner 输出）

html_path = OUT / "p2_smoke_report.html"
html = html_path.read_text(encoding="utf-8")

results, _ = load_results()
st = compute_stats(results)

report = []

# ---- 1. 结果表 ----
new_tbody = "<tbody>" + build_rows(results) + "\n</tbody>"
html, n = re.subn(r"<tbody>.*?</tbody>", lambda _: new_tbody, html, count=1, flags=re.S)
report.append(f"结果表 tbody: {'OK' if n else '未命中!'}")

# ---- 2. 证据列表 ----
new_ev = '<div class="ev-list">' + build_evidence(results) + "</div>\n</section>"
html, n = re.subn(r'<div class="ev-list">.*?</div>\s*</section>',
                  lambda _: new_ev, html, count=1, flags=re.S)
report.append(f"证据列表 ev-list: {'OK' if n else '未命中!'}")

# ---- 3. 统计数字 ----
stat_values = [
    f"{st['n_cases_ok']}/20",
    str(st["n_parts"]),
    f"{st['n_rank1']}/20",
    f"{st['n_failed']}/{st['n_claims']}",
]
idx = [0]
def _stat_sub(m):
    v = stat_values[idx[0]] if idx[0] < len(stat_values) else m.group(2)
    idx[0] += 1
    return m.group(1) + v + m.group(3)

html, n = re.subn(r'(<div class="stat"><b>)([^<]*)(</b>)', _stat_sub, html)
report.append(f"统计块 <b> 数字: 命中 {n}/4")

for pattern, repl, name in [
    (r"· \d+ 工具故障", f"· {st['n_tool_fail']} 工具故障", "工具故障数"),
    (r"单轮 \d+ 秒", f"单轮 {RUNTIME_S} 秒", "运行时长"),
    (r"其中 \d+ 条为穿透", f"其中 {st['n_pen']} 条为穿透", "穿透条数"),
]:
    html, n = re.subn(pattern, repl, html, count=1)
    report.append(f"{name}: {'OK' if n else '未命中(措辞可能已被手改, 跳过)'}")

html_path.write_text(html, encoding="utf-8")
print("\n".join(report))
print(f"\n已写回: {html_path}")
print(f"本轮数据: 跑通 {st['n_cases_ok']}/20, 零件 {st['n_parts']}, GF1第一 {st['n_rank1']}/20, "
      f"判负 {st['n_failed']}/{st['n_claims']} (穿透 {st['n_pen']})")
