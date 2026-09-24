from desk.order_skew import latest_for_tool, page_should_reverse, reverse_rows

def skew_list(rows):
    return reverse_rows(rows)

def skew_latest(qs):
    return latest_for_tool(qs)

def skew_page_flag() -> bool:
    return page_should_reverse()

