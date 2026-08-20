# p2-kai — P2 geometry verifier (GF1–GF4)

Task-13-4. Scores a CAD asset against its **contract** using deterministic 3D
measurements, then compares each injected variant with its own uuid's GT baseline
to name the defect.

    env_mujoco/bin/python code/p2-kai/run_eval.py            # -> results/results.json + scores.csv
    env_mujoco/bin/python code/p2-kai/report.py --out <path>.html

## Files

| file | role |
|---|---|
| `measure.py` | mesh primitives: components (sliver-filtered), cross-sections in world coordinates, enclosed cavities with diameter/roundness/depth, radial lobe count, wall thickness, ring radii, outline indentation depth, mirror symmetry |
| `geo.py` | `Geo` facade: one variant mesh in, geometric queries out |
| `bindings.py` | **frozen** contract→detector table (part id → detector, proportion claim → measurement recipe), one block per uuid |
| `gf.py` | GF1–GF4 scorers, frozen thresholds, and the two detection rules |
| `run_eval.py` | scores every entry in the testbed's `index.json` |
| `report.py` | renders `results.json` as the answer HTML |

## Rules of the harness

- The scorer reads **only** the variant `model.stl` and the uuid's `contract.yaml`.
  `injection.json` is opened after scoring, purely to attach the label for the report.
- `bindings.py` is written from the contract text, once per uuid, and shared by the
  GT and all variants — this is the P2 spec's "part masks already bound by the Gate".
- Deviation from `answer2/task-2_08-16-p2.html`: GF1/GF2 use geometry, not CLIP/SigLIP
  (no torch locally, and Task-13-4 asks for a geometry verifier). GF3/GF4 follow the spec.
- Detection compares against the same uuid's GT profile, per the plan's "GT scores too,
  it is the upper bound" rule. Two rules are reported: `argmin` (largest drop) and
  `gated` (connectivity failure outranks proportion drops).

## Env

`env_mujoco` + `shapely`, `scipy`, `networkx`, `rtree` (installed for this task).
