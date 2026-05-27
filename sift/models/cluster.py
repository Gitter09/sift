from dataclasses import dataclass, field
from typing import List, Optional
from sift.models.feedback import FeedbackItem


@dataclass
class ClusterResult:
    cluster_id: int                      # HDBSCAN cluster label (-1 = noise)
    label: Optional[str] = None          # human-readable name (set by LLM later)
    items: List[FeedbackItem] = field(default_factory=list)
    summary: Optional[str] = None        # pain point summary (set by LLM later)
    severity: Optional[str] = None       # "high", "medium", "low" (set by LLM later)
    representative_quotes: List[str] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.items)

    @property
    def is_noise(self) -> bool:
        return self.cluster_id == -1

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "summary": self.summary,
            "severity": self.severity,
            "size": self.size,
            "representative_quotes": self.representative_quotes,
            "items": [item.to_dict() for item in self.items],
        }
