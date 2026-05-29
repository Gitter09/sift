import logging
from typing import Dict, List, Optional
from sift.scrapers.base import BaseScraper
from sift.scrapers.reddit import RedditScraper
from sift.scrapers.g2 import G2Scraper
from sift.config import Settings
from sift.scrapers.simple_sources import (
    AppStoreScraper,
    ChangelogScraper,
    DevToScraper,
    DiscordExportsScraper,
    GitHubIssuesScraper,
    HackerNewsScraper,
    LinkedInCommentsScraper,
    PlayStoreScraper,
    ProductHuntScraper,
    StackOverflowScraper,
    SupportForumsScraper,
    YouTubeScraper,
)

logger = logging.getLogger(__name__)

_g2_proxy_warning_shown = False

AVAILABLE_SOURCES = {
    "reddit",
    "g2",
    "app_store",
    "play_store",
    "youtube",
    "hacker_news",
    "github_issues",
    "product_hunt",
    "stack_overflow",
    "dev_to",
    "support_forums",
    "changelogs",
    "discord_exports",
    "linkedin_comments",
}


def get_scraper(source: str, settings: Settings) -> Optional[BaseScraper]:
    global _g2_proxy_warning_shown
    if source in settings.sources.disabled_sources:
        logger.info("Source '%s' is disabled, skipping.", source)
        return None

    if source == "reddit":
        return RedditScraper(settings.reddit)
    elif source == "g2":
        if not settings.g2.proxy_url and not _g2_proxy_warning_shown:
            from sift.ui.display import print_g2_proxy_warning
            print_g2_proxy_warning()
            _g2_proxy_warning_shown = True
        return G2Scraper(settings.g2)
    elif source == "app_store":
        return AppStoreScraper(settings.app_store)
    elif source == "play_store":
        return PlayStoreScraper(settings.play_store)
    elif source == "youtube":
        return YouTubeScraper(settings.youtube)
    elif source == "hacker_news":
        return HackerNewsScraper(settings.hacker_news)
    elif source == "github_issues":
        return GitHubIssuesScraper(settings.github_issues)
    elif source == "product_hunt":
        return ProductHuntScraper(settings.product_hunt)
    elif source == "stack_overflow":
        return StackOverflowScraper(settings.stack_overflow)
    elif source == "dev_to":
        return DevToScraper(settings.dev_to)
    elif source == "support_forums":
        return SupportForumsScraper(settings.support_forums)
    elif source == "changelogs":
        return ChangelogScraper(settings.changelogs)
    elif source == "discord_exports":
        return DiscordExportsScraper(settings.discord_exports)
    elif source == "linkedin_comments":
        return LinkedInCommentsScraper(settings.linkedin_comments)
    return None


def get_all_scrapers(settings: Settings) -> List[BaseScraper]:
    scrapers: List[BaseScraper] = []
    for source in default_sources(settings):
        scraper = get_scraper(source, settings)
        if scraper:
            scrapers.append(scraper)
    return scrapers


def default_sources(settings: Settings) -> List[str]:
    return [
        source
        for source in settings.sources.default_sources
        if source not in settings.sources.disabled_sources
        and is_source_configured(source, settings)
    ]


def is_source_configured(source: str, settings: Settings) -> bool:
    if source == "reddit":
        return bool(settings.reddit.client_id and settings.reddit.client_secret)
    if source == "app_store":
        return bool(settings.app_store.app_ids)
    if source == "play_store":
        return bool(settings.play_store.package_names)
    if source == "youtube":
        return bool(settings.youtube.api_key and settings.youtube.video_ids)
    if source == "support_forums":
        return bool(settings.support_forums.search_urls)
    if source == "changelogs":
        return bool(settings.changelogs.urls or settings.changelogs.search_urls)
    if source == "discord_exports":
        return bool(settings.discord_exports.paths or settings.discord_exports.urls)
    if source == "linkedin_comments":
        return bool(settings.linkedin_comments.paths or settings.linkedin_comments.urls)
    if source == "g2":
        return bool(settings.g2.proxy_url)
    # These sources work without any configuration (auto-discover or open APIs)
    return source in {"hacker_news", "github_issues", "product_hunt", "stack_overflow", "dev_to"}


