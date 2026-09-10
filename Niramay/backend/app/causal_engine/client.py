import httpx
import json
import structlog
from app.core.config import settings
from app.shared.healing_vocabulary import (
    HEALING_ACTIONS,
    coerce_action,
)
from typing import Dict, Any, Optional

logger = structlog.get_logger(__name__)

class CausalEngine:
    """
    AI-Powered Causal Engine.
    Uses a local Ollama instance (LLaMA3) to perform Root Cause Analysis (RCA) 
    on detected anomalies.
    """
    
    def __init__(self):
        self.url = settings.OLLAMA_URL
        self.model = settings.OLLAMA_MODEL
        self.enabled = settings.ENABLE_AI_CAUSAL

    async def analyze(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Performs RCA on an anomaly log.
        Falls back to rule-based analysis if LLM is disabled or fails.
        """
        if not self.enabled:
            return self._rule_based_fallback(log)

        try:
            prompt = self._build_prompt(log)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.url,
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "stream": False,
                        "format": "json"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    ai_response = json.loads(result.get("response", "{}"))
                    raw_action = ai_response.get("suggested_action", "none")
                    validated_action = coerce_action(raw_action)
                    if validated_action != raw_action:
                        logger.warning(
                            "LLM returned action outside vocabulary, coerced",
                            returned=raw_action,
                            coerced_to=validated_action,
                        )
                    return {
                        "root_cause": ai_response.get(
                            "root_cause", "Unknown (AI Parsing Error)"
                        ),
                        "confidence": ai_response.get("confidence", 0.5),
                        "suggested_action": validated_action,
                        "analysis_type": "ai_llm",
                    }
                else:
                    logger.warning("Ollama API returned error", status=response.status_code)
                    return self._rule_based_fallback(log)

        except Exception as e:
            logger.error("Causal Engine AI analysis failed", error=str(e))
            return self._rule_based_fallback(log)

    def _build_prompt(self, log: Dict[str, Any]) -> str:
        """Constructs the prompt for the LLM with enriched Stage 2 context"""
        vocab_block = "\n".join(
            f"       - {k}: {v}"
            for k, v in HEALING_ACTIONS.items()
        )
        return f"""
        You are an expert SRE and system architect. Analyze the following anomaly detected in a backend service and provide a root cause analysis in JSON format.

        LOG DATA:
        - Service: {log.get('service')}
        - Endpoint: {log.get('endpoint')}
        - Status Code: {log.get('status_code')}
        - Response Time: {log.get('response_time_ms', log.get('response_time'))}ms
        - Failure Tag: {log.get('failure_tag', 'none')}
        - Anomaly Reasons: {log.get('anomaly_reasons')}
        - Engines Triggered: {log.get('engines_triggered', [])}
        - Anomaly Score: {log.get('anomaly_score', 'N/A')}
        - Severity: {log.get('severity', 'N/A')}
        - Metadata: {log.get('metadata')}

        INSTRUCTIONS:
        1. Identify the most likely root cause considering all triggered detection engines.
        2. Assign a confidence score between 0.0 and 1.0.
        3. Suggest a technical healing action. You MUST pick exactly
           ONE value from this allowed vocabulary:
{vocab_block}
           Do not invent new action names. Do not return phrases or
           sentences. Return only the single action key.
        4. Return ONLY a valid JSON object with the keys: "root_cause", "confidence", "suggested_action".

        Example Output:
        {{
            "root_cause": "Database connection pool exhaustion due to high concurrent traffic.",
            "confidence": 0.95,
            "suggested_action": "restart_service"
        }}
        """

    def _rule_based_fallback(self, log: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps CRAVE failure signals to healing actions.

        Priority order:
        1. failure_tag — most precise, comes directly
           from CRAVE's exception handler or injector
        2. Multi-engine — 3+ engines firing together
           indicates cascading/system-wide failure
        3. Single anomaly reason — least precise,
           used when failure_tag is absent

        All returned suggested_action values are
        validated against VALID_ACTIONS vocabulary.
        """
        failure_tag = log.get("failure_tag", "none")
        reasons = log.get("anomaly_reasons", [])
        engines = log.get("engines_triggered", [])

        # ── Priority 1: failure_tag mapping ──────────
        # These tags come from CRAVE's exception handler
        # and are the most reliable signal we have.
        # Niramay should trust them completely.

        TAG_MAP = {
            "database_error": (
                "restart_service",
                "Database connection failure or query error. "
                "Service restart will re-establish pool.",
                0.88,
            ),
            "service_unavailable": (
                "scale_up",
                "Service overloaded — current replica count "
                "insufficient for traffic volume.",
                0.85,
            ),
            "config_error": (
                "rollback_deployment",
                "Bad configuration deployed. "
                "Previous version was stable.",
                0.90,
            ),
            "rate_limiting": (
                "throttle_requests",
                "Request rate exceeding configured limits. "
                "Client-side rate reduction needed.",
                0.82,
            ),
            "payment_timeout": (
                "restart_service",
                "Payment gateway timeout. Downstream service "
                "unresponsive — restart clears connection state.",
                0.80,
            ),
            "dependency": (
                "circuit_breaker",
                "External dependency unavailable. "
                "Circuit breaker prevents cascade failure.",
                0.85,
            ),
            "auth_expiration": (
                "escalate_only",
                "Authentication credentials expired. "
                "Requires human intervention to rotate.",
                0.95,
            ),
        }

        if failure_tag and failure_tag != "none":
            if failure_tag in TAG_MAP:
                action, cause, confidence = TAG_MAP[failure_tag]
                return {
                    "root_cause": cause,
                    "confidence": confidence,
                    "suggested_action": action,
                    "analysis_type": "rule_fallback",
                    "matched_by": "failure_tag",
                }

        # ── Priority 2: cascading failure detection ───
        # When 3 or more engines fire simultaneously the
        # failure is system-wide and a circuit breaker
        # prevents further cascade.

        cascading = (
            len(engines) >= 3
            or (
                "server_error" in reasons
                and "high_latency" in reasons
                and any(
                    r in reasons
                    for r in [
                        "rate_based_error_spike",
                        "baseline_deviation",
                        "service_silence",
                    ]
                )
            )
        )

        if cascading:
            return {
                "root_cause": (
                    "Cascading failure across multiple signals. "
                    "System under severe stress — circuit breaker "
                    "prevents further degradation."
                ),
                "confidence": 0.75,
                "suggested_action": "circuit_breaker",
                "analysis_type": "rule_fallback",
                "matched_by": "multi_engine",
            }

        # ── Priority 3: single reason mapping ─────────
        REASON_MAP = {
            "server_error": (
                "restart_service",
                "Internal server error in service logic or database.",
                0.70,
            ),
            "high_latency": (
                "scale_up",
                "Service response time degraded under load. "
                "Additional capacity needed.",
                0.65,
            ),
            "rate_limit": (
                "throttle_requests",
                "API rate limit exceeded by client or "
                "internal service call.",
                0.75,
            ),
            "rate_based_error_spike": (
                "scale_up",
                "Sustained error rate spike — service under "
                "load it cannot handle at current replica count.",
                0.68,
            ),
            "service_silence": (
                "escalate_only",
                "Service not responding for extended period. "
                "May need manual inspection before restart.",
                0.60,
            ),
            "baseline_deviation": (
                "scale_up",
                "Response time significantly above baseline. "
                "Load increasing beyond current capacity.",
                0.55,
            ),
        }

        for reason in reasons:
            if reason in REASON_MAP:
                action, cause, confidence = REASON_MAP[reason]
                return {
                    "root_cause": cause,
                    "confidence": confidence,
                    "suggested_action": action,
                    "analysis_type": "rule_fallback",
                    "matched_by": "anomaly_reason",
                }

        # ── Default: unknown pattern ───────────────────
        return {
            "root_cause": (
                "Unknown anomaly pattern. "
                "Insufficient signals for automatic classification."
            ),
            "confidence": 0.30,
            "suggested_action": "escalate_only",
            "analysis_type": "rule_fallback",
            "matched_by": "default",
        }

# Singleton instance
causal_engine = CausalEngine()


async def analyze_anomaly(log: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience wrapper for the detection worker.

    The detection worker imports this function:
        from app.causal_engine.client import analyze_anomaly
    """
    return await causal_engine.analyze(log)
