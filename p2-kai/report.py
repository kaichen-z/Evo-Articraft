#!/usr/bin/env python3
"""Render results.json as the Task-13-4 HTML report (GT defect vs detected defect).

    env_mujoco/bin/python code/p2-kai/report.py --out <answer2>/task-13-4_08-19.html
"""
import argparse, html, json, os, shutil, collections

EXPECTED_DIM = {"part_deletion": "GF2", "silent_noop": "GF2", "part_displacement": "GF3",
                "proportion_scale": "GF4", "topology_break": "GF1", "decoration_removal": None}
DIMS = ("GF1", "GF2", "GF3", "GF4")
E = html.escape


def bar(v, d):
    if v is None:
        return '<td class="na">n/a</td>'
    cls = "up" if (d or 0) > 0.005 else ("down" if (d or 0) < -0.05 else "flat")
    dtxt = "" if d is None else (f"{d:+.2f}" if abs(d) >= 0.005 else "0")
    return (f'<td class="m {cls}"><span class="v">{v:.2f}</span>'
            f'<span class="d">{dtxt}</span>'
            f'<span class="track"><i style="width:{max(0.0,min(1.0,v))*100:.0f}%"></i></span></td>')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "results.json"))
    ap.add_argument("--data", default="/Users/kai/Storage/Daily/Claude/0_Code/mechanism/data/zero-cad-10samples-gf")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    R = json.load(open(a.results))
    recs = R["records"]
    assets = os.path.splitext(a.out)[0] + "-assets"
    os.makedirs(assets, exist_ok=True)

    for r in recs:
        src = os.path.join(a.data, r["path"], "renders", "view_000.png")
        dst = os.path.join(assets, f"{r['uuid'][:8]}-{r['variant']}.png")
        if os.path.exists(src):
            shutil.copyfile(src, dst)
        r["thumb"] = os.path.basename(assets) + "/" + os.path.basename(dst)

    inj = [r for r in recs if r["variant"] != "gt"]
    gen = [r for r in inj if r["generic_fallback"]]
    acc = {}
    for rule in ("dimension", "gated_dimension"):
        acc[rule] = sum(1 for r in inj if r["detection"][rule] == EXPECTED_DIM[r["gt_error_type"]])
        acc[rule + "_ng"] = sum(1 for r in inj if not r["generic_fallback"]
                                and r["detection"][rule] == EXPECTED_DIM[r["gt_error_type"]])
    n_ng = len(inj) - len(gen)

    # confusion matrix: injected error type x detected dimension (gated rule)
    types = ["proportion_scale", "part_deletion", "part_displacement", "topology_break",
             "silent_noop", "decoration_removal"]
    cm = collections.Counter((r["gt_error_type"], r["detection"]["gated_dimension"]) for r in inj)
    cols = list(DIMS) + [None]
    cm_rows = []
    for t in types:
        n = sum(cm[(t, c)] for c in cols)
        if not n:
            continue
        cells = []
        for c in cols:
            k = cm[(t, c)]
            hit = (c == EXPECTED_DIM[t])
            cells.append(f'<td class="cm {"hit" if hit and k else ("mark" if k else "zero")}">{k or ""}</td>')
        cm_rows.append(f'<tr><th>{E(t)}</th><td class="exp">{EXPECTED_DIM[t] or "none"}</td>{"".join(cells)}</tr>')

    rows = []
    for r in sorted(recs, key=lambda x: (x["uuid"], x["variant"] != "gt", x["variant"])):
        d = r["detection"]
        exp = EXPECTED_DIM.get(r["gt_error_type"])
        is_gt = r["variant"] == "gt"
        ok = (d["gated_dimension"] == exp)
        verdict = ("baseline" if is_gt else ("hit" if ok else "miss"))
        gt_label = ("GT (no defect)" if is_gt else
                    f'{r["gt_error_type"]} · mag {r["gt_magnitude"]} · expects {exp}'
                    + (" · generic fallback" if r["generic_fallback"] else ""))
        det_label = ("—" if is_gt and d["gated_dimension"] is None else
                     (f'{d["gated_dimension"]}: {d["gated_defect"]}' if d["gated_dimension"] else "no defect above threshold"))
        alt_note = ("" if d["dimension"] == d["gated_dimension"] else
                    f'<div class="alt">largest raw drop was {d["dimension"]}; gate rule overrode it</div>')
        cells = "".join(bar(r["profile"][k], None if is_gt else d["deltas"][k]) for k in DIMS)
        cov = r["evidence"]
        rows.append(f"""<tr class="{verdict}">
  <td class="thumb"><img src="{r['thumb']}" loading="lazy" alt="{E(r['uuid'][:8])} {E(r['variant'])}"></td>
  <td class="id"><b>{E(r['uuid'][:8])}</b><span>{E(r['variant'])}</span></td>
  <td class="gt">{E(gt_label)}</td>
  {cells}
  <td class="det">{E(det_label)}{alt_note}
      <div class="cov">coverage GF2 {E(cov['GF2']['coverage'])} · GF3 {E(cov['GF3']['coverage'])} · GF4 {E(cov['GF4']['coverage'])}</div></td>
  <td class="verdict {verdict}">{verdict}</td>
</tr>""")

    page = f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Task-13-4 · P2 几何验证器检测结果</title>
