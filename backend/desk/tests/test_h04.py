"""h04 回归：列表顶序、同刀最近、落盘口径、合格/超差判定。

这些用例不连数据库，纯校验顺序权威模块与判定函数，保证在 docker
（Postgres 后端模块）与本机（conftest 回退 sqlite）下都能直接跑。
"""

from desk.h04_extra_trap import skew_list, skew_page_flag
from desk.models import OffsetSubmission
from desk.order_skew import (
    ORDER_KEYS,
    commit_and_latest_split,
    latest_for_tool,
    page_should_reverse,
    reverse_rows,
)
from desk.services import evaluate_verdict


# ---------- 列表：新交顶队首，页面禁再倒排 ----------

def test_list_passthrough_does_not_reverse():
    # 入参已是按 ORDER_KEYS 取好的队首序，旁路必须原样透传，不得再翻。
    assert reverse_rows([1, 2, 3]) == [1, 2, 3]
    assert skew_list(["新", "中", "旧"]) == ["新", "中", "旧"]


def test_page_must_not_reverse():
    assert skew_page_flag() is False
    assert page_should_reverse() is False


# ---------- 同刀最近：必落到最新编号，不摸旧号 ----------

class _RecordingQS:
    """记录 order_by 收到的键，并模拟 .first() 返回标记对象。"""

    def __init__(self, sentinel):
        self._sentinel = sentinel
        self.order_keys = None

    def order_by(self, *keys):
        self.order_keys = keys
        return self

    def first(self):
        return self._sentinel


def test_latest_uses_same_order_keys_as_list():
    sentinel = object()
    qs = _RecordingQS(sentinel)
    assert latest_for_tool(qs) is sentinel
    # 必须与列表共用同一套键（倒序取最新），而非自写的正序键。
    assert qs.order_keys == ORDER_KEYS
    assert qs.order_keys == ("-created_at", "-id")


def test_order_keys_single_source():
    assert ORDER_KEYS == ("-created_at", "-id")
    # 模型默认序与顺序权威同源，落盘瞬间两处不会各说各话。
    assert list(OffsetSubmission._meta.ordering) == list(ORDER_KEYS)


def test_commit_and_latest_no_longer_split():
    # 修复前为 True（列表与最近各执一套序，像处在半提交状态）；修复后必须 False。
    assert commit_and_latest_split() is False


# ---------- 合格 / 超差判定：甲刀合格、乙刀超差，边界不漂 ----------

def test_verdict_boundary_does_not_drift():
    P = OffsetSubmission.Verdict.PASS
    F = OffsetSubmission.Verdict.FAIL
    # 容差 12µm：含 ±12 合格，±13 起超差；正负对称、0 合格。
    for value in (0, 1, 5, 12, -1, -5, -12):
        assert evaluate_verdict(value) == P, value
    for value in (13, 20, 100, -13, -20, -100):
        assert evaluate_verdict(value) == F, value
    # 结论文案本身不能漂。
    assert P == "合格"
    assert F == "超差"
