import json
import logging
from typing import List, Dict
from openai import OpenAI
from src.models.report import ProductReport, ComparisonReport
from src.config import LLMConfig

logger = logging.getLogger(__name__)


COMPARISON_PROMPT = """You are a competitive product analyst. Compare these products based on their pain points and user feedback.

Products: {products}

Product summaries:
{product_summaries}

Analyze and provide:

1. Shared pain points - issues that ALL products suffer from
2. Unique pain points - issues specific to each product that competitors don't have
3. Competitive insights - strategic recommendations based on the comparison

Provide your analysis in this exact JSON format:
{{
  "shared_pain_points": ["shared issue 1", "shared issue 2"],
  "unique_pain_points": {{
    "{{product_1}}": ["unique issue 1", "unique issue 2"],
    "{{product_2}}": ["unique issue 1", "unique issue 2"]
  }},
  "competitive_insights": "3-4 sentence strategic comparison insight"
}}

Respond only with the JSON, no additional text."""


class Comparator:
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

    def compare(self, reports: Dict[str, ProductReport]) -> ComparisonReport:
        products = list(reports.keys())
        if self.client is None:
            self._warn_unavailable_once()
            return self._fallback_comparison(products, reports, self._unavailable_reason)

        product_summaries = ""
        for name, report in reports.items():
            cluster_info = "\n".join(
                f"  - [{c.severity}] {c.label}: {c.summary}"
                for c in report.clusters
            )
            product_summaries += f"\n{name}:\n{cluster_info}\n  Overall: {report.overall_insights}\n"

        prompt = COMPARISON_PROMPT.format(
            products=", ".join(products),
            product_summaries=product_summaries,
        )

        try:
            raw = self._call_llm(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

            result = json.loads(raw)
            return ComparisonReport(
                products=products,
                product_reports=reports,
                shared_pain_points=result.get("shared_pain_points", []),
                unique_pain_points=result.get("unique_pain_points", {}),
                competitive_insights=result.get("competitive_insights", ""),
            )
        except Exception as exc:
            logger.warning(
                "LLM comparison failed for %s (%s: %s), using cluster label intersection as fallback.",
                ", ".join(products),
                type(exc).__name__,
                exc,
            )
            return self._fallback_comparison(products, reports, "LLM call failed")

    def _warn_unavailable_once(self) -> None:
        if self._warned_unavailable:
            return
        logger.warning("%s; using fallback comparison.", self._unavailable_reason)
        self._warned_unavailable = True

    @staticmethod
    def _fallback_comparison(
        products: List[str],
        reports: Dict[str, ProductReport],
        reason: str,
    ) -> ComparisonReport:
        all_labels: Dict[str, List[str]] = {
            name: [c.label or f"Cluster {c.cluster_id}" for c in report.clusters]
            for name, report in reports.items()
        }
        label_sets = [set(labels) for labels in all_labels.values()]
        shared = set.intersection(*label_sets) if label_sets else set()
        unique = {
            name: [label for label in labels if label not in shared]
            for name, labels in all_labels.items()
        }
        return ComparisonReport(
            products=products,
            product_reports=reports,
            shared_pain_points=list(shared),
            unique_pain_points=unique,
            competitive_insights=f"Comparison analysis unavailable ({reason})",
        )
