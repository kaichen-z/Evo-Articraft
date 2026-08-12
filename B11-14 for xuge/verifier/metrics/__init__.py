"""B11-B14 打分函数。全部是纯函数:
    score(signals: dict, contract: dict, consts: Consts) -> MetricResult
不读文件、不启仿真器、不用全局状态。
"""
from . import b11, b12, b13, b14

REGISTRY = {"B11": b11.score, "B12": b12.score, "B13": b13.score, "B14": b14.score}
__all__ = ["b11", "b12", "b13", "b14", "REGISTRY"]
