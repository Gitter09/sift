from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class FeedbackItem:
    source: str          # "reddit" or "g2"
    product: str         # product name being analyzed
    text: str            # the actual feedback/complaint text
    rating: Optional[float] = None   # numeric rating if available (e.g. G2 stars)
    url: Optional[str] = None        # original URL
    author: Optional[str] = None     # username/reviewer
    date: Optional[datetime] = None  # when feedback was posted
    metadata: dict = field(default_factory=dict)  # extra source-specific fields

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "product": self.product,
            "text": self.text,
            "rating": self.rating,
            "url": self.url,
            "author": self.author,
            "date": self.date.isoformat() if self.date else None,
            "metadata": self.metadata,
        }
