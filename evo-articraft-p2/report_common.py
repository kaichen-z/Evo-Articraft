"""报告数据区构建器：make_report.py（整页生成）与 update_report_data.py（只换数据）共用。"""

from __future__ import annotations

import base64
import io
import json
import pathlib

from PIL import Image

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"


def load_results():
    payload = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
    return payload["results"], payload["protocol"]


def thumb_b64(rid: str, size: int = 168) -> str:
    p = OUT / "renders" / rid / "global_az000.png"
    if not p.exists():
        return ""
    img = Image.open(p).convert("RGB")
    img.thumbnail((size, size))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=72)
    return base64.b64encode(buf.getvalue()).decode()


def fmt(v, nd=3):
    if v is None:
        return '<span class="na">n/a</span>'
    return f"{v:.{nd}f}"


def gf_chip(v, warn=0.999):
    if v is None:
        return '<span class="na">n/a</span>'
    cls = "ok" if v >= warn else ("mid" if v >= 0.5 else "bad")
    return f'<span class="score {cls}">{v:.3f}</span>'


def compute_stats(results) -> dict:
    n_fail_tool = sum(1 for r in results if r.get("coverage") == "tool-failure")
    all_claims = [c for r in results for c in r.get("gf3", {}).get("claims", [])]
    failed = [c for c in all_claims if c.get("satisfied") is False]
    n_pen = sum(1 for c in failed
                if any((p.get("measured") or {}).get("state") == "penetration"
                       for p in c.get("pairs", [])))
    return {
        "n_cases_ok": len(results) - n_fail_tool,
        "n_tool_fail": n_fail_tool,
        "n_parts": sum(r.get("gf2", {}).get("n_parts_scored", 0) for r in results),
        "n_rank1": sum(1 for r in results if r.get("gf1", {}).get("rank_among_20") == 1),
        "n_claims": len(all_claims),
        "n_failed": len(failed),
        "n_pen": n_pen,
    }


def build_rows(results) -> str:
    rows = []
    for r in results:
        rid = r["record_id"]
        gf1, gf2 = r.get("gf1", {}), r.get("gf2", {})
        gf3, gf4 = r.get("gf3", {}), r.get("gf4", {})
        rank = gf1.get("rank_among_20")
        rank_cls = "ok" if rank == 1 else ("mid" if (rank or 99) <= 3 else "bad")
        unmeas = (gf3.get("n_unmeasurable", 0) or 0)
        unmeas_txt = f'<span class="muted"> ·{unmeas}不可测</span>' if unmeas else ""
        rows.append(f"""
<tr>
  <td class="thumb-cell"><img src="data:image/jpeg;base64,{thumb_b64(rid)}" alt="{rid}"></td>
  <td><div class="case-label">{r.get('label','')}</div>
      <div class="case-cat">{r.get('category','')}</div>
      <div class="case-rid">{rid[:44]}…</div></td>
  <td class="num">{fmt(gf1.get('mean_cos'),4)}<br>
      <span class="sub">p={fmt(gf1.get('softmax_prob_vs_19_distractors'),3)}
      <span class="rank {rank_cls}">#{rank}</span></span></td>
  <td class="num">{fmt(gf2.get('macro_mean_cos'),4)}<br>
      <span class="sub">p̄={fmt(gf2.get('macro_prob'),3)} · {gf2.get('n_parts_scored','–')}件</span></td>
  <td class="num">{gf_chip(gf3.get('score'))}<br>
      <span class="sub">{gf3.get('n_satisfied','–')}/{gf3.get('n_evaluated','–')}条{unmeas_txt}</span></td>
  <td class="num">{gf_chip(gf4.get('score'), warn=0.95)}<br>
      <span class="sub">{gf4.get('n_evaluated', 0) or '–'}对</span></td>
</tr>""")
    return "".join(rows)


def _pair_detail(m: dict) -> str:
    if "signed_distance_over_D" in m:
        return f"sd = {m['signed_distance']:+.4f} m（{m['signed_distance_over_D']:+.4f}·D，{m.get('state','')}）"
    if "z_gap_over_D" in m:
        return f"z-gap = {m['z_gap_over_D']:+.4f}·D，投影重叠 {m.get('footprint_overlap',0):.2f}"
    if "inside_fraction" in m:
        return f"inside 比例 {m['inside_fraction']:.2f}"
    return str(m)


def build_evidence(results) -> str:
    ev_rows = []
    for r in results:
        fails = [c for c in r.get("gf3", {}).get("claims", []) if c.get("satisfied") is False]
        if not fails:
            continue
        items = []
        for c in fails:
            for p in [p for p in c.get("pairs", []) if p.get("satisfied") is False]:
                m = p.get("measured") or {}
                proxy = ' <span class="tag-fused">fused-proxy</span>' if "fused-proxy" in (p.get("note") or "") else ""
                items.append(
                    f"<li><code>{p['subject']}</code> —{c['relation']}→ <code>{p['object']}</code>："
                    f"{_pair_detail(m)}{proxy}</li>")
        ev_rows.append(f"""<div class="ev-case"><div class="ev-head">{r.get('label','')} · <span class="case-rid">{r['record_id'][:52]}</span>
    <span class="score bad">GF3 {fmt(r['gf3'].get('score'))}</span></div><ul>{''.join(items)}</ul></div>""")
    return "".join(ev_rows)
