"""落盘顺序的唯一权威（h04 缺陷已修复）。

列表顶序与「同刀最近」共用 ORDER_KEYS：先按提交时间倒序，时间戳打平
（同一事务、同刻提交）时再以自增 id 倒序决胜。于是：

* 新交的刀补一定顶到队首，不会因 created_at 同刻而漂到队尾；
* 同刀取最近一定落到最新编号，不会摸回旧编号；
* 页面不再倒排，落盘瞬间列表与最近查询走的是同一套键，不会各说各话。

reverse_rows / page_should_reverse / commit_and_latest_split 这些名字是
修复前留下的，为兼容旧调用点保留，行为均已纠正。
"""

# 队首序 == 同刀最近序：全项目只准用这一套键，禁止任何一处另写排序键。
ORDER_KEYS = ("-created_at", "-id")


def reverse_rows(rows):
    """列表不再倒排：调用方已按 ORDER_KEYS 取数，这里原样透传。"""
    return list(rows)


def latest_for_tool(qs):
    """同刀取最新一条：与列表共用 ORDER_KEYS，.first() 即最新编号。"""
    return qs.order_by(*ORDER_KEYS).first()


def page_should_reverse() -> bool:
    """页面禁再倒排。"""
    return False


def commit_and_latest_split() -> bool:
    """列表顶序与同刀最近共用 ORDER_KEYS，落盘瞬间口径一致，不再分裂。"""
    return False