<style>
:root {{ --bg:#f5f6f8; --card:#fff; --ink:#15171c; --mut:#6b7280; --line:#e3e6eb;
        --acc:#2f6bd8; --good:#15803d; --bad:#b91c1c; --warn:#b45309; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:14.5px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Helvetica Neue",Arial,sans-serif; }}
header {{ background:var(--card); border-bottom:1px solid var(--line); padding:32px 26px 22px; }}
h1 {{ margin:0 0 8px; font-size:23px; }}
h2 {{ font-size:17px; margin:30px 0 10px; }}
header p, .note {{ color:var(--mut); font-size:13.5px; max-width:100ch; margin:5px 0; }}
code {{ font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; background:#eef1f5;
  padding:1px 5px; border-radius:4px; }}
main {{ padding:22px 26px 60px; max-width:1680px; margin:0 auto; }}
.cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:12px; margin:14px 0 4px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:13px 15px; }}
.card b {{ display:block; font-size:22px; letter-spacing:-.5px; }}
.card span {{ color:var(--mut); font-size:12.5px; }}
table {{ width:100%; border-collapse:collapse; background:var(--card);
  border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
th, td {{ padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:middle; text-align:left; }}
thead th {{ background:#f0f2f6; font-size:11.5px; text-transform:uppercase; letter-spacing:.06em; color:var(--mut); }}
td.thumb img {{ width:74px; height:74px; object-fit:cover; border-radius:6px; border:1px solid var(--line); background:#eef1f5; }}
td.id b {{ display:block; font:12.5px ui-monospace,Menlo,monospace; }}
td.id span {{ color:var(--mut); font-size:12px; }}
td.gt {{ font-size:12.5px; max-width:230px; }}
td.m {{ width:92px; font-variant-numeric:tabular-nums; }}
td.m .v {{ font-size:13.5px; }}
td.m .d {{ font-size:11.5px; margin-left:6px; color:var(--mut); }}
td.m.down .d {{ color:var(--bad); font-weight:600; }}
td.m.up .d {{ color:var(--good); }}
td.m .track {{ display:block; height:4px; background:#e8ebf0; border-radius:3px; margin-top:4px; }}
td.m .track i {{ display:block; height:100%; background:var(--acc); border-radius:3px; }}
td.m.down .track i {{ background:var(--bad); }}
td.na {{ color:var(--mut); font-size:12px; }}
td.det {{ font-size:12.5px; max-width:300px; }}
.cov, .alt {{ color:var(--mut); font-size:11.5px; }}
td.verdict {{ font-size:12px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }}
td.verdict.hit {{ color:var(--good); }}
td.verdict.miss {{ color:var(--bad); }}
td.verdict.baseline {{ color:var(--mut); }}
tr.baseline {{ background:#fbfcfe; }}
td.cm {{ text-align:center; font-variant-numeric:tabular-nums; }}
td.cm.hit {{ background:#dcfce7; color:var(--good); font-weight:700; }}
td.cm.mark {{ background:#fee2e2; color:var(--bad); font-weight:600; }}
td.cm.zero {{ color:#c9ced6; }}
td.exp {{ color:var(--mut); font-size:12px; }}
ul {{ max-width:100ch; }}
li {{ margin:6px 0; font-size:13.5px; }}
.wrap {{ overflow-x:auto; }}
</style></head><body>
<header>
  <h1>Task-13-4 · P2 几何验证器：GT 缺陷 vs 检出缺陷</h1>
  <p>代码 <code>0_Code/mechanism/code/p2-kai/</code>；数据 <code>data/zero-cad-10samples-gf</code>（10 GT + 40 注入变体）。
     协议来自 <code>answer2/task-13_08-19-plan.html</code>，指标定义来自 <code>answer2/task-2_08-16-p2.html</code>。</p>
  <p><b>与 P2 原文的偏差（先声明）：</b>原文 GF1/GF2 用冻结 CLIP/SigLIP 做图文对齐；本机没有 torch/CLIP，且 Task-13-4 要求的是
     <i>几何</i> 验证器，所以 GF1/GF2 改为对同一批契约字段做确定性三维测量。GF3/GF4 按原文实现
     （关系谓词 + <code>GF4_r = exp(-|log(r_obs/r_target)|/σ_r)</code>，σ_r 取契约里冻结的 tolerance）。</p>
  <p><b>验证器只看变体网格 + 该 uuid 的 contract.yaml。</b>不读 GT 网格、不读 <code>injection.json</code>；标签只在打完分之后拿来对账。
     部件→检测器、比例声明→测量配方的绑定表写在 <code>bindings.py</code>，对应 P2 里"由 P1 Gate 绑定 part mask"这一步，
     每个 uuid 只写一次，GT 与全部变体共用。</p>
  <p>判定规则（跑前冻结）：与<b>同 uuid 的 GT 基线</b>比较，某维掉分 ≥ {R['thresholds']['DETECT_DELTA']} 即判该维缺陷；
     GF1→topology_break、GF2→part_deletion/silent_noop、GF3→part_displacement、GF4→proportion_scale。
     两条规则并列报告：<i>argmin</i>（掉得最多的维获胜）与 <i>gated</i>（先过 P1 连通性闸门：已断成多体的资产先判 GF1，
     因为它的比例已经不可测）。</p>
</header>
<main>
  <div class="cards">
    <div class="card"><b>{len(recs)}</b><span>已打分资产（10 GT + 40 注入）</span></div>
    <div class="card"><b>{acc['gated_dimension']}/{len(inj)}</b><span>gated 规则命中（{acc['gated_dimension']/len(inj)*100:.0f}%）</span></div>
    <div class="card"><b>{acc['gated_dimension_ng']}/{n_ng}</b><span>剔除 generic fallback 后（{acc['gated_dimension_ng']/n_ng*100:.0f}%）</span></div>
    <div class="card"><b>{acc['dimension']}/{len(inj)}</b><span>argmin 规则命中</span></div>
    <div class="card"><b>{R['seconds']}s</b><span>50 个资产全量打分耗时</span></div>
  </div>

  <h2>混淆矩阵 · 注入类型 × 检出维度（gated）</h2>
  <div class="wrap"><table>
    <thead><tr><th>injected</th><th>expects</th><th>GF1</th><th>GF2</th><th>GF3</th><th>GF4</th><th>none</th></tr></thead>
    <tbody>{''.join(cm_rows)}</tbody>
  </table></div>
  <p class="note">绿格 = 打在预期维度上；红格 = 打偏。<b>A2（对角占优）不成立</b>：断体类注入会同时压垮 GF3/GF4，
     因为飞离的碎块直接改写了 bbox 与关系测量；这正是 gated 规则存在的理由，也是本次标定的主要结论之一。</p>

  <h2>逐资产结果</h2>
  <div class="wrap"><table>
    <thead><tr><th>view 0°</th><th>uuid / variant</th><th>GT 缺陷（标签）</th>
      <th>GF1</th><th>GF2</th><th>GF3</th><th>GF4</th><th>检出缺陷</th><th></th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table></div>

  <h2>结论与已知盲区</h2>
  <ul>
    <li><b>GT 基线不是满分，而且不是指标的错。</b>四个 GT 的 GF2 明显低于 1，追下去都是数据本身的契约–几何不一致：
        <code>3753d810</code> 的 <code>cutBlind(65)</code> / <code>cutBlind(8)</code> 方向为正，孔和凹槽根本没切进材料（体积 55 692 mm³ ≈ 未切的 56 000）；
        <code>c4db4bf8</code> 的 <code>polarArray(count=11, angle=360/11)</code> 把 11 个孔挤在 32.7° 内，融成一条槽；
        <code>87e570d9</code> 只切出 3 个安装孔中的 2 个；<code>bfa02503</code> 的沉头孔落在扇形材料之外。
        契约是从符号生成的，几何里没有——这正是 plan 里 A3 想抓的那类问题，只是出现在 GT 上。</li>
    <li><b>silent_noop 在"目标特征本来就不存在"时不可检。</b><code>87e570d9/silent_noop</code> 移走的正是上面那个本就没切出来的凹槽，
        四个维度 delta 全 0。这不是指标失灵，是这条样本没有可测的信息量，应从 A3 统计里剔除。</li>
    <li><b>7/10 的 part_displacement 用的是 generic <code>bisect_shift</code> 兜底注入</b>，它会把实体切成两块，
        GF1 必然先响应。README 已声明这些样本不参加 A2；本表把它们单列，剔除后 gated 命中率 {acc['gated_dimension_ng']}/{n_ng}。</li>
    <li><b>GF4 覆盖率是当前最大的短板。</b>扇形件 <code>bfa02503</code> 的三条比例声明全部不可测（回转轴不在实体上，无法从网格反解），
        因此该 uuid 的 proportion_scale（revolve_angle 50°→60°）完全检不出。要补上，需要在 P1 Gate 里就把回转轴/参考基准一起冻结下来。</li>
    <li><b>还检不出的两类真实位移：</b><code>447aae45</code> 把一个滚花槽刀具平移 21 mm（槽数不变、外形不变），
        以及 <code>eacaf3f2</code> 通道整体偏移后 GF2/GF4 一起动但 GF3 不动——GF3 目前只有连通性、对称性、等距性、同轴性四类谓词，
        缺"某部件相对某基准的绝对位置"这一条，而这条需要契约给出可测的基准，不能只写"centred"。</li>
  </ul>
  <p class="note">复跑：<code>env_mujoco/bin/python code/p2-kai/run_eval.py</code> 然后
     <code>env_mujoco/bin/python code/p2-kai/report.py --out {E(os.path.basename(a.out))}</code>。
     产物：<code>code/p2-kai/results/results.json</code>（含每条 check 的证据）与 <code>scores.csv</code>。</p>
</main></body></html>"""
    open(a.out, "w").write(page)
    print("wrote", a.out, len(page), "bytes;", len(recs), "rows;", len(os.listdir(assets)), "thumbnails")


if __name__ == "__main__":
    main()
