from .settings import *  # noqa: F401,F403

# 测试用内存 sqlite，不依赖外部 PostgreSQL；排序键含 -id，两种库行为一致。
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# 登录鉴权走 JWT，这里仅为加速账号创建，不影响被测接口。
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
