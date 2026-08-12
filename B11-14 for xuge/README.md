# ArtiCraft Verifier — B11–B14

PRO-12 自动验证器中 B11–B14 四项指标的精确计算。
A1–A6 / B7–B10 由他人负责, 本仓库不实现。

## 现状

- [x] `types.py` / `consts.py` / 契约 schema
- [x] `metrics/b11–b14.py` 纯函数实现
- [x] 柜子案例验收测试 (四个分数 1e-3 复现)
- [ ] `primitives/` 几何扫掠 (待仿真器确定)
- [ ] `sim/` 仿真器 runner (待仿真器确定)

**本轮不依赖任何仿真器**, 测试全部用手写 signals dict。
仿真器一旦确定, 只需新增 `sim/runner.py` 产生 signals, 四个打分函数一行不改。

## 运行

```bash
pip install pytest
pytest -q
```

## 架构

```
signals(dict) ──┐
contract(dict) ─┼─> metrics/bXX.score() ──> MetricResult ──> report/
consts(Consts) ─┘        (纯函数)
```

`score()` 不读文件、不启仿真器、不用全局状态 —— 因此换仿真器
(PyBullet / MuJoCo / Isaac Sim) 不影响打分逻辑。

## 关键约束

1. 工具故障 != 资产失败 —— NaN/发散/超时返回 `coverage="tool-failure"`,
   `score=None`, 绝不返回 0.0
2. 不适用返回 `not-applicable`, `score=None`, 不进聚合分母
3. `coverage` 必须与 `score` 同时返回
4. 每个失败判定可回溯到具体连杆对 / 姿态索引 / 时间步
5. 所有常量来自 `consts.py`, 公式里禁止硬编码
6. 未冻结的参数标 PROVISIONAL, 并在每份结果的 `provisional_params` 中报告

## 待确认

见 `QUESTIONS.md` —— 12 项规范问题, 其中 3 项阻塞可复现性。
