"""Tests that healing/index.py is fully aligned with
healing_vocabulary.py."""
from app.shared.healing_vocabulary import VALID_ACTIONS


def test_healing_index_imports_vocabulary():
    """healing/index.py must import from vocabulary."""
    import inspect
    from app.healing import index
    source = inspect.getsource(index)
    assert "healing_vocabulary" in source or \
           "VALID_ACTIONS" in source or \
           "coerce_action" in source


def test_no_retired_action_strings_in_healing_index():
    """retry_request and fallback_response must not
    appear as returned action strings."""
    import inspect
    from app.healing import index
    source = inspect.getsource(index)
    # These should not appear as string literals being
    # returned (comments are acceptable)
    lines_with_retired = [
        line for line in source.split("\n")
        if ("retry_request" in line or
            "fallback_response" in line)
        and not line.strip().startswith("#")
        and ("return" in line or
             "action" in line.lower())
    ]
    assert len(lines_with_retired) == 0, (
        f"Retired action strings found in active code:\n"
        + "\n".join(lines_with_retired)
    )


def test_decide_healing_action_returns_valid_vocabulary():
    """decide_healing_action must always return a
    vocabulary item."""
    from app.healing.index import healing_service
    from app.shared.healing_vocabulary import VALID_ACTIONS

    test_cases = [
        {"anomaly_reasons": ["server_error"],
         "severity": "high",
         "failure_tag": "database_error"},
        {"anomaly_reasons": ["high_latency"],
         "severity": "medium",
         "failure_tag": "none"},
        {"anomaly_reasons": ["rate_limit"],
         "severity": "medium",
         "failure_tag": "none"},
        {"anomaly_reasons": ["unknown_xyz"],
         "severity": "low",
         "failure_tag": "none"},
    ]

    for case in test_cases:
        action = healing_service.decide_healing_action(case)
        assert action in VALID_ACTIONS, (
            f"decide_healing_action returned '{action}' "
            f"for input {case}, which is not in vocabulary"
        )
