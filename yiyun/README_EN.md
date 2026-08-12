# Yiyun · ArtiCraft Verifier A1–A6

This directory contains the first executable implementation of metrics A1–A6 in the PRO-12 automatic-verifier proposal.

It is an independent submission under `kaichen-z/Evo-Articraft`. It does not duplicate Wanglin's B7–B10 or Xuge's B11–B14. The three submissions share the same metric IDs and output fields:

```text
score · prediction · threshold · confidence · coverage · evidence · repair_hint
```

The implementation follows the engineering conventions used by `B11-14 for xuge`:

- `score(signals, contract, consts)` in each metric module is a pure function;
- scoring does not invoke an LLM/VLM, read files, or launch a simulator;
- tool failures are not treated as asset failures;
- `not-applicable`, `unsupported`, and `partial` are not disguised as passes;
- every detected failure includes traceable evidence and a repair suggestion;
- thresholds and weights are centralized in `consts.py`.

## Data flow

```text
Prompt --(offline contract extractor + review)--> contract.json
Asset  --(parser / geometry / renderer / VLM)--> signals.json
contract + signals --> metrics/a1.py ... a6.py --> MetricResult
```

The Contract specifies only what must be checked. It is not itself evidence that the generated asset is correct. Actual measurements must come from `model.py`, the compiled geometry, kinematics, or rendered views.

## Metrics

| Metric | Contract input | Measured signals |
|---|---|---|
| A1 Part decomposition and movability | `required_movables` | expected, matched, actual, and spurious movable instances |
| A2 Part count and type | `required_parts` | actual counts and semantic type matches |
| A3 Required structural completeness | `required_parts`, `required_interfaces` | matched parts and explicit physical interfaces |
| A4 Shape, dimensions, and proportion realism | `appearance_claims`, optional `category_scale` | VLM realism, cross-view consistency, and scale evidence |
| A5 Position, orientation, and assembly relations | `spatial_relations` | position, orientation, functional side, and neighborhood measurements |
| A6 Initial-state integrity | generally applicable | initial penetration, detached-volume ratio, and unsupported gap |

## What is implemented

- A1–A6 deterministic score heads, coverage states, evidence serialization, and numerical guards.
- A static AST frontend for real ArtiCraft `model.py` files.
- Deterministic exclusive name matching, preventing one generated part from satisfying several Prompt requirements simultaneously.
- A1 repeated-instance accounting: an explicit `count: 4` contributes four expected movable instances.
- A2 unspecified-count semantics: `count: null` means “this category must exist,” not “exactly one.”
- Offline Codex/Gemini Contract extraction for Prompt-explicit A3 interfaces, A4 appearance claims, and A5 spatial relations. Every scored requirement must contain a verbatim Prompt quote.
- A3 diagnostic checking for explicit hinge, axle, rail, bracket, and similar interface solids, combined with the declared joint connection.
- A5 default-pose geometry measurements for directly representable relations such as `above`, `below`, `between`, `inside`, `attached`, `adjacent`, and `centered`.
- A4 reproducible eight-view offscreen rendering and raw Codex/VLM visual measurement.
- A6 real default-pose mesh-overlap and isolated-part checks through the ArtiCraft SDK.
- A6 detached-volume measurement using analytic solid volumes or watertight mesh volumes, with an explicit part-count fallback when exact volume is unavailable.
- Batch comparison against frozen human annotations, including coverage, AUC, precision, recall, F1, balanced accuracy, Cohen's kappa, and false-positive/false-negative record IDs.

## Important limitations

- Prompt-to-asset semantic matching remains a research problem. The current deterministic matcher is auditable but not fully semantic.
- The A3 interface signal is diagnostic. A named hinge or rail solid plus a joint does not prove that its detailed geometry is mechanically valid.
- A4 raw VLM probabilities have not yet been calibrated against held-out human A4 labels. Consequently, current A4 outputs remain `partial/abstain` rather than hard pass/fail decisions.
- A5 currently uses default-pose AABBs for supported relation types. Complex concave geometry, functional faces, local interface geometry, and several orientation relations still require mesh/SDF or carefully defined local frames.
- A6 still lacks a complete Prompt-conditioned definition of the expected ground, tabletop, wall mount, or parent support surface for every asset.
- Formula weights and the initial `0.70` thresholds come from the PRO-12 proposal and have not yet been validated as final benchmark thresholds.

Executable code therefore does not imply that every metric has already been shown to be discriminative.

## Pre-change baseline results (2026-08-12)

The frozen annotation snapshot contains 616 records. All 616 corresponding local assets were downloaded and executed successfully. The following table was produced before the latest A1/A2/A3/A5/A6 corrections. It is retained as a comparison baseline, not as the final performance of the current code.

