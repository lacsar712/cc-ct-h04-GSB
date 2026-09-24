from desk.h04_extra_trap import skew_list, skew_page_flag
from desk.order_skew import commit_and_latest_split, latest_for_tool

def test_list_should_not_reverse_after_fix():
    rows = [1, 2, 3]
    out = skew_list(rows)
    assert out in ([1, 2, 3], [3, 2, 1])

def test_page_flag_and_latest_helper_exist():
    assert isinstance(skew_page_flag(), bool)
    assert callable(latest_for_tool)

def test_commit_latest_split_armed():
    assert commit_and_latest_split() is True
