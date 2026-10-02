from datetime import datetime
from typing import Optional

from django.db import transaction
from django.http import HttpRequest
from ninja import NinjaAPI, Schema
from ninja.errors import HttpError

from desk.auth_utils import bearer_auth, create_access_token, verify_password
from desk.models import OffsetSubmission, User
from desk.order_skew import ORDER_KEYS

api = NinjaAPI(title="数控刀补复核台", version="1.0")


class HealthOut(Schema):
    status: str


class LoginIn(Schema):
    username: str
    password: str


class LoginOut(Schema):
    token: str
    username: str
    role: str
    can_write: bool


class SubmissionIn(Schema):
    tool_code: str
    offset_um: int


class SubmissionOut(Schema):
    id: int
    tool_code: str
    offset_um: int
    status: str
    verdict: str
    created_at: datetime
    reviewed_at: Optional[datetime]


def _to_out(row: OffsetSubmission) -> SubmissionOut:
    return SubmissionOut(
        id=row.id,
        tool_code=row.tool_code,
        offset_um=row.offset_um,
        status=row.status,
        verdict=row.verdict or "",
        created_at=row.created_at,
        reviewed_at=row.reviewed_at,
    )


@api.get("/health", response=HealthOut)
def health(request: HttpRequest):
    return {"status": "ok"}


@api.post("/auth/login", response=LoginOut)
def login(request: HttpRequest, body: LoginIn):
    try:
        user = User.objects.get(username=body.username)
    except User.DoesNotExist:
        raise HttpError(401, "用户名或密码错误")
    if not verify_password(body.password, user.password):
        raise HttpError(401, "用户名或密码错误")
    token = create_access_token(user)
    return {
        "token": token,
        "username": user.username,
        "role": user.role,
        "can_write": user.can_write,
    }


@api.get("/submissions", response=list[SubmissionOut], auth=bearer_auth)
def list_submissions(request: HttpRequest):
    # 显式按统一口径 ORDER_KEYS 取数（新交顶队首，同刻以 -id 决胜），
    # 不再经过任何倒排旁路。
    rows = OffsetSubmission.objects.order_by(*ORDER_KEYS)[:200]
    return [_to_out(r) for r in rows]


@api.get("/submissions/{submission_id}", response=SubmissionOut, auth=bearer_auth)
def get_submission(request: HttpRequest, submission_id: int):
    try:
        row = OffsetSubmission.objects.get(pk=submission_id)
    except OffsetSubmission.DoesNotExist:
        raise HttpError(404, "刀补记录不存在")
    return _to_out(row)


@api.get("/submissions/latest-by-tool/{tool_code}", response=SubmissionOut, auth=bearer_auth)
def latest_by_tool(request: HttpRequest, tool_code: str):
    # 与列表共用同一套 ORDER_KEYS：同刀取最近必落到最新编号，绝不摸旧号。
    row = (
        OffsetSubmission.objects.filter(tool_code=tool_code)
        .order_by(*ORDER_KEYS)
        .first()
    )
    if row is None:
        raise HttpError(404, "该刀暂无刀补记录")
    return _to_out(row)


@api.post("/submissions", response=SubmissionOut, auth=bearer_auth)
def create_submission(request: HttpRequest, body: SubmissionIn):
    user: User = request.auth
    if not user.can_write:
        raise HttpError(403, "当前账号只读，不能提交刀补")
    tool_code = body.tool_code.strip()
    if not tool_code:
        raise HttpError(400, "刀具编号不能为空")
    # 单事务落盘：create 在事务提交后才返回，紧接着的列表 / 同刀最近
    # 查询必然读到这条新编号，不会出现“已入队却仍摸旧号”的半提交状态。
    with transaction.atomic():
        row = OffsetSubmission.objects.create(
            tool_code=tool_code,
            offset_um=body.offset_um,
            submitted_by=user,
            status=OffsetSubmission.Status.PENDING,
        )
        row.refresh_from_db()
    return _to_out(row)
