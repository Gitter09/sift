from typing import List, Dict
from openai import OpenAI
from src.models.report import ProductReport, ComparisonReport
from src.config import LLMConfig


COMPARISON_PROMPT = """You are a competitive product analyst. Compare these products based on their pain points and user feedback.

Products: {products}

Product summaries:
{product_summaries}

Analyze and provide:

1. Shared pain points - issues that ALL products suffer from
2. Unique pain points - issues specific to each product that competitors don't have
3. Competitive insights - strategic recommendations based on the comparison

Provide your analysis in this exact JSON format:
{
  "shared_pain_points": ["shared issue 1", "shared issue 2"],
  "unique_pain_points": {
    "{product_1}": ["unique issue 1", "unique issue 2"],
    "{product_2}": ["unique issue 1", "unique issue 2"]
  },
  "competitive_insights": "3-4 sentence strategic comparison insight"
}

Respond only with the JSON, no additional text."""


class Comparator:
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

    def compare(self, reports: Dict[str, ProductReport]) -> ComparisonReport:
        products = list(reports.keys())
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
            import json
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
        except Exception as e:
            print(f"[Comparator] LLM comparison failed: {e}")
            # Fallback: compute basic comparison from cluster labels
            all_labels: Dict[str, List[str]] = {
                name: [c.label for c in report.clusters]
                for name, report in reports.items()
            }
            label_sets = [set(labels) for labels in all_labels.values()]
            shared = set.intersection(*label_sets) if label_sets else set()
            unique = {
                name: [l for l in labels if l not in shared]
                for name, labels in all_labels.items()
            }
            return ComparisonReport(
                products=products,
                product_reports=reports,
                shared_pain_points=list(shared),
                unique_pain_points=unique,
                competitive_insights="Comparison analysis unavailable (LLM call failed)",
            )