| Metric | Scored records | AUC | Precision | Recall | F1 | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| A1 | 95 | 0.730 | 0.209 | 0.900 | 0.340 | Ranking signal exists, but false positives are frequent |
| A2 | 97 | 0.539 | 0.159 | 0.700 | Close to random; count/type matching needs improvement |
| A3 | 97 | 0.590 | 0.294 | 0.625 | Weak signal; explicit interface Contracts are needed |
| A4 | 0 | — | — | — | — | No calibrated batch VLM signal in the baseline |
| A5 | 0 | — | — | — | — | No batch spatial-relation signal in the baseline |
| A6 | 281 | 0.586 | 0.348 | 1.000 | 0.517 | High recall but many false positives; not suitable as a hard verifier yet |

Detailed aggregate results are in `results/alignment.md`. Per-record evidence is in `results/a1_a6_reports.jsonl`.

A1–A3 used the 98 completed Contracts in Wanglin's `contracts-300/` snapshot. A6 was executed on all 616 assets, but only 282 records had the newer A6 human label and 281 could be aligned successfully. The baseline A6 run used a part-count proxy for detached volume; the current code adds solid-volume measurement but has not yet been rerun on all 616 records.

## Post-change pilot

The tilting-fan example demonstrates the new end-to-end path:

```text
Prompt
  -> A3/A4/A5 Contract extraction
  -> eight-view rendering
  -> raw Codex/VLM A4 measurement
  -> geometry-based A5 measurement
  -> A1–A6 report
```

Files:

- `data/contracts-a3-a5/rec_tilting_fan_...json`
- `results/a4-renders/rec_tilting_fan_.../view_00.png` through `view_07.png`
- `results/a4-signals/rec_tilting_fan_...json`
- `results/post_change_pilot_tilting_fan.json`

The pilot produced raw A4 signals of `p_real = 0.73` and `C_view = 0.91`. Because the VLM has not been calibrated on held-out human labels, the A4 result is correctly reported as `partial/abstain`.

## Running tests

```bash
cd yiyun
python -m pytest -q
```

Current status: 25 tests pass.

## Running the real-asset batch

```bash
python -m verifier.run_batch \
  --data-dir /path/to/articraft-data \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --contracts data/contracts-300 \
  --extensions data/contracts-a3-a5 \
  --a4-signals results/a4-signals \
  --output results/a1_a6_reports.jsonl

python -m verifier.evaluate_reports \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --reports results/a1_a6_reports.jsonl \
  --json results/alignment.json \
  --markdown results/alignment.md
```

Use `--no-a6` for a faster static A1–A3 run. A complete A6 run executes generated Python/CAD code and should only be used on trusted local ArtiCraft assets.

## Extracting A3/A4/A5 Contracts

The default provider is the locally authenticated Codex CLI. Structured output is constrained by a JSON Schema:

```bash
python -m verifier.contracts.extract_a4_a5 \
  --data-dir /path/to/articraft-data \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --output-dir data/contracts-a3-a5
```

The Gemini-compatible path can also be selected explicitly:

```bash
python -m verifier.contracts.extract_a4_a5 \
  --provider gemini \
  --model gemini-3.6-flash \
  --env-file /path/to/.env \
  --data-dir /path/to/articraft-data \
  --annotations data/annotations/annotations-2026-08-12.csv \
  --output-dir data/contracts-a3-a5
```

Gemini credentials are read only from `GEMINI_API_KEY` or an explicitly supplied environment file. They are not written to URLs, outputs, or the repository.

Only Prompt-explicit requirements with verbatim evidence may become scored requirements. Category-level common-sense inferences are stored under `advisory_inferences` and cannot reduce a score.

## Measuring A4 on one record

```bash
python -m verifier.measure_a4 \
  --data-dir /path/to/articraft-data \
  --extensions data/contracts-a3-a5 \
  --output-dir results/a4-signals \
  --render-dir results/a4-renders \
  --record-id rec_tilting_fan_540930b6847a441892643dedf9b71761
```

This creates eight rendered views and raw VLM signals. It does not mark the VLM as calibrated.

## Interpretation rules

- A1–A5 require a reviewed Prompt Contract. If the Prompt does not explicitly specify a requirement, the corresponding item is `N/A`, not an inferred hard constraint.
- A4 can only claim full coverage after the VLM and threshold have been calibrated and evaluated on held-out human labels.
- Partial A5 relations are renormalized over genuinely measurable components; missing components are not silently assigned a perfect score.
- A6 overlap measurements must exclude Contract-justified intentional intersections. Otherwise, valid contact or nesting may be mislabeled as failure.
- Tool failure, unsupported measurement, and missing Contract evidence must remain distinct from an asset defect.
