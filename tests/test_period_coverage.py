from function_app.src.period_coverage import infer_period_coverage


def test_subject_period_hint_yyyymm_is_inclusive_month_range():
    coverage = infer_period_coverage(
        subject_period_hint="202605",
        link_text="",
        source_url="",
    )

    assert coverage.coverage_type == "single_month"
    assert coverage.subject_period_from == "20260501T000000"
    assert coverage.subject_period_to == "20260531T235959"
    assert coverage.inference_source == "subject_period_hint"


def test_rolling_12_detection_from_link_text():
    coverage = infer_period_coverage(
        subject_period_hint=None,
        link_text="Rolling 12 months up to May 2026",
        source_url="https://example.com/file.csv",
    )

    assert coverage.coverage_type == "rolling_12_month"
    assert coverage.subject_period_from == "20250601T000000"
    assert coverage.subject_period_to == "20260531T235959"


def test_not_inferred_returns_unknown_contract():
    coverage = infer_period_coverage(
        subject_period_hint=None,
        link_text="Summary data extract",
        source_url="https://example.com/data.csv",
    )

    assert coverage.coverage_type == "unknown"
    assert coverage.subject_period_from == ""
    assert coverage.subject_period_to == ""
    assert coverage.inference_method == "not_inferred"
