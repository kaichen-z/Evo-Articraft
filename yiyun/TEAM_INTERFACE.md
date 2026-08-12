# 与团队代码的接口

本目录只负责 A1–A6。输入输出约定与另外两组保持同构，但不要求把三个人的源码放进
同一个 Python package。

## 输入

每个评分头使用统一函数形式：

```python
score(signals, contract, consts) -> MetricResult
```

- `contract`：由 Prompt 提取并冻结的明确要求；
- `signals`：parser、geometry、renderer 或 VLM 产生的原始测量；
- `consts`：集中管理的阈值和权重。

评分函数运行时不调用 LLM/VLM，也不启动 simulator。

## 输出

每项结果至少包含：

```text
metric
score
prediction
threshold
confidence
coverage
tools
raw_measurements
failure_reason
repair_hint
```

额外保留 `sub_scores`、`evidence`、`provisional_params` 和 `diagnostics`，供误报/漏报
分析和后续 verifier 演化使用。

## 分工边界

- `yiyun/`：A1–A6；
- Wanglin：B7–B10 和公共标签/评测基础；
- Xuge：B11–B14、mesh/FK/MuJoCo 后端。

接口对齐不等于判别效果已经对齐。每组都需要在相同的数据划分和人工标签上报告
coverage、precision、recall、F1、AUC 和 Cohen's kappa。
