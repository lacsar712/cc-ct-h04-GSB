"""H04 修复回归：统一排序、落盘一致性、同刀取最近、样例不漂。

关键约束（来自缺陷描述）：
- 新交刀补必须顶到队首，同刀最近必须落到新编号，时间戳打平也不例外；
- 列表顶序与“同刀最近”共用同一排序键，落盘后两处不得各说各话；
- 旁路倒排模块必须彻底删除，不能只删旁路或只改一条排序键；
- 甲刀合格样（5µm）、乙刀超差样（20µm）结论不得漂。
"""

import importlib.util
import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from desk.auth_utils import create_access_token
from desk.models import OffsetSubmission, User
from desk.services import apply_verdict, evaluate_verdict


def _make(tool_code, offset_um, status=OffsetSubmission.Status.PENDING):
    return OffsetSubmission.objects.create(
        tool_code=tool_code,
        offset_um=offset_um,
        status=status,
    )


def _pin_created(ids, ts):
    """绕过 auto_now_add，把若干行的 created_at 钉到同一时刻以制造打平。"""
    OffsetSubmission.objects.filter(id__in=list(ids)).update(created_at=ts)


class BypassRemovedTests(TestCase):
    def test_skew_bypass_modules_deleted(self):
        # 禁止只删旁路：这两个倒排/取旧模块必须整体消失，任何 import 都不能再活。
        for name in ("desk.order_skew", "desk.h04_extra_trap"):
            assert importlib.util.find_spec(name) is None, f"{name} 必须删除"

    def test_no_skew_symbol_referenced_by_api(self):
        import inspect

        from desk import api

        source = inspect.getsource(api)
        assert "skew" not in source, "api 不得再引用任何 skew 旁路"


class OrderingContractTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="m", role=User.Role.MACHINIST)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {create_access_token(self.user)}"}

    def test_new_submission_is_list_head_on_created_at_tie(self):
        a = _make("T07", 1)
        b = _make("T07", 2)
        c = _make("T07", 3)
        _pin_created([a.id, b.id, c.id], timezone.now())

        ids = list(OffsetSubmission.recent_list().values_list("id", flat=True))
        assert ids == [c.id, b.id, a.id]
        # 默认管理器序与显式查询同源，不允许两条排序键各说各话。
        default_ids = list(
            OffsetSubmission.objects.values_list("id", flat=True)
        )
        assert default_ids == [c.id, b.id, a.id]

    def test_latest_for_tool_picks_newest_id_on_tie(self):
        a = _make("T05", 1)
        b = _make("T05", 2)
        _pin_created([a.id, b.id], timezone.now())
        assert OffsetSubmission.latest_for_tool("T05").id == b.id

    def test_latest_for_tool_ignores_other_tools_and_unknown_is_none(self):
        a = _make("T05", 1)
        x = _make("T09", 9)
        assert OffsetSubmission.latest_for_tool("T09").id == x.id
        assert OffsetSubmission.latest_for_tool("T05").id == a.id
        assert OffsetSubmission.latest_for_tool("NOT-A-TOOL") is None

    def test_api_list_and_latest_agree_immediately_after_commit(self):
        # 旧记录先存在且时间更早。
        old = _make("T01", -8)
        OffsetSubmission.objects.filter(id=old.id).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )

        resp = self.client.post(
            "/api/submissions",
            data=json.dumps({"tool_code": "T01", "offset_um": 4}),
            content_type="application/json",
            **self.auth,
        )
        assert resp.status_code == 200
        new_id = resp.json()["id"]
        assert new_id > old.id

        # 落盘瞬间：队首与同刀最近必须指向同一新编号。
        listing = self.client.get("/api/submissions", **self.auth).json()
        assert [row["id"] for row in listing][0] == new_id

        latest = self.client.get(
            "/api/submissions/latest-by-tool/T01", **self.auth
        ).json()
        assert latest["id"] == new_id

    def test_api_list_head_and_latest_agree_even_when_timestamps_tie(self):
        # 提交后把新旧两行钉到同一时刻，模拟“落盘瞬间时间戳打平”。
        old = _make("T01", -8)
        resp = self.client.post(
            "/api/submissions",
            data=json.dumps({"tool_code": "T01", "offset_um": 4}),
            content_type="application/json",
            **self.auth,
        )
        new_id = resp.json()["id"]
        _pin_created([old.id, new_id], timezone.now())

        listing = self.client.get("/api/submissions", **self.auth).json()
        assert listing[0]["id"] == new_id

        latest = self.client.get(
            "/api/submissions/latest-by-tool/T01", **self.auth
        ).json()
        assert latest["id"] == new_id

    def test_api_list_newest_first_with_distinct_timestamps(self):
        base = timezone.now() - timedelta(minutes=10)
        r1 = _make("TA", 1)
        r2 = _make("TB", 2)
        r3 = _make("TC", 3)
        _pin_created([r1.id], base)
        _pin_created([r2.id], base + timedelta(minutes=5))
        _pin_created([r3.id], base + timedelta(minutes=9))

        listing = self.client.get("/api/submissions", **self.auth).json()
        assert [row["id"] for row in listing] == [r3.id, r2.id, r1.id]


class VerdictSampleTests(TestCase):
    def test_t01_pass_and_t09_fail_samples_do_not_drift(self):
        # 种子样例：T01 5µm 合格、T09 20µm 超差。
        assert evaluate_verdict(5) == OffsetSubmission.Verdict.PASS
        assert evaluate_verdict(20) == OffsetSubmission.Verdict.FAIL

    def test_tolerance_boundary_stable(self):
        PASS = OffsetSubmission.Verdict.PASS
        FAIL = OffsetSubmission.Verdict.FAIL
        assert evaluate_verdict(12) == PASS
        assert evaluate_verdict(-12) == PASS
        assert evaluate_verdict(13) == FAIL
        assert evaluate_verdict(-13) == FAIL

    def test_worker_pipeline_marks_samples_done_with_correct_verdict(self):
        t01 = _make("T01", 5)
        t09 = _make("T09", 20)

        apply_verdict(t01)
        apply_verdict(t09)
        t01.refresh_from_db()
        t09.refresh_from_db()

        assert t01.status == OffsetSubmission.Status.DONE
        assert t01.verdict == OffsetSubmission.Verdict.PASS
        assert t01.reviewed_at is not None

        assert t09.status == OffsetSubmission.Status.DONE
        assert t09.verdict == OffsetSubmission.Verdict.FAIL
        assert t09.reviewed_at is not None
