from abc import ABC, abstractmethod
from typing import List
from sift.models.feedback import FeedbackItem


class BaseScraper(ABC):
    @abstractmethod
    def scrape(self, product_name: str) -> List[FeedbackItem]:
        """Scrape feedback for a given product name."""
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the stable config key for this data source."""
        pass
