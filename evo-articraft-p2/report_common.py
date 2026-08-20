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


# ============================================================ 人工标注比对

REVIEW_CSV = pathlib.Path(r"C:\Users\Xuge\Downloads\articraft_case_reviews_v6 (2).csv")

COL_A5 = "零件位置、朝向与装配关系是否合理"
COL_A6 = "初始状态是否不存在非预期穿插、悬浮或脱离"
COL_GEO = "几何形状、尺寸和比例是否合理"

# 2026-08-20 针对"对不齐案例"的复核中被改判的案例（用于表格标记）
REREVIEWED = {
    "rec_cash_register_a90a3eb4ec5a49c79034bac363111f2a",
    "rec_flip_phone_83b0fac634af42e2bd288f59133e70c8",
    "rec_lazy_susan_efcb4237eb1c4f96a46d0b370cf1dcb5",
    "rec_monitor_mount_c10308ed1ba241a9a835032150c14cbb",
    "rec_yawpitchroll_wrist_71a3903167694d5ab1a72ebd73fa28f6",
}


def load_reviews() -> dict:
    """Record ID → 逐项标注行（articraft_case_reviews_v6 (2)，含 2026-08-20 复核）。"""
    import csv as _csv
    out = {}
    with REVIEW_CSV.open(encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            rid = (row.get("Record ID") or "").strip()
            if rid:
                out[rid] = row
    return out


def build_human_comparison(results) -> str:
    reviews = load_reviews()

    def chip(text, cls):
        return f'<span class="score {cls}">{text}</span>'

    rows, stat = [], {"both": 0, "clean": 0, "m_only": 0, "h_only": 0}
    for r in results:
        rid = r["record_id"]
        rv = reviews.get(rid, {})
        gf3, gf4 = r.get("gf3", {}), r.get("gf4", {})

        fails = [name for col, name in ((COL_A5, "装配关系"), (COL_A6, "穿插/悬浮/脱离"))
                 if rv.get(col, "") == "不满足"]
        retag = ' <span class="tag-fused">08-20 复核改判</span>' if rid in REREVIEWED else ""
        h_rel_txt = (("✗ " + "、".join(fails)) if fails else "✓ 未勾") + retag
        m3 = gf3.get("score")
        m3_fail = m3 is not None and m3 < 0.999

        if m3_fail and fails:
            cmp3, key = chip("一致·同报", "ok"), "both"
        elif not m3_fail and not fails:
            cmp3, key = chip("一致·同净", "ok"), "clean"
        elif m3_fail:
            cmp3, key = chip("仅机器", "mid"), "m_only"
        else:
            cmp3, key = chip("仅人工", "bad"), "h_only"
        stat[key] += 1

        h_geo = rv.get(COL_GEO, "") == "不满足"
        m4 = gf4.get("score")
        m4_flag = m4 is not None and m4 < 0.95
        if m4 is None:
            cmp4 = chip("仅人工", "bad") if h_geo else '<span class="na">无声明</span>'
        elif m4_flag and h_geo:
            cmp4 = chip("一致·同报", "ok")
        elif not m4_flag and not h_geo:
            cmp4 = chip("一致·同净", "ok")
        elif m4_flag:
            cmp4 = chip("仅机器", "mid")
        else:
            cmp4 = chip("仅人工", "bad")

        rows.append(f"""
<tr>
  <td><div class="case-label">{r.get('label','')}</div>
      <div class="case-rid">{rid[:40]}…</div></td>
  <td class="num">{gf_chip(m3)}<br><span class="sub">{gf3.get('n_satisfied','–')}/{gf3.get('n_evaluated','–')}条</span></td>
  <td>{h_rel_txt}</td>
  <td>{cmp3}</td>
  <td class="num">{gf_chip(m4, warn=0.95)}</td>
  <td>{'✗ 已勾' if h_geo else '✓ 未勾'}</td>
  <td>{cmp4}</td>
</tr>""")

    agree = stat["both"] + stat["clean"]
    return f"""<section>
  <h2>补充：与人工标注的比对</h2>
  <p class="sec-note">标注源为逐项标注表 articraft_case_reviews_v6 (2)，含 2026-08-20 针对"对不齐案例"的定向复核（5 例被改判，表中已标注）。
  人工清单与 GF 维度并非一一对应，按语义就近比对：<b>GF3 ↔「零件位置、朝向与装配关系」+「初始状态非预期穿插、悬浮或脱离」</b>两项；
  <b>GF4 ↔「几何形状、尺寸和比例」</b>；GF1/GF2 在人工清单里没有对应维度（最接近的「零件数量种类」「必要结构」查的是存在性而非形似度），不做硬比对；
  「运动过程穿模」「关节类型/轴向/范围」等项属 P3 运动学范畴，不参与。人工为二值勾选、GF 为连续分数，故只比"双方是否都报了问题"的方向一致性。</p>

  <div class="tablewrap"><table>
    <thead><tr><th>案例</th><th>GF3</th><th>人工·装配/穿插</th><th>对比</th><th>GF4</th><th>人工·几何比例</th><th>对比</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>

  <div class="legend" style="margin-top:14px">
    <b>GF3 方向一致性：{agree}/20（同报 {stat['both']} + 同净 {stat['clean']}）；仅机器报 {stat['m_only']}；仅人工报 {stat['h_only']}</b>
    <ul>
      <li><b>定向复核确认了 6 个"仅机器"案例中的 5 个是标注遗漏。</b>复核前 GF3 方向一致性为 10/20；复核后转盘（−0.19/−0.21·D）、显示器支架（−0.031·D）、三自由度腕（−0.029/−0.034·D）、收银机（−0.006·D）、翻盖手机（−0.008·D）全部改判为"穿插不满足"，一致性升至 {agree}/20。<b>值得注意的是两个浅压入案例（收银机、翻盖手机）也被确认为真缺陷——这把此前"放宽 ATTACH_MAX_PEN"的倾向反转了：0.005·D 的容差目前看画得并不算严。</b></li>
      <li><b>唯一剩下的"仅机器"是台钳</b>（jaw 嵌入 bench −0.069·D）。该案例标注人为 wanglin（07-29），不在本轮复核范围，且其"零件拆分与活动属性"已被勾不满足——建议按同样方式回看一次"穿插"维度。</li>
      <li><b>仅人工报的 4 例（帕尼尼机、风力机、办公椅、指骨链）是已知的声明覆盖缺口。</b>替身声明只覆盖"关节相连零件对"的 attached 关系，而人工的"穿插/悬浮/脱离"覆盖任意零件对与悬浮脱离。接入 P0 真声明或补一个全零件对穿插扫描即可闭合。</li>
      <li><b>GF4 与人工"几何比例"维度在本轮后完全无重叠样本。</b>收银机的"几何比例"勾选在复核中撤销，20 例中人工该维度已无失败；机器唯一报的办公椅（脚轮 5% 不等大）人工未勾。替身比例声明（命名对称）与人工"几何合理性"问的不是同一件事，此项比对要等 P0 真比例声明。</li>
      <li><b>GF1/GF2 无对应维度，仅一条方向观察：</b>塔扇被人工勾了"零件数量/必要结构"，GF1 仍排第 1（p=0.757）——符合设计（GF1 只管整体形似、不管数量），说明感知指标与人工存在性检查互补而非冗余。</li>
    </ul>
  </div>
</section>
"""
