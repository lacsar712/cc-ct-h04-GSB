from django.db import migrations


class Migration(migrations.Migration):
    # 统一落盘口径：列表顶序与同刀最近都按 -created_at,-id。
    # 仅为 Meta.ordering 状态同步，不产生表结构 SQL。
    dependencies = [
        ("desk", "0001_initial"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="offsetsubmission",
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
