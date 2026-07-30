from ace.visual_intelligence.benchmark import run


def test_benchmark_gold_set_passes():
    report = run()
    assert report["case_count"] >= 10
    assert report["status"] == "passed"
    assert report["average_score"] >= 95
