import logging
import time
from typing import List
from openai import OpenAI
from src.models.cluster import ClusterResult
from src.config import LLMConfig
from src.pipeline.llm_json import log_parse_debug, parse_json_object

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are Sift's product research analyst.

Your job is to turn scraped user feedback into evidence-bound product research.
Use only the provided input. Do not invent causes, features, competitors, or facts.
Return exactly one JSON object. Do not use markdown, commentary, or code fences."""


ANALYZE_CLUSTER_PROMPT = """TASK
Analyze one complaint cluster for the product "{product}".

INPUT
Total feedback items in this cluster: {size}
Representative quotes:
{quotes}

SEVERITY RUBRIC
- high: frequent or emotionally intense pain that blocks adoption, trust, or core workflows
- medium: meaningful repeated friction that users can work around
- low: minor annoyance, preference, or isolated complaint

OUTPUT SCHEMA
{{
  "label": "2-5 word noun phrase naming the specific pain point",
  "summary": "2-3 sentences synthesizing the cluster, grounded only in the quotes",
  "severity": "high|medium|low"
}}

RULES
- The label must be specific, not generic phrases like "User Complaints" or "Product Issues".
- The severity value must be exactly one of: high, medium, low.
- Return only the JSON object."""


OVERALL_INSIGHTS_PROMPT = """TASK
Generate product-level insights for "{product}" from already-clustered feedback.

INPUT
Cluster summaries:
{cluster_summaries}

OUTPUT SCHEMA
{{
  "overall_insights": "3-4 sentence assessment of the biggest product weaknesses",
  "top_pain_points": ["pain point 1", "pain point 2", "pain point 3"]
}}

RULES
- Ground every claim in the provided cluster summaries.
- Prioritize by severity first, then complaint count, then strategic importance.
- Use no more than 3 top pain points. If fewer clusters are provided, return fewer.
- Return only the JSON object."""


REPAIR_JSON_PROMPT = """TASK
Convert this model response into one valid JSON object matching the schema.

SCHEMA
{schema}

MODEL RESPONSE
{raw}

