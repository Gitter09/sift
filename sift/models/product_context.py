from dataclasses import dataclass, field
from typing import Iterable

from sift.config import ProductProfileConfig, Settings


@dataclass(frozen=True)
class ProductContext:
    canonical_name: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    negative_terms: tuple[str, ...] = field(default_factory=tuple)
    category: str = ""
    description: str = ""
    website: str = ""
    repos: tuple[str, ...] = field(default_factory=tuple)
    slugs: tuple[str, ...] = field(default_factory=tuple)
    app_ids: tuple[str, ...] = field(default_factory=tuple)
    package_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def search_terms(self) -> tuple[str, ...]:
        return _unique_terms((self.canonical_name, *self.aliases))

    @property
    def identifiers(self) -> tuple[str, ...]:
        return _unique_terms((*self.repos, *self.slugs, *self.app_ids, *self.package_names))


def build_product_context(product_name: str, settings: Settings) -> ProductContext:
    profile = _lookup_profile(product_name, settings.products)
    if profile is None:
        return ProductContext(canonical_name=product_name, aliases=())

    aliases = _unique_terms((product_name, *profile.aliases))
    return ProductContext(
        canonical_name=product_name,
        aliases=aliases,
        negative_terms=_unique_terms(profile.negative_terms),
        category=profile.category,
        description=profile.description,
        website=profile.website,
        repos=tuple(profile.repos),
        slugs=tuple(profile.slugs),
        app_ids=tuple(profile.app_ids),
        package_names=tuple(profile.package_names),
    )


def _lookup_profile(
    product_name: str,
    profiles: dict[str, ProductProfileConfig],
) -> ProductProfileConfig | None:
    needle = product_name.casefold()
    for name, profile in profiles.items():
        candidates = [name, *profile.aliases]
        if any(candidate.casefold() == needle for candidate in candidates):
            return profile
    return None


def _unique_terms(terms: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        cleaned = str(term).strip()
        key = cleaned.casefold()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return tuple(result)
