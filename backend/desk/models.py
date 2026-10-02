from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.query import QuerySet


class User(AbstractUser):
    class Role(models.TextChoices):
        MACHINIST = "machinist", "操作员"
        AUDITOR = "auditor", "复核员"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MACHINIST,
    )

    @property
    def can_write(self) -> bool:
        return self.role == self.Role.MACHINIST


class OffsetSubmission(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "待复核"
        PROCESSING = "processing", "复核中"
        DONE = "done", "已完成"

    class Verdict(models.TextChoices):
        PASS = "合格", "合格"
        FAIL = "超差", "超差"

    # 全应用唯一的“最新优先”排序键。
    # 必须带 -id 作为决胜键：同秒提交时 created_at 打平，
    # 仅靠 -created_at 无法保证新交顶到队首、同刀最近落到新编号。
    RECENT_ORDER = ("-created_at", "-id")

    tool_code = models.CharField(max_length=32, db_index=True)
    offset_um = models.IntegerField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    verdict = models.CharField(
        max_length=8,
        choices=Verdict.choices,
        blank=True,
        default="",
    )
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # 与 RECENT_ORDER 同源，默认查询即“新交在队首”，任何路径都不再倒排。
        ordering = ["-created_at", "-id"]
        indexes = [
            # 与唯一排序键对齐，同刀最近查询也走 tool_code 前缀。
            models.Index(
                fields=["tool_code", "-created_at", "-id"],
                name="offs_tool_recent_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.tool_code} {self.offset_um}µm"

    @classmethod
    def recent_list(cls, limit: int = 200) -> QuerySet["OffsetSubmission"]:
        """复核总览列表：最新提交在队首。"""
        return cls.objects.order_by(*cls.RECENT_ORDER)[:limit]

    @classmethod
    def latest_for_tool(cls, tool_code: str) -> "OffsetSubmission | None":
        """同刀取最近：时间戳打平时由 -id 决胜，必落到最新编号，绝不摸旧号。"""
        return (
            cls.objects.filter(tool_code=tool_code)
            .order_by(*cls.RECENT_ORDER)
            .first()
        )