RULES
- Preserve the intended meaning when possible.
- Return only the corrected JSON object."""


class Analyzer:
    def __init__(self, config: LLMConfig):
        self.client = None
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens
        self._unavailable_reason = ""
        self._warned_unavailable = False

        api_key = (config.api_key or "").strip()
        if not api_key:
            self._unavailable_reason = "LLM API key is not configured"
            return

        try:
            self.client = OpenAI(
                api_key=api_key,
                base_url=config.base_url,
            )
        except Exception as exc:
            self._unavailable_reason = f"LLM client setup failed: {exc}"

    def _call_llm(self, prompt: str, _retries: int = 2) -> str:
        if self.client is None:
            raise RuntimeError(self._unavailable_reason or "LLM client is unavailable")
        last_exc: Exception = RuntimeError("LLM returned empty response")
        for attempt in range(_retries + 1):
            if attempt:
                time.sleep(attempt)
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            content = (response.choices[0].message.content or "").strip()
            if content:
                return content
            logger.debug("LLM returned empty response on attempt %d/%d", attempt + 1, _retries + 1)
        raise last_exc

    def analyze_cluster(self, cluster: ClusterResult) -> ClusterResult:
        quotes = "\n".join(f"- \"{q}\"" for q in cluster.representative_quotes)
        product = cluster.items[0].product if cluster.items else "the product"
        prompt = ANALYZE_CLUSTER_PROMPT.format(
            product=product,
            quotes=quotes,
            size=cluster.size,
        )

        if self.client is None:
            self._warn_unavailable_once()
            return self._apply_cluster_fallback(cluster, self._unavailable_reason)

        try:
            raw = self._call_llm(prompt)
            result = self._parse_or_repair(raw, "cluster analysis", _CLUSTER_SCHEMA)
            cluster.label = _clean_string(result.get("label")) or "Unnamed cluster"
            cluster.summary = _clean_string(result.get("summary"))
            cluster.severity = _normalize_severity(result.get("severity"))
        except Exception as exc:
            logger.warning(
                "LLM analysis failed for cluster %d (%s: %s), using fallback labels.",
                cluster.cluster_id,
                type(exc).__name__,
                exc,
            )
            self._apply_cluster_fallback(cluster, "LLM call failed")

        return cluster

    def analyze_clusters(self, clusters: List[ClusterResult]) -> List[ClusterResult]:
        for cluster in clusters:
            self.analyze_cluster(cluster)
        return clusters

    def generate_overall_insights(self, product: str, clusters: List[ClusterResult]) -> dict:
        if self.client is None:
            self._warn_unavailable_once()
            return self._overall_fallback(clusters, self._unavailable_reason)

        summaries = "\n".join(
            f"- [{c.severity}] {c.label}: {c.summary} ({c.size} complaints)"
            for c in clusters
        )
        prompt = OVERALL_INSIGHTS_PROMPT.format(
            product=product,
            cluster_summaries=summaries,
        )

        try:
            raw = self._call_llm(prompt)
            result = self._parse_or_repair(raw, "overall insights", _OVERALL_SCHEMA)
            return _normalize_overall_result(result, clusters)
        except Exception as exc:
            logger.warning(
                "LLM overall insights generation failed for '%s' (%s: %s), using cluster labels as fallback.",
                product,
                type(exc).__name__,
                exc,
            )
            return self._overall_fallback(clusters, "LLM call failed")

    def _parse_or_repair(self, raw: str, context: str, schema: str) -> dict:
        try:
            return parse_json_object(raw, logger, context)
        except Exception as exc:
            log_parse_debug(logger, context, raw, exc)

        repair_prompt = REPAIR_JSON_PROMPT.format(schema=schema, raw=raw)
        repaired = self._call_llm(repair_prompt)
        return parse_json_object(repaired, logger, f"{context} repair")

    def _warn_unavailable_once(self) -> None:
        if self._warned_unavailable:
            return
        logger.warning("%s; using fallback analysis.", self._unavailable_reason)
        self._warned_unavailable = True

    @staticmethod
    def _apply_cluster_fallback(cluster: ClusterResult, reason: str) -> ClusterResult:
        cluster.label = cluster.label or f"Cluster {cluster.cluster_id}"
        cluster.summary = f"Analysis unavailable - {reason}"
        cluster.severity = cluster.severity or "medium"
        if not cluster.representative_quotes:
            cluster.representative_quotes = [item.text[:200] for item in cluster.items[:3]]
        return cluster

    @staticmethod
    def _overall_fallback(clusters: List[ClusterResult], reason: str) -> dict:
        return {
            "overall_insights": f"Analysis unavailable - {reason}",
            "top_pain_points": [c.label or f"Cluster {c.cluster_id}" for c in clusters[:3]],
        }


_CLUSTER_SCHEMA = """{
  "label": "2-5 word noun phrase",
  "summary": "2-3 sentence cluster summary",
  "severity": "high|medium|low"
}"""

_OVERALL_SCHEMA = """{
  "overall_insights": "3-4 sentence product assessment",
  "top_pain_points": ["pain point 1", "pain point 2", "pain point 3"]
}"""


def _clean_string(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalize_severity(value: object) -> str:
    severity = value.strip().lower() if isinstance(value, str) else ""
    return severity if severity in {"high", "medium", "low"} else "medium"


def _normalize_string_list(value: object, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    strings = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return strings[:limit] if limit is not None else strings


def _normalize_overall_result(result: dict, clusters: List[ClusterResult]) -> dict:
    top_points = _normalize_string_list(result.get("top_pain_points"), limit=min(3, len(clusters)))
    if not top_points:
        top_points = [c.label or f"Cluster {c.cluster_id}" for c in clusters[:3]]
    return {
        "overall_insights": _clean_string(result.get("overall_insights")),
        "top_pain_points": top_points,
    }