_resolver_pipeline_singleton = None


def build_resolver_pipeline(settings: Settings):
    """Construct (and cache) the ResolverPipeline for the current Settings.

    Returns ``None`` when the resolver is disabled or no search backend
    is available — callers should fall through to manual config in that
    case.
    """
    global _resolver_pipeline_singleton
    if not settings.resolver.enabled:
        return None
    if _resolver_pipeline_singleton is not None:
        return _resolver_pipeline_singleton

    from sift.pipeline.resolver import (
        BraveSearchClient,
        LLMDisambiguator,
        ResolverPipeline,
        SitemapIndex,
    )

    if not settings.resolver.brave_api_key:
        logger.info("Resolver enabled but BRAVE_SEARCH_API_KEY not set; resolver inactive.")
        return None

    primary = BraveSearchClient(settings.resolver.brave_api_key)
    disambiguator = (
        LLMDisambiguator(settings.llm)
        if settings.resolver.use_llm_disambiguator
        else None
    )
    fallback = (
        SitemapIndex(settings.resolver.sitemap_cache_path)
        if settings.resolver.use_sitemap_fallback
        else None
    )
    _resolver_pipeline_singleton = ResolverPipeline.build(
        cache_path=settings.resolver.cache_path,
        cache_ttl_days=settings.resolver.cache_ttl_days,
        primary_search=primary,
        disambiguator=disambiguator,
        fallback_search=fallback,
    )
    return _resolver_pipeline_singleton


def get_cached_profile(settings: Settings, product_name: str):
    """Return the cached resolver ``ProductProfile`` for a product, or None.

    Reads the resolver cache directly (no enrichment / network) so the content
    disambiguator can build a rich Layer 2 anchor for free on a cache hit — the
    profile was already computed during scraping. Returns None when the resolver
    is disabled or the product was never resolved, in which case the anchor
    falls back to the config-derived ProductContext.
    """
    pipeline = build_resolver_pipeline(settings)
    if pipeline is None:
        return None
    try:
        entry = pipeline.cache.get_profile(product_name)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Resolver cache read failed for '%s': %s", product_name, e)
        return None
    return entry.value if entry else None


def resolve_source_refs(
    settings: Settings, product_name: str, sources: List[str]
) -> Dict[str, object]:
    """Resolve SourceRefs for the given sources, honoring manual overrides.

    For each source, manual config (e.g. ``app_store.app_ids[product]``)
    is preferred when present; the resolver only fills gaps. Returns a
    ``{source: SourceRef}`` mapping; missing sources are simply absent.
    """
    pipeline = build_resolver_pipeline(settings)
    if pipeline is None:
        return {}
    product_cfg = settings.products.get(product_name)
    hint_url = product_cfg.website if product_cfg else None
    refs: Dict[str, object] = {}
    for source in sources:
        if _has_manual_override(source, product_name, settings):
            continue
        try:
            ref = pipeline.resolve(product_name, [source], hint_url=hint_url).get(source)
        except Exception as e:
            logger.warning("Resolver error for %s/%s: %s", product_name, source, e)
            ref = None
        if ref is not None:
            refs[source] = ref
    return refs


def _has_manual_override(source: str, product_name: str, settings: Settings) -> bool:
    if source == "product_hunt":
        return bool(settings.product_hunt.slugs.get(product_name))
    if source == "g2":
        # G2 has no per-product slug map; resolver always fills.
        return False
    if source == "app_store":
        return bool(settings.app_store.app_ids.get(product_name))
    if source == "play_store":
        return bool(settings.play_store.package_names.get(product_name))
    if source == "github_issues":
        return bool(settings.github_issues.repos.get(product_name))
    return False
