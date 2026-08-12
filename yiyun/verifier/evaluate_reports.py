"""Compare A1-A6 JSONL output with the frozen human annotations."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .evaluation.metrics import evaluate_item


COLUMNS = {
    "A1": "零件拆分与活动属性是否合理",
    "A2": "零件数量和种类是否符合描述",
    "A3": "必要结构是否完整",
    "A4": "几何形状、尺寸和比例是否合理",
    "A5": "零件位置、朝向与装配关系是否合理",
    "A6": "初始状态是否不存在非预期穿插、悬浮或脱离",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotations", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    args = parser.parse_args()

    with args.annotations.open(encoding="utf-8-sig", newline="") as handle:
        labels = {row["Record ID"].strip(): row for row in csv.DictReader(handle)}
    reports: dict[str, dict[str, Any]] = {}
    for line in args.reports.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("status") == "ok":
            reports[row["record_id"]] = row

    all_results: dict[str, dict[str, Any]] = {}
    comparisons: dict[str, list[dict[str, Any]]] = {item: [] for item in COLUMNS}
    for record_id, report_row in reports.items():
        human = labels.get(record_id, {})
        metrics = report_row.get("report", {}).get("human_metrics", {})
        for item, column in COLUMNS.items():
            result = metrics.get(item, {})
            comparisons[item].append(
                {
                    "record_id": record_id,
                    "human": human.get(column, ""),
                    "score": result.get("score"),
                    "prediction": result.get("prediction"),
                    "coverage": result.get("coverage"),
                }
            )
    for item in COLUMNS:
        all_results[item] = evaluate_item(comparisons[item], item)

    payload = {
        "annotation_rows": len(labels),
        "report_rows": len(reports),
        "items": all_results,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown.write_text(_markdown(payload), encoding="utf-8")
    print(_markdown(payload))
    return 0


def _fmt(value: Any) -> str:
    return "—" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# A1–A6 real-asset alignment",
        "",
        f"Frozen annotations: {payload['annotation_rows']}; successfully scored local assets: {payload['report_rows']}.",
        "",
        "| Item | Human labeled | Scored | Coverage | Decided | AUC | Precision | Recall | F1 | Balanced acc. | Kappa |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item, result in payload["items"].items():
        lines.append(
            "| " + " | ".join(
                [
                    item,
                    str(result["human_labeled"]),
                    str(result["scored"]),
                    _fmt(result["coverage"]),
                    str(result["decided"]),
                    _fmt(result["auc"]),
                    _fmt(result["precision"]),
                    _fmt(result["recall"]),
                    _fmt(result["f1"]),
                    _fmt(result["balanced_accuracy"]),
                    _fmt(result["kappa"]),
                ]
            ) + " |"
        )
    lines.extend(
        [
            "",
            "AUC uses human FAIL as the positive class; 0.5 is random ranking. N/A/unsupported and abstentions are reported through coverage rather than converted to pass/fail.",
            "",
            "## Error IDs",
            "",
        ]
    )
    for item, result in payload["items"].items():
        lines.extend(
            [
                f"### {item}",
                "",
                "False positives: " + (", ".join(result["false_positive_ids"]) or "none"),
                "",
                "False negatives: " + (", ".join(result["false_negative_ids"]) or "none"),
                "",
            ]
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
