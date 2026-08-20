"""P2 Geometry Fidelity 冻结常量。

全部为 PROVISIONAL 初值：跑通流水线用，正式冻结前需在校准集上定。
所有阈值会原样回显在结果 JSON 的 provisional_params 里。
"""

# ---------- 渲染协议 ----------
RENDER_SIZE = 448            # 渲染分辨率 (方形)
AZIMUTHS = (0.0, 90.0, 180.0, 270.0)
ELEVATION = -20.0            # 相机俯仰角 (度)
DIST_FACTOR = 1.7            # 相机距离 = DIST_FACTOR × 包围盒对角线
NEUTRAL_GRAY = 0.72          # 中性材质灰度
BG_GRAY = 240                # 背景灰度 (0-255)
HEADLIGHT_AMBIENT = 0.40
HEADLIGHT_DIFFUSE = 0.65

# ---------- GF1/GF2 编码器 ----------
CLIP_ARCH = "ViT-B-32"
CLIP_CKPT = "laion2b_s34b_b79k"   # 冻结 checkpoint

# ---------- GF3 关系谓词容差 (均以整体包围盒对角线 D 归一化) ----------
ATTACH_MAX_GAP = 0.010       # attached: 最小符号距离 ≤ 0.010·D
ATTACH_MAX_PEN = 0.005       # attached: 穿透不得超过 0.005·D
INSIDE_MIN_FRAC = 0.70       # inside: A 的 AABB 体积落入 B 的 AABB 的比例 ≥ 0.7
ABOVE_TOL = 0.05             # above/below: z 向间隙 ≥ −0.05·D
ABOVE_MIN_OVERLAP = 0.30     # above/below: 水平投影重叠 ≥ 0.3 × A footprint
ALIGN_TOL = 0.05             # aligned: 偏轴中心偏移 ≤ 0.05·D

# ---------- GF3 新谓词 (2026-08-20 语料扫描后新增, 全部 PROVISIONAL) ----------
SUPPORT_PROBE_DELTA = 0.005  # supported_by: 向 −Z 虚拟下移的探测步长 (×D)
SUPPORT_MIN_DROP_FRAC = 0.2  # 下移后 sd 下降 ≥ 0.2×步长 即判"被挡住"
                             # (不要求掉满一个步长: 薄导轨等特征会使穿透深度饱和,
                             #  实测 2mm 厚导轨挡 5.8mm 探测只报 −2mm)
THROUGH_MIN_EXTEND = 0.01    # through: A 沿某轴在 B 两侧各伸出 ≥ 0.01·D
BETWEEN_TOL = 0.10           # between: A 中心到 B-C 连线段的偏距 ≤ 0.10·D
AROUND_MIN_FRAC = 0.50       # around: B 的 AABB 落入 A 的比例 ≥ 0.5
SYM_TOL = 0.05               # symmetric: 镜像位置误差 ≤ 0.05·D
SYM_SIZE_LOGTOL = 0.15       # symmetric: 两件长边 |log 比| ≤ 0.15

# ---------- GF4 ----------
SIGMA_R = 0.15               # claim 未声明 tolerance 时的兜底 σ
DEFAULT_TOLERANCE = 0.10     # 替身自动起草的 claims 用的容差
TOL_TO_SIGMA = "log1p"       # σ = ln(1+tolerance)；容差边界处得分恰为 1/e ≈ 0.368
# measure 提取约定 (对 q0 世界系 AABB)：height=Z 边; length=水平长边;
# width=水平短边; area=水平投影面积; volume=AABB 体积; long=三边最大
MEASURE_CONVENTION = "aabb_v0"

PROVISIONAL_PARAMS = [
    "DIST_FACTOR", "ELEVATION", "ATTACH_MAX_GAP", "ATTACH_MAX_PEN",
    "INSIDE_MIN_FRAC", "ABOVE_TOL", "ABOVE_MIN_OVERLAP", "ALIGN_TOL",
    "SUPPORT_PROBE_DELTA", "SUPPORT_MIN_DROP_FRAC", "THROUGH_MIN_EXTEND",
    "BETWEEN_TOL", "AROUND_MIN_FRAC", "SYM_TOL", "SYM_SIZE_LOGTOL",
    "SIGMA_R", "DEFAULT_TOLERANCE", "TOL_TO_SIGMA", "MEASURE_CONVENTION",
]
