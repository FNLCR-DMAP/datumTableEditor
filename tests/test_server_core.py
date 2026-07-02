import pandas as pd


def test_reset_lazy_cache_clears_page_and_count_cache():
    from src.server.core import _reset_lazy_cache

    page_buffer = {
        "key": ("old",),
        "df": pd.DataFrame({"id": [1]}),
        "filtered_count": 1,
        "total_count": 10,
    }
    count_cache = {"key": ("old",), "value": 1}

    _reset_lazy_cache(page_buffer, count_cache)

    assert page_buffer["key"] is None
    assert page_buffer["df"].empty
    assert page_buffer["filtered_count"] == 0
    assert page_buffer["total_count"] == 0
    assert count_cache == {"key": None, "value": 0}
