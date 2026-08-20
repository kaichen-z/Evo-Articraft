"""从 out/results.json 整页生成 HTML 报告（数据构建逻辑在 report_common.py）。

生成后的 out/p2_smoke_report.html 是独立文件，文字可直接在该文件里编辑。
注意：重新运行本脚本会用模板覆盖手工编辑；只想刷新数据请用 update_report_data.py。
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from report_common import (OUT, load_results, compute_stats, build_rows,
                           build_evidence, build_human_comparison)

REPORT = OUT / "p2_smoke_report.html"
RUNTIME_S = 21

results, proto = load_results()
st = compute_stats(results)
prov = "、".join(f"{k}={v}" for k, v in proto["provisional_params"].items())

html = """<title>Evo-Articraft P2 冒烟报告</title>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap">
<style>
:root{
  --paper:#f5f3ed; --card:#fffefa; --ink:#172337; --muted:#637186;
  --navy:#15314e; --teal:#087f78; --teal-soft:#e1f3ef; --line:#d8d5cd;
  --gold:#a56f18; --gold-soft:#f8efd9; --red:#a43f37; --red-soft:#f7e6e2;
  --hero-a:#132e4b; --hero-b:#126862; --hero-ink:#eef6f4; --hero-sub:#c8dfda;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --paper:#111a22; --card:#18242e; --ink:#e6edf1; --muted:#93a5b1;
    --navy:#cddceb; --teal:#3cb8ac; --teal-soft:#12332f; --line:#2b3a45;
    --gold:#d4a355; --gold-soft:#2e2413; --red:#d97f72; --red-soft:#3a1f1b;
    --hero-a:#0d1f33; --hero-b:#0d4741; --hero-ink:#eef6f4; --hero-sub:#a7c5bf;
  }
}
:root[data-theme="dark"]{
  --paper:#111a22; --card:#18242e; --ink:#e6edf1; --muted:#93a5b1;
  --navy:#cddceb; --teal:#3cb8ac; --teal-soft:#12332f; --line:#2b3a45;
  --gold:#d4a355; --gold-soft:#2e2413; --red:#d97f72; --red-soft:#3a1f1b;
  --hero-a:#0d1f33; --hero-b:#0d4741; --hero-ink:#eef6f4; --hero-sub:#a7c5bf;
}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.72;
  font-family:Inter,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",ui-sans-serif,sans-serif}
.hero{background:linear-gradient(120deg,var(--hero-a),var(--hero-b));color:var(--hero-ink);padding:36px 24px 28px}
.hero-in,.main{max-width:1100px;margin:0 auto}
.eyebrow{font-size:.72rem;font-weight:800;letter-spacing:.14em;text-transform:uppercase;color:var(--hero-sub);margin-bottom:8px}
h1{margin:0;font-family:Georgia,"Times New Roman","Songti SC",serif;font-weight:600;
  font-size:clamp(1.7rem,4vw,2.4rem);line-height:1.12;letter-spacing:-.02em;text-wrap:balance}
.hero p{margin:10px 0 0;color:var(--hero-sub);max-width:74ch}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.chips span{border:1px solid color-mix(in srgb,var(--hero-ink) 30%,transparent);
  border-radius:999px;padding:3px 11px;font-size:.78rem;color:var(--hero-ink)}
.main{padding:26px 24px 64px;display:grid;gap:30px}
h2{margin:0 0 6px;font-family:Georgia,"Songti SC",serif;font-weight:600;color:var(--navy);font-size:1.4rem}
h3{color:var(--navy)}
.sec-note{margin:0 0 14px;font-size:.92rem;color:var(--muted);max-width:82ch}
p{margin:8px 0;max-width:82ch}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px}
.stat b{display:block;font-size:1.55rem;font-weight:800;color:var(--teal);font-variant-numeric:tabular-nums}
.stat span{font-size:.82rem;color:var(--muted)}
.prep{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:12px}
.prep-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.prep-card h3{margin:0 0 8px;font-size:1.02rem}
.prep-card p{margin:6px 0;font-size:.93rem}
.prep-card ul{margin:6px 0;padding-left:1.2rem;font-size:.93rem}
.prep-card li{margin:4px 0}
.gf-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.gf-card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.gf-card .gf-id{display:inline-block;background:var(--teal);color:#fff;font-weight:800;
  border-radius:8px;padding:2px 9px;font-size:.85rem;margin-bottom:8px}
