"""pytest 引导：让 desk 模型在测试可被导入。

优先使用正式的 Postgres 配置（docker / CI 里装了 psycopg，用例本身不连库）；
若本机没有 psycopg，则退回内存 sqlite 设置。两者都只做 django.setup()，
不迁移、不写任何真实数据库。
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    import psycopg  # noqa: F401
except Exception:  # pragma: no cover - 仅本机无 psycopg 时走这里
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.sqlite_settings"

import django  # noqa: E402

django.setup()
