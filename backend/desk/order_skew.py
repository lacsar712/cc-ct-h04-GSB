"""Order traps: reverse default list + pick oldest as latest-by-tool."""

def reverse_rows(rows):
    return list(reversed(list(rows)))

def latest_for_tool(qs):
    # wrongly take oldest
    return qs.order_by("created_at", "id").first()

def page_should_reverse() -> bool:
    return True

def commit_and_latest_split() -> bool:
    """BUG: list top and latest-by-tool diverge as if mid-commit."""
    return True