.gf-card h3{margin:0 0 6px;font-size:1rem}
.gf-card p{margin:6px 0;font-size:.9rem}
.gf-card .delta{margin-top:8px;padding:8px 10px;border-left:3px solid var(--gold);
  background:var(--gold-soft);color:var(--ink);border-radius:6px;font-size:.86rem}
.legend{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;font-size:.9rem}
.legend b{color:var(--navy)}
.legend ul{margin:6px 0 0;padding-left:1.2rem}
.legend li{margin:4px 0}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:14px;background:var(--card)}
table{border-collapse:collapse;width:100%;min-width:860px;font-size:.88rem}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
th{font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);white-space:nowrap}
tr:last-child td{border-bottom:none}
.thumb-cell img{width:84px;height:84px;object-fit:cover;border-radius:9px;border:1px solid var(--line);display:block}
.case-label{font-weight:600}
.case-cat{font-size:.8rem;color:var(--muted)}
.case-rid{font-family:Consolas,Menlo,monospace;font-size:.68rem;color:var(--muted)}
.num{font-variant-numeric:tabular-nums;white-space:nowrap}
.sub{font-size:.75rem;color:var(--muted)}
.score{font-weight:700;padding:1px 7px;border-radius:6px}
.score.ok{color:var(--teal);background:var(--teal-soft)}
.score.mid{color:var(--gold);background:var(--gold-soft)}
.score.bad{color:var(--red);background:var(--red-soft)}
.rank{font-weight:700;padding:0 5px;border-radius:5px}
.rank.ok{color:var(--teal)} .rank.mid{color:var(--gold)} .rank.bad{color:var(--red)}
.na{color:var(--muted)}
.muted{color:var(--muted)}
.ev-list{display:grid;gap:10px}
.ev-case{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 16px}
.ev-head{font-weight:600;display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.ev-case ul{margin:8px 0 0;padding-left:1.2rem}
.ev-case li{margin:3px 0;font-size:.87rem}
code{font-family:Consolas,Menlo,monospace;font-size:.9em;color:var(--teal);background:var(--teal-soft);
  padding:.08em .3em;border-radius:5px}
.tag-fused{font-size:.68rem;font-weight:700;color:var(--gold);background:var(--gold-soft);
  border-radius:5px;padding:1px 6px;letter-spacing:.03em}
.qa{counter-reset:q;display:grid;gap:10px}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px 14px 56px;position:relative;font-size:.93rem}
.q::before{counter-increment:q;content:"Q" counter(q);position:absolute;left:14px;top:14px;
  width:30px;height:26px;border-radius:8px;display:grid;place-items:center;
  background:var(--teal-soft);color:var(--teal);font-weight:800;font-size:.85rem}
.q b{color:var(--navy)}
footer{font-size:.78rem;color:var(--muted);border-top:1px solid var(--line);padding-top:14px}
footer code{background:none;color:var(--muted)}
</style>

<div class="hero"><div class="hero-in">
  <div class="eyebrow">Evo-Articraft · P2 Geometry Fidelity</div>
  <h1>GF1–GF4 首版实现 · 20 案例运行</h1>
  <p>本页说明四件事：动手写指标之前做了哪些准备、四个指标各自如何实现（以及在规格之外补了什么）、
     20 个案例的结果和各项数据的含义、以及需要和 P0/P1/规格作者确认的问题。</p>
  <div class="chips">
    <span>__DATE__</span><span>渲染 448² · 4 方位角 · 仰角 −20°</span>
    <span>ViT-B-32 · laion2b_s34b_b79k（冻结）</span><span>MuJoCo 3.11 离屏</span>
  </div>
</div></div>

<div class="main">

