from dataclasses import dataclass, field
from typing import List, Optional, Dict
from sift.models.cluster import ClusterResult


@dataclass
class ProductReport:
    product: str
    total_feedback_count: int
    clusters: List[ClusterResult] = field(default_factory=list)
    overall_insights: Optional[str] = None     # LLM-generated high-level summary
    top_pain_points: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "total_feedback_count": self.total_feedback_count,
            "clusters": [c.to_dict() for c in self.clusters],
            "overall_insights": self.overall_insights,
            "top_pain_points": self.top_pain_points,
        }


@dataclass
class ComparisonReport:
    products: List[str]
    product_reports: Dict[str, ProductReport] = field(default_factory=dict)
    shared_pain_points: List[str] = field(default_factory=list)
    unique_pain_points: Dict[str, List[str]] = field(default_factory=dict)
    competitive_insights: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "products": self.products,
            "product_reports": {k: v.to_dict() for k, v in self.product_reports.items()},
            "shared_pain_points": self.shared_pain_points,
            "unique_pain_points": self.unique_pain_points,
            "competitive_insights": self.competitive_insights,
        }
