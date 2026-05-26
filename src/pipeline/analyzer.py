import json
import logging
from typing import List
from openai import OpenAI
from src.models.cluster import ClusterResult
from src.config import LLMConfig

logger = logging.getLogger(__name__)


ANALYZE_CLUSTER_PROMPT = """You are a product research analyst. Analyze this cluster of user feedback/complaints about a product.

Cluster representative quotes:
{quotes}

Total items in this cluster: {size}

Provide your analysis in this exact JSON format:
{{
  "label": "short descriptive name for this complaint theme (3-5 words)",
  "summary": "2-3 sentence summary of the pain point this cluster represents",
  "severity": "high|medium|low (based on frequency and emotional intensity)"
}}

Respond only with the JSON, no additional text."""


OVERALL_INSIGHTS_PROMPT = """You are a product research analyst. Given the following clustered pain points for the product "{product}", provide:

1. A 3-4 sentence overall insight about the product's biggest weaknesses
2. A prioritized list of top 3 pain points (most severe first)

Cluster summaries:
{cluster_summaries}

Provide your analysis in this exact JSON format:
{{
  "overall_insights": "3-4 sentence overall assessment",
  "top_pain_points": ["pain point 1", "pain point 2", "pain point 3"]
}}

Respond only with the JSON, no additional text."""


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

    def _call_llm(self, prompt: str) -> str:
        if self.client is None:
            raise RuntimeError(self._unavailable_reason or "LLM client is unavailable")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return response.choices[0].message.content.strip()

    def analyze_cluster(self, cluster: ClusterResult) -> ClusterResult:
        quotes = "\n".join(f"- \"{q}\"" for q in cluster.representative_quotes)
        prompt = ANALYZE_CLUSTER_PROMPT.format(
            quotes=quotes,
            size=cluster.size,
        )

        if self.client is None:
            self._warn_unavailable_once()
            return self._apply_cluster_fallback(cluster, self._unavailable_reason)

        try:
            raw = self._call_llm(prompt)
            # Strip markdown code block markers if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            result = json.loads(raw)
            cluster.label = result.get("label", "Unnamed cluster")
            cluster.summary = result.get("summary", "")
            cluster.severity = result.get("severity", "medium")
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
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            return json.loads(raw)
        except Exception as exc:
            logger.warning(
                "LLM overall insights generation failed for '%s' (%s: %s), using cluster labels as fallback.",
                product,
                type(exc).__name__,
                exc,
            )
            return self._overall_fallback(clusters, "LLM call failed")

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