<section>
  <h2>一、动手之前的准备</h2>
  <div class="prep">
    <div class="prep-card">
      <h3>按 P0/P1 的格式自动起草了替身契约与绑定</h3>
      <p><b>为什么要做</b>：GF3/GF4 验证的是"声明"（部件关系、比例），GF1/GF2 需要评分文本，这些按设计全部来自 P0 的结构化契约；部件到 body/geom 的绑定来自 P1 Gate。两者都还没交付，但 GF 代码必须现在就能跑、将来还要能无缝接上——所以我们照 P0 文档的真 schema 自动起草替身，<b>接口形状与真货完全一致，上游就绪后整文件替换、评分代码不动</b>。</p>
      <p><b>怎么做的</b>（每条声明都带 source 字段注明来历，存于 <code>specs/&lt;rid&gt;.json</code>，可手工修订）：</p>
      <ul>
        <li><code>global_form</code> ← 案例类别名（GF1 文本）；<code>part_geometry</code> ← 零件命名（GF2 文本）。</li>
        <li><code>part_relations</code> ← URDF 关节拓扑：文件里声明了"抽屉与柜身之间有滑轨"，即得一条可验证的 <code>drawer attached_to body</code>；再加命名启发（名字含 drawer → inside，含 lid → above）。声明是作者意图、验证用实际几何，两个通道独立，不构成自证。</li>
        <li><code>proportion_claims</code> ← 命名对称组：wheel_0…wheel_4 理应一样大（target_ratio=1，tolerance=0.10）。预期值来自命名约定而非实测，同样避免循环。</li>
        <li>部件引用一律经<b>绑定层</b>解析（实例名 → 抽象 part 展开全部实例 → geom 名兜底），今天用 URDF link 名起草，将来直接换成 Gate 的绑定表。</li>
      </ul>
    </div>
    <div class="prep-card">
      <h3>选了 20 个案例，按机构类型配齐而非随机抽</h3>
      <p><b>怎么选的</b>：从 110 个训练案例按关键词配 20 个槽位——棱柱抽拉类 4（抽屉柜、伸缩臂、台钳、收银机）、旋转开合类 6（园门、电柜门、垃圾桶盖、翻盖手机、眼镜、帕尼尼机）、连续转子类 4（塔扇、风力机、转盘、水轮）、链式 2（三自由度腕、指骨链）、混合家电 4（办公椅、显示器支架、洗碗机、打印机）。</p>
      <p><b>为什么这么选</b>：第一次全量运行的目标是验证方法在各种机构形态上都能跑，所以优先覆盖面而非数量；同时刻意拉开两个极值——尺度从 0.27 米（翻盖手机）到 280 米（风力机），检验按物体对角线 D 归一化的阈值是否真正尺度无关；部件数从 3（眼镜）到 25（收银机），后者是 GF2 的压力位（一堆外形相同的按键）。伸缩臂、转盘这类嵌套结构则是 GF3 的压力位。</p>
    </div>
  </div>
</section>

<section>
  <h2>二、四个指标的实现与我们做的改动</h2>
  <p class="sec-note">指标定义以 P2 规格页为准，此处不复述；只说实现选择和规格之外的增补（金色框）。</p>
  <div class="gf-grid">
    <div class="gf-card">
      <span class="gf-id">GF1</span>
      <h3>实现</h3>
      <p>冻结渲染协议：统一中性灰材质、方位角 0/90/180/270、仰角 −20°、相机距离 1.7×AABB 对角线、分割通道把背景抠成浅灰。编码器冻结为 open_clip ViT-B-32 / laion2b_s34b_b79k，四视角图文余弦取均值。</p>
      <div class="delta"><b>规格之外的增补</b>：裸余弦挤在 0.13–0.36 的窄带里没有绝对意义，我们加了 20 类干扰项 softmax——每个资产的照片在全部 20 个类别文本里"认亲"，报告认对自己的概率 p 与排名；另附最差视角 min_cos，防止单面坍塌被均值抹平。</div>
    </div>
    <div class="gf-card">
      <span class="gf-id">GF2</span>
      <h3>实现</h3>
      <p>逐零件隔离渲染：其余 geom 移入隐藏组、相机按该零件自身 AABB 重新构图，同样四视角；按规格先聚合视角、再对零件宏平均。零件文本来自 part_geometry 的形状描述。</p>
      <div class="delta"><b>规格之外的增补</b>：兄弟部件辨识——每张零件照片在本资产全部零件文本里做选择题，报告认对概率与实际最像谁（best_match），用于诊断"零件做得不像自己"；无几何、AABB 退化的零件记不可测，不计入宏平均。</div>
    </div>
    <div class="gf-card">
      <span class="gf-id">GF3</span>
      <h3>实现</h3>
      <p>四种关系落成确定性判据（容差一律按整体对角线 D 归一化）：attached_to = 两零件所有 geom 对的最小符号距离，sd&lt;−0.005D 判穿透、≤0.01D 判接触（唯一算满足）、其余判分离；inside = A 的 AABB 体积落入 B 的比例 ≥0.7；above = z 向间隙 ≥−0.05D 且水平投影重叠 ≥0.3；aligned = 偏轴中心偏移 ≤0.05D。声明指向抽象部件时展开为全部实例、须全部满足。</p>
      <div class="delta"><b>规格之外的决定</b>：证据落到实例对级（哪两个零件、实测几米）；引用解析失败或零件无几何记 unmeasurable、不进分母——测不了和做得差是两回事。</div>
    </div>
    <div class="gf-card">
      <span class="gf-id">GF4</span>
      <h3>实现</h3>
      <p>尺寸从 q0 世界系 AABB 提取：height=Z 边、length=水平长边、width=水平短边、area=投影面积、volume=AABB 体积。成组声明（[1,1,1]）展开为对第一成员的逐对比较；按规格公式 exp(−|log(r_obs/r_target)|/σ) 打分。</p>
      <div class="delta"><b>规格之外的决定</b>：P0 声明的是 tolerance、公式要的是 σ，两者换算规格未定，我们暂用 σ=ln(1+tolerance)（恰好使"偏到容差边界"得分 = 1/e≈0.37）；measure 的几何定义也是暂定约定。两者都列入下方问题清单。</div>
    </div>
  </div>
