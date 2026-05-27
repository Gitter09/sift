import hashlib
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class FeedbackItem:
    source: str          # source key such as "g2", "hacker_news", or "github_issues"
    product: str         # product name being analyzed
    text: str            # the actual feedback/complaint text
    rating: Optional[float] = None   # numeric rating if available (e.g. G2 stars)
    url: Optional[str] = None        # clickable link to original post/review
    date: Optional[datetime] = None  # when feedback was posted
    metadata: dict = field(default_factory=dict)  # extra source-specific fields
    id: str = field(init=False)      # deterministic hash ID for deduplication

    def __post_init__(self):
        raw = f"{self.source}:{self.url or self.text}"
        self.id = hashlib.sha256(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "product": self.product,
            "text": self.text,
            "rating": self.rating,
            "url": self.url,
            "date": self.date.isoformat() if self.date else None,
            "metadata": self.metadata,
        }
