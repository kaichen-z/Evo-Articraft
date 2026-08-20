"""从 train.csv 里选 20 个类型多样的典型案例。

覆盖面设计（每类 1 个，共 20 类关键词）：
  棱柱类容器 / 多级滑轨 / 工具 / 抽屉设备
  旋转门 / 柜门 / 翻盖 / 小型翻盖 / 双铰链 / 贴合式家电
  连续转子（风扇/风机/转盘/水轮）
  混合家电（洗碗机、打印机）
  多关节链（腕、指骨链）
  家具与支架（办公椅、显示器支架）
"""

import csv
import json
import pathlib

TRAIN = pathlib.Path(r"D:\projects\articraft-verifier\splits\train.csv")
OUT = pathlib.Path(__file__).parent / "cases_20.json"

# 关键词按优先级匹配 record_id（小写），每个关键词取第一个命中且未被占用的案例
KEYWORDS = [
    ("drawer_cabinet",        "棱柱-多抽屉柜"),
    ("telescoping",           "棱柱-多级滑轨"),
    ("bench_vise",            "棱柱-台钳"),
    ("cash_register",         "棱柱-收银机抽屉"),
    ("garden_gate",           "旋转-园门"),
    ("electrical_cabinet",    "旋转-电柜门"),
    ("wheelie_bin",           "旋转-垃圾桶盖"),
    ("flip_phone",            "旋转-翻盖手机"),
    ("glasses",               "旋转-眼镜双铰链"),
    ("panini_press",          "旋转-贴合式家电"),
    ("tower_fan",             "转子-塔扇"),
    ("wind_turbine",          "转子-风力机"),
    ("lazy_susan",            "转子-转盘"),
    ("waterwheel",            "转子-水轮"),
    ("office_chair",          "混合-办公椅"),
    ("monitor_mount",         "混合-显示器支架"),
    ("yawpitchroll_wrist",    "链-三自由度腕"),
    ("phalanx_chain",         "链-指骨链"),
    ("dishwasher",            "混合-洗碗机"),
    ("printer",               "混合-打印机"),
]


def main():
    rows = list(csv.DictReader(TRAIN.open(encoding="utf-8-sig")))
    chosen = []
    used = set()

    for kw, label in KEYWORDS:
        hit = None
        for r in rows:
            rid = r["record_id"].lower()
            if kw in rid and r["record_id"] not in used:
                hit = r
                break
        if hit is None:
            print(f"[MISS] {kw} ({label})")
            continue
        used.add(hit["record_id"])
        chosen.append({
            "record_id": hit["record_id"],
            "category": hit["category"],
            "label": label,
            "n_joints": int(hit["n_joints"]),
            "ngeom": int(hit["ngeom"]),
            "d_bbox": float(hit["d_bbox"]),
            "urdf_path": hit["urdf_path"],
            "model_py_path": hit["model_py_path"],
        })

    print(f"\n选出 {len(chosen)} 个案例:")
    print(f"{'label':<14} | {'joints':>6} | {'geoms':>5} | {'D':>6} | category")
    print("-" * 100)
    for c in chosen:
        print(f"{c['label']:<14} | {c['n_joints']:>6} | {c['ngeom']:>5} | {c['d_bbox']:>6.3f} | {c['category'][:50]}")

    OUT.write_text(json.dumps(chosen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已保存到 {OUT}")


if __name__ == "__main__":
    main()