</section>

<section>
  <h2>三、20 案例结果</h2>
  <div class="stats">
    <div class="stat"><b>__N_CASES__/20</b><span>案例端到端跑通 · __N_TOOLFAIL__ 工具故障 · 单轮 __RUNTIME__ 秒</span></div>
    <div class="stat"><b>__N_PARTS__</b><span>零件完成隔离渲染与 GF2 打分</span></div>
    <div class="stat"><b>__N_RANK1__/20</b><span>GF1 在 20 类干扰中排第 1</span></div>
    <div class="stat"><b>__N_FAILED__/__N_CLAIMS__</b><span>GF3 声明判负 · 其中 __N_PEN__ 条为穿透</span></div>
  </div>

  <div class="legend" style="margin-top:14px">
    <b>表中各列数据的含义</b>
    <ul>
      <li><b>GF1 列</b>：上行是四视角图文余弦均值（只在同类资产间可比，不是百分制）；下行 p = 该资产照片在 20 个类别文本里认出自己的概率，# = 排名。<b>读 p 和排名，别读裸余弦。</b></li>
      <li><b>GF2 列</b>：上行是零件宏平均余弦；下行 p̄ = 兄弟部件辨识概率的均值（此值低未必是缺陷——收银机 25 个零件里一堆外形相同的按键，天然认不出彼此），"N 件"= 参与打分的零件数。</li>
      <li><b>GF3 列</b>：分数 = 满足的声明 / 可测的声明；下行 x/y = 满足数/可测数，"·k 不可测"= 引用解析不到的声明数。注意各案例声明数量不同（1–22 条），满分的含金量不等。</li>
      <li><b>GF4 列</b>：分数 = 各比例对得分的均值；"N 对"= 成组声明展开后的比较对数。</li>
      <li><b>n/a</b> = 该案例没有这类声明或全部不可测，<b>不是 0 分</b>，也不进任何平均。</li>
    </ul>
  </div>

  <div class="tablewrap" style="margin-top:14px"><table>
    <thead><tr><th>渲染</th><th>案例</th><th>GF1 整体形态</th><th>GF2 部件几何</th><th>GF3 部件关系</th><th>GF4 比例</th></tr></thead>
    <tbody>__ROWS__</tbody>
  </table></div>

  <h3 style="margin-top:22px">GF3 失败证据（逐条可回溯）</h3>
  <p class="sec-note">说明：separated / contact / penetration 是 attached_to 这一种关系的测量结果三态（sd 正得多=悬空分离、零附近=接触、负=互相嵌入），只有 contact 算满足；inside/above/aligned 各有自己的失败度量。本次判负的声明里，attached_to 的失败<b>全部以 penetration 形态出现、0 条 separated</b>：伸缩臂三节杆彼此嵌入 5–13 cm，洗碗机碗架穿进机身约 30 cm，转盘中轴插在实心盘面里 13–14 cm；唯一的非 attached_to 失败是打印机的一条 above 声明——盖子嵌坐在机身翻边之间、底面比机身顶沿低 0.069·D，属于 above 语义与容差待校准的情形。sd 为最小符号距离（负 = 穿透深度）。</p>
  <div class="ev-list">__EVIDENCE__</div>
