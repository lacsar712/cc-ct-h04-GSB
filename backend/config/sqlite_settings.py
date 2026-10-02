"""测试专用设置：仅在本机没有 PostgreSQL / psycopg 时由 conftest 选用。

复用全部正式配置，只把数据库换成内存 sqlite。测试用例本身不连库，
这里存在的意义是让 Django 在加载模型（引入 DB 后端模块）时有一个
无需外部依赖的后端，绝不影响 config.settings 里的正式 Postgres 配置。
"""

from config.settings import *  # noqa: F401,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
