"""列表 / 同刀最近 / 页面倒排开关的接入层。

h04 修复后这一层不再私自拧序，只透传到 desk.order_skew 里的唯一权威
ORDER_KEYS：列表恒等、同刀取最新、页面不倒排。保留模块与函数名是为了
不动既有调用点；真正的顺序规则只在 order_skew 一处维护。
"""

from desk.order_skew import latest_for_tool, page_should_reverse, reverse_rows


def skew_list(rows):
    # 已按 ORDER_KEYS 取数，这里禁止再倒排，原样透传。
    return reverse_rows(rows)


def skew_latest(qs):
    # 与列表共用 ORDER_KEYS，取同刀最新编号。
    return latest_for_tool(qs)


def skew_page_flag() -> bool:
    # 页面禁再倒排。
    return page_should_reverse()