</section>

__COMPARISON__
<section>
  <h2>四、想提的问题</h2>
  <div class="qa">
    <div class="q"><b>子部件引用的绑定约定。</b>P0 示例里出现了 <code>drawer_front</code> 这类比 part 更细的引用。在 MJCF 里它约定为 geom 名、site 名，还是 Gate 绑定表里单独的一层？我们目前按 geom 名兜底解析，如果约定不同需要改解析器。</div>
    <div class="q"><b>tolerance → σ 的换算。</b>P0 声明 tolerance（如 0.10），P2 公式用 σ_r，换算规则没有写。我们暂用 σ = ln(1+tolerance)，效果是"偏到容差边界得 1/e≈0.37 分"。这个语义是否符合公式作者的本意？</div>
    <div class="q"><b>measure 的几何定义。</b>length/width/height 对摆放旋转过的零件有歧义。我们暂用 q0 世界系 AABB（height=Z 边、length=水平长边、width=水平短边），正式版是否应换 OBB？谁来冻结这套定义？</div>
    <div class="q"><b>attached / above 的容差怎么定。</b>翻盖手机、收银机屏幕、园门锁杆都是 2 mm 量级（0.005–0.01·D）的轻微压入，恰在当前容差外被判负；打印机盖子嵌坐在机身翻边之间也被 above 判负。这些算建模常态还是缺陷？答案直接决定 ATTACH_MAX_PEN / ABOVE_TOL 的冻结值，建议用一批人工标注案例校准。</div>
    <div class="q"><b>GF1/GF2 会进 Evo 循环当适应度吗？</b>如果这两个分数参与选择压力，生成器可能学会针对固定编码器刷分（对抗纹理）而非改进真实几何。若要当适应度，建议只用确定性的 GF3/GF4；GF1/GF2 作观测报表，或至少双编码器互备。</div>
    <div class="q"><b>MJCF 资产从哪来？</b>ArtiCraft 现存资产全部是 URDF（缓存无一个 .xml，代码库也无 MJCF 导出能力），而 P1 规格按 MJCF 原生书写。是新生成管线直出 MJCF，还是需要 URDF→MJCF 转换步骤？另请 P1 侧确认绑定表交付格式。（URDF 融合导致零件名丢失的问题我们已在加载层注入 <code>fusestatic="false"</code> 解决，不再依赖 fused-proxy 别名。）</div>
  </div>
</section>

<footer>
  暂定参数（正式冻结前需校准，已随每份结果原样回显）：__PROV__。<br>
  产物：<code>out/results.json</code>（全量证据）· <code>out/summary.csv</code> · <code>out/renders/&lt;rid&gt;/</code>（整体 + 逐部件渲染）·
  spec 替身（P0 真格式，可手工修订后重跑）在 <code>specs/&lt;rid&gt;.json</code>。
</footer>

</div>
"""

html = (html
        .replace("__DATE__", "2026-08-19")
        .replace("__RUNTIME__", str(RUNTIME_S))
        .replace("__N_CASES__", str(st["n_cases_ok"]))
        .replace("__N_TOOLFAIL__", str(st["n_tool_fail"]))
        .replace("__N_PARTS__", str(st["n_parts"]))
        .replace("__N_RANK1__", str(st["n_rank1"]))
        .replace("__N_CLAIMS__", str(st["n_claims"]))
        .replace("__N_FAILED__", str(st["n_failed"]))
        .replace("__N_PEN__", str(st["n_pen"]))
        .replace("__ROWS__", build_rows(results))
        .replace("__EVIDENCE__", build_evidence(results))
        .replace("__COMPARISON__", build_human_comparison(results))
        .replace("__PROV__", prov))

REPORT.write_text(html, encoding="utf-8")
print(f"报告已生成: {REPORT}  ({REPORT.stat().st_size/1024:.0f} KB)")
