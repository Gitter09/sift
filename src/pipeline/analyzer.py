from typing import List
from openai import OpenAI
from src.models.cluster import ClusterResult
from src.config import LLMConfig


ANALYZE_CLUSTER_PROMPT = """You are a product research analyst. Analyze this cluster of user feedback/complaints about a product.

Cluster representative quotes:
{quotes}

Total items in this cluster: {size}

Provide your analysis in this exact JSON format:
{
  "label": "short descriptive name for this complaint theme (3-5 words)",
  "summary": "2-3 sentence summary of the pain point this cluster represents",
  "severity": "high|medium|low (based on frequency and emotional intensity)"
}

Respond only with the JSON, no additional text."""


OVERALL_INSIGHTS_PROMPT = """You are a product research analyst. Given the following clustered pain points for the product "{product}", provide:

1. A 3-4 sentence overall insight about the product's biggest weaknesses
2. A prioritized list of top 3 pain points (most severe first)

Cluster summaries:
{cluster_summaries}

Provide your analysis in this exact JSON format:
{
  "overall_insights": "3-4 sentence overall assessment",
  "top_pain_points": ["pain point 1", "pain point 2", "pain point 3"]
}

Respond only with the JSON, no additional text."""


class Analyzer:
    def __init__(self, config: LLMConfig):
        self.client = OpenAI(
            api_key=config.api_key,
            base_url=config.base_url,
        )
        self.model = config.model
        self.temperature = config.temperature
        self.max_tokens = config.max_tokens

    def _call_llm(self, prompt: str) -> str:
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

        try:
            raw = self._call_llm(prompt)
            import json
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
        except Exception as e:
            print(f"[Analyzer] LLM parsing failed for cluster {cluster.cluster_id}: {e}")
            cluster.label = f"Cluster {cluster.cluster_id}"
            cluster.summary = "Analysis unavailable"
            cluster.severity = "medium"

        return cluster

    def analyze_clusters(self, clusters: List[ClusterResult]) -> List[ClusterResult]:
        for cluster in clusters:
            self.analyze_cluster(cluster)
        return clusters

    def generate_overall_insights(self, product: str, clusters: List[ClusterResult]) -> dict:
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
            import json
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            return json.loads(raw)
        except Exception as e:
            print(f"[Analyzer] Overall insights LLM call failed: {e}")
            return {
                "overall_insights": "Analysis unavailable",
                "top_pain_points": [c.label for c in clusters[:3]],
            }
