"""
Tests for unified failure_tag -> healing action mapping.
Covers every CRAVE failure scenario and edge case.
Must pass with K3S_ENABLED=false (no cluster needed).
"""
from app.causal_engine.client import causal_engine
from app.shared.healing_vocabulary import VALID_ACTIONS


class TestFailureTagMapping:
    def test_database_error(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "database_error",
            "anomaly_reasons": ["server_error"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "restart_service"
        assert r["matched_by"] == "failure_tag"
        assert r["confidence"] >= 0.80

    def test_service_unavailable(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "service_unavailable",
            "anomaly_reasons": ["server_error"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "scale_up"
        assert r["matched_by"] == "failure_tag"

    def test_config_error(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "config_error",
            "anomaly_reasons": ["server_error"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "rollback_deployment"
        assert r["matched_by"] == "failure_tag"

    def test_rate_limiting(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "rate_limiting",
            "anomaly_reasons": ["rate_limit"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "throttle_requests"
        assert r["matched_by"] == "failure_tag"

    def test_payment_timeout(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "payment_timeout",
            "anomaly_reasons": ["high_latency"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "restart_service"
        assert r["matched_by"] == "failure_tag"

    def test_dependency(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "dependency",
            "anomaly_reasons": ["server_error"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "circuit_breaker"
        assert r["matched_by"] == "failure_tag"

    def test_auth_expiration(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "auth_expiration",
            "anomaly_reasons": [],
            "engines_triggered": [],
        })
        assert r["suggested_action"] == "escalate_only"
        assert r["matched_by"] == "failure_tag"


class TestMultiEngineMapping:
    def test_cascading_three_engines(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": [
                "server_error", "high_latency",
                "rate_based_error_spike"
            ],
            "engines_triggered": [
                "feature_rule_engine",
                "rate_based_engine",
                "silence_detection_engine",
            ],
        })
        assert r["suggested_action"] == "circuit_breaker"
        assert r["matched_by"] == "multi_engine"

    def test_two_engines_not_cascading(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": ["server_error", "high_latency"],
            "engines_triggered": [
                "feature_rule_engine",
                "rate_based_engine",
            ],
        })
        # Two engines = not cascading, falls to reason map
        assert r["matched_by"] == "anomaly_reason"


class TestReasonMapping:
    def test_high_latency_no_tag(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": ["high_latency"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "scale_up"
        assert r["matched_by"] == "anomaly_reason"

    def test_server_error_no_tag(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": ["server_error"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "restart_service"
        assert r["matched_by"] == "anomaly_reason"

    def test_rate_limit_no_tag(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": ["rate_limit"],
            "engines_triggered": ["feature_rule_engine"],
        })
        assert r["suggested_action"] == "throttle_requests"

    def test_unknown_defaults_to_escalate(self):
        r = causal_engine._rule_based_fallback({
            "failure_tag": "none",
            "anomaly_reasons": [],
            "engines_triggered": [],
        })
        assert r["suggested_action"] == "escalate_only"
        assert r["matched_by"] == "default"


class TestVocabularyCompliance:
    def test_all_outputs_in_vocabulary(self):
        test_inputs = [
            {"failure_tag": "database_error",
             "anomaly_reasons": ["server_error"],
             "engines_triggered": []},
            {"failure_tag": "service_unavailable",
             "anomaly_reasons": ["server_error"],
             "engines_triggered": []},
            {"failure_tag": "config_error",
             "anomaly_reasons": ["server_error"],
             "engines_triggered": []},
            {"failure_tag": "rate_limiting",
             "anomaly_reasons": ["rate_limit"],
             "engines_triggered": []},
            {"failure_tag": "payment_timeout",
             "anomaly_reasons": ["high_latency"],
             "engines_triggered": []},
            {"failure_tag": "dependency",
             "anomaly_reasons": ["server_error"],
             "engines_triggered": []},
            {"failure_tag": "auth_expiration",
             "anomaly_reasons": [],
             "engines_triggered": []},
            {"failure_tag": "none",
             "anomaly_reasons": ["high_latency"],
             "engines_triggered": []},
            {"failure_tag": "none",
             "anomaly_reasons": [],
             "engines_triggered": []},
        ]
        for inp in test_inputs:
            r = causal_engine._rule_based_fallback(inp)
            assert r["suggested_action"] in VALID_ACTIONS, (
                f"'{r['suggested_action']}' not in vocabulary "
                f"for input {inp['failure_tag']}"
            )
