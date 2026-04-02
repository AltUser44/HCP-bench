from hcpbench.metrics import percentile_sorted, summarize_ns


def test_percentile_sorted():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile_sorted(xs, 50) == 3.0
    assert percentile_sorted(xs, 0) == 1.0
    assert percentile_sorted(xs, 100) == 5.0


def test_summarize_ns():
    s = summarize_ns([100.0, 200.0, 300.0])
    assert s["count"] == 3
    assert s["mean_ns"] == 200.0
    assert s["min_ns"] == 100.0
    assert s["max_ns"] == 300.0
