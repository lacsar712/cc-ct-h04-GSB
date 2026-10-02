"""真建表的顺序集成测试（仅 sqlite，用于本机/conftest 回退环境）。

在内存库里插入 created_at 完全相同的记录，验证：
1. 列表按 -created_at,-id 顶序，同刻也以新编号在前（新交顶队首）；
2. 同刀最近取到最新编号，不摸旧号；
3. HTTP 接口 /submissions 与 /submissions/latest-by-tool 与之一致；
4. 甲刀（5µm）合格、乙刀（20µm）超差不漂。

docker/CI 的 Postgres 环境下整套纯函数回归（test_h04.py）照跑，本文件
只在 sqlite 启用，避免触碰外部数据库。
"""

import datetime as dt

import pytest
from django.core.management import call_command
from django.db import connection
from django.utils import timezone

from desk.models import OffsetSubmission
from desk.order_skew import ORDER_KEYS, latest_for_tool

pytestmark = pytest.mark.skipif(
    connection.vendor != "sqlite",
    reason="顺序集成测试只在内存 sqlite 下运行，避免触碰外部 Postgres",
)


@pytest.fixture(scope="module")
def _schema():
    call_command("migrate", verbosity=0, run_syncdb=True)
    yield
    call_command("flush", verbosity=0, interactive=False)


@pytest.fixture()
def _clean():
    yield
    OffsetSubmission.objects.all().delete()


def _bulk(tool, triples):
    rows = OffsetSubmission.objects.bulk_create(
        [
            OffsetSubmission(
                tool_code=tool,
                offset_um=offset,
                status=OffsetSubmission.Status.DONE,
                verdict=verdict,
            )
            for offset, verdict, _created in triples
        ]
    )
    # auto_now_add 会在插入时逐行盖 now()，无法精确制造同刻/异刻；
    # 插入后用 UPDATE 回写指定时间戳（.update 绕过 auto_now_add）。
    for row, (_offset, _verdict, created) in zip(rows, triples):
        OffsetSubmission.objects.filter(pk=row.pk).update(created_at=created)
        row.created_at = created
    return rows


def test_same_timestamp_new_id_sorts_to_top(_schema, _clean):
    stamp = timezone.now()
    rows = _bulk(
        "T01",
        [
            (5, "合格", stamp),
            (20, "超差", stamp),
            (7, "合格", stamp),  # 同刻、编号最大 -> 必须在队首
        ],
    )
    newest_id = max(r.id for r in rows)

    listed = list(
        OffsetSubmission.objects.order_by(*ORDER_KEYS).values_list("id", flat=True)
    )
    # 同刻时间戳下，顺序严格按 id 倒序：新交顶队首，不沉队尾。
    assert listed == sorted((r.id for r in rows), reverse=True)
    assert listed[0] == newest_id


def test_timestamp_primary_key_then_id(_schema, _clean):
    new_stamp = timezone.now()
    old_stamp = new_stamp - dt.timedelta(minutes=5)
    rows = _bulk(
        "T09",
        [
            (20, "超差", new_stamp),
            (5, "合格", old_stamp),  # 编号更大但时间更老 -> 必须排到后面
        ],
    )
    ordered = list(
        OffsetSubmission.objects.order_by(*ORDER_KEYS).values_list("id", flat=True)
    )
    assert ordered[0] == rows[0].id  # 时间更新者在首，即便它 id 更小
    assert ordered[-1] == rows[1].id


def test_latest_by_tool_lands_on_new_id_at_same_timestamp(_schema, _clean):
    stamp = timezone.now()
    rows = _bulk(
        "T01",
        [
            (5, "合格", stamp),
            (20, "超差", stamp),
            (7, "合格", stamp),  # 同刀同刻最新编号
        ],
    )
    latest = latest_for_tool(OffsetSubmission.objects.filter(tool_code="T01"))
    assert latest.id == max(r.id for r in rows)
    assert latest.offset_um == 7  # 落到新编号，而不是旧编号 5µm


def test_latest_picks_newer_when_timestamps_differ(_schema, _clean):
    new_stamp = timezone.now()
    old_stamp = new_stamp - dt.timedelta(seconds=30)
    _bulk("T07", [(5, "合格", old_stamp)])
    new_rows = _bulk("T07", [(9, "合格", new_stamp)])
    latest = latest_for_tool(OffsetSubmission.objects.filter(tool_code="T07"))
    assert latest.id == new_rows[0].id
    assert latest.offset_um == 9


def test_http_list_and_latest_agree_after_commit(_schema, _clean):
    from ninja.testing import TestClient

    from desk.api import api
    from desk.auth_utils import create_access_token
    from desk.models import User

    user, _ = User.objects.get_or_create(
        username="t_machinist", defaults={"role": User.Role.MACHINIST}
    )
    token = create_access_token(user)
    client = TestClient(api)
    headers = {"Authorization": f"Bearer {token}"}

    stamp = timezone.now()
    rows = _bulk(
        "T01",
        [
            (5, "合格", stamp),
            (20, "超差", stamp),
            (7, "合格", stamp),
        ],
    )
    newest_id = max(r.id for r in rows)

    resp = client.get("/submissions", headers=headers)
    assert resp.status_code == 200
    payload = resp.json()
    ids = [r["id"] for r in payload]
    assert ids == sorted(ids, reverse=True)
    assert payload[0]["id"] == newest_id

    resp2 = client.get("/submissions/latest-by-tool/T01", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == newest_id
    # 列表队首与同刀最近在落盘后指向同一条：新编号，不各说各话。
    assert payload[0]["id"] == resp2.json()["id"]


def test_post_then_list_top_and_latest_both_land_on_new_id(_schema, _clean):
    from ninja.testing import TestClient

    from desk.api import api
    from desk.auth_utils import create_access_token
    from desk.models import User

    machinist, _ = User.objects.get_or_create(
        username="t_machinist", defaults={"role": User.Role.MACHINIST}
    )
    auditor, _ = User.objects.get_or_create(
        username="t_auditor", defaults={"role": User.Role.AUDITOR}
    )
    client = TestClient(api)

    # 只读账号不得提交。
    aud = client.post(
        "/submissions",
        json={"tool_code": "T01", "offset_um": 3},
        headers={"Authorization": f"Bearer {create_access_token(auditor)}"},
    )
    assert aud.status_code == 403

    # 先放同刀旧记录，时间戳就用 now()：模拟新交与旧记录“同刻”。
    old = _bulk("T01", [(5, "合格", timezone.now())])

    auth = {"Authorization": f"Bearer {create_access_token(machinist)}"}
    created = client.post(
        "/submissions", json={"tool_code": "T01", "offset_um": 11}, headers=auth
    )
    assert created.status_code == 200
    new_id = created.json()["id"]
    assert new_id > max(r.id for r in old)

    # 提交事务一旦返回，列表队首与同刀最近都必须是这条新编号。
    listed = client.get("/submissions", headers=auth).json()
    latest = client.get("/submissions/latest-by-tool/T01", headers=auth).json()
    assert listed[0]["id"] == new_id
    assert latest["id"] == new_id


def test_verdict_samples_do_not_drift(_schema, _clean):
    from desk.services import apply_verdict

    a = OffsetSubmission.objects.create(tool_code="T-A", offset_um=5)
    b = OffsetSubmission.objects.create(tool_code="T-B", offset_um=20)
    apply_verdict(a)
    apply_verdict(b)
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.verdict == "合格" and a.status == OffsetSubmission.Status.DONE
    assert b.verdict == "超差" and b.status == OffsetSubmission.Status.DONE
