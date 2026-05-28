import json
import logging
import os
from typing import List, Optional

import click

from sift.config import load_settings, setup_logging, Settings
from sift.scrapers.factory import (
    AVAILABLE_SOURCES,
    default_sources,
    get_scraper,
    is_source_configured,
)
from sift.pipeline.dedup import DedupFilter
from sift.pipeline.relevance import RelevanceFilter
from sift.pipeline.report_generator import save_reports
from sift.models.feedback import FeedbackItem
from sift.models.product_context import build_product_context
from sift.models.report import ProductReport, ComparisonReport

from sift.ui.display import (
    console,
    print_banner,
    print_config_summary,
    print_cluster_summary,
    print_comparison_summary,
    print_report_preview,
    print_comparison_preview,
    print_done_banner,
    print_skip_warning,
    print_scraper_warning,
    print_unknown_sources,
    print_no_scraper,
    print_dedup_summary,
    print_relevance_summary,
    print_no_reports,
    ScrapeProgress,
    PipelineProgress,
)

logger = logging.getLogger(__name__)

SOURCE_HELP = "Data source to use. Default: configured active sources."

# Shared verbose option decorator
_verbose_option = click.option(
    "--verbose", "-v", is_flag=True, default=False,
    help="Enable debug-level logging output.",
)


# ---------------------------------------------------------------------------
# Click group — entry point
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True)
@_verbose_option
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Sift - scrape, cluster, and analyze product feedback.

    Run without arguments to launch the interactive CLI.
    Use 'sift analyze PRODUCT' or 'sift scrape PRODUCT' for scripted runs.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if ctx.invoked_subcommand is None:
        # No subcommand → launch interactive mode.
        from sift.ui.setup import is_configured, run_setup_wizard
        from sift.ui.menu import run_main_menu

        if not is_configured():
            run_setup_wizard()

        run_main_menu()


# ---------------------------------------------------------------------------
# Extracted pipeline runners (no Click dependency — reusable)
# ---------------------------------------------------------------------------


def run_analyze(
    products: List[str],
    sources: List[str],
    settings: Settings,
    output: str = "output",
    no_preview: bool = False,
    verbose: bool = False,
    show_banner: bool = True,
) -> None:
    """Run the full analyze pipeline for one or more products.

    This is the core logic shared by the interactive menu and the ``analyze``
    Click subcommand.  All terminal output goes through ``src.ui.display``.
    """
    setup_logging(settings, verbose=verbose)

    if show_banner:
        print_banner()
    print_config_summary(settings, sources)

    dedup = DedupFilter()
    relevance = RelevanceFilter(settings.relevance)
    all_feedback: dict[str, list[FeedbackItem]] = {}

    total_scrape_tasks = len(products) * len(sources)
    with ScrapeProgress(total=total_scrape_tasks) as scrape_progress:
        from sift.scrapers.factory import resolve_source_refs
        for product in products:
            feedback: list[FeedbackItem] = []
            source_counts: dict[str, int] = {}
            resolved_refs = resolve_source_refs(settings, product, sources)
            for src in sources:
                scraper = get_scraper(src, settings)
                if scraper:
                    scraper.set_source_ref(resolved_refs.get(src))
                    scrape_progress.update_desc(f"Scraping {src} › {product}")
                    try:
                        items = scraper.scrape(product)
                        source_counts[src] = len(items)
                        feedback.extend(items)
                    except Exception:
                        logger.exception("Scraper '%s' failed for '%s'.", src, product)
                        print_scraper_warning(src, product)
                        source_counts[src] = 0
                else:
                    print_no_scraper(src)
                scrape_progress.advance()

            counts_str = ", ".join(f"{s}={source_counts.get(s, 0)}" for s in sources if s in source_counts)
            logger.info("Source breakdown for '%s': %s", product, counts_str)

            context = build_product_context(product, settings)
            total_before_relevance = len(feedback)
            feedback, relevance_stats = relevance.filter(feedback, context)
            print_relevance_summary(
                total_before_relevance,
                relevance_stats.rejected,
                relevance_stats.kept,
                relevance_stats.relaxed,
            )

            total_before_dedup = len(feedback)
            feedback = dedup.filter(feedback)
            if len(feedback) > settings.max_feedback_per_source:
                feedback = feedback[:settings.max_feedback_per_source]

            all_feedback[product] = feedback
            print_dedup_summary(
                total_before_dedup,
                total_before_dedup - len(feedback),
                len(feedback),
            )

    product_reports: dict[str, ProductReport] = {}
    for product, feedback in all_feedback.items():
        if len(feedback) < 3:
            print_skip_warning(product, len(feedback))
            continue

        from sift.pipeline.analyzer import Analyzer
        from sift.pipeline.clusterer import Clusterer
        from sift.pipeline.comparator import Comparator
        from sift.pipeline.embedder import Embedder

        embedder = Embedder(settings.clustering)
        clusterer = Clusterer(settings.clustering)
        analyzer_inst = Analyzer(settings.llm)
        comparator = Comparator(settings.llm)

        with PipelineProgress(total_stages=2) as pipeline:
            pipeline.stage(f"Embedding — {product}")
            embeddings = embedder.embed(feedback)
            pipeline.advance()

            pipeline.stage(f"Clustering — {product}")
            clusters = clusterer.cluster(embeddings, feedback)
            pipeline.advance()

            # Expand total now that we know the cluster count so the bar
            # advances once per LLM call rather than jumping 25% at a time.
            n = len(clusters)
            pipeline.set_total(2 + n + 1)

            for i, cluster in enumerate(clusters, 1):
                pipeline.stage(f"Analysing — {product} ({i}/{n})")
                analyzer_inst.analyze_cluster(cluster)
                pipeline.advance()

            pipeline.stage(f"Insights — {product}")
            insights = analyzer_inst.generate_overall_insights(product, clusters)
            pipeline.advance()

            report = ProductReport(
                product=product,
                total_feedback_count=len(feedback),
                clusters=clusters,
                overall_insights=insights.get("overall_insights", ""),
                top_pain_points=insights.get("top_pain_points", []),
            )
            product_reports[product] = report

    if not product_reports:
        empty_products = [product for product, feedback in all_feedback.items() if not feedback]
        if empty_products:
            from sift.ui.display import print_no_feedback_guidance

            for product in empty_products:
                print_no_feedback_guidance(product, sources)
        print_no_reports()
        return

    # In-terminal summaries
    for product, report in product_reports.items():
        print_cluster_summary(report)
        if not no_preview:
            print_report_preview(report)

    if len(product_reports) >= 2:
        with PipelineProgress(total_stages=1) as pipeline:
            pipeline.stage("Comparison")
            comparison = comparator.compare(product_reports)
            pipeline.advance()
        print_comparison_summary(comparison)
        if not no_preview:
            print_comparison_preview(comparison)
    else:
        report = list(product_reports.values())[0]
        comparison = ComparisonReport(
            products=list(product_reports.keys()),
            product_reports=product_reports,
            shared_pain_points=report.top_pain_points,
            unique_pain_points={report.product: report.top_pain_points},
            competitive_insights="Single product analyzed - no comparison available.",
        )

    saved_files = save_reports(product_reports, comparison, output)
    print_done_banner(output, saved_files)


def run_scrape(
    product: str,
    sources: List[str],
    settings: Settings,
    output: str = "output",
    verbose: bool = False,
    show_banner: bool = True,
) -> None:
    """Run the scrape-only pipeline for a single product.

    This is the core logic shared by the interactive menu and the ``scrape``
    Click subcommand.
    """
    setup_logging(settings, verbose=verbose)

    if show_banner:
        print_banner()
    print_config_summary(settings, sources)

    dedup = DedupFilter()
    relevance = RelevanceFilter(settings.relevance)
    feedback: list[FeedbackItem] = []
    from sift.scrapers.factory import resolve_source_refs
    resolved_refs = resolve_source_refs(settings, product, sources)
    with ScrapeProgress(total=len(sources)) as scrape_progress:
        for src in sources:
            scraper = get_scraper(src, settings)
            if scraper:
                scraper.set_source_ref(resolved_refs.get(src))
                scrape_progress.update_desc(f"Scraping {src} › {product}")
                try:
                    items = scraper.scrape(product)
                    feedback.extend(items)
                except Exception:
                    logger.exception("Scraper '%s' failed for '%s'.", src, product)
                    print_scraper_warning(src, product)
            else:
                print_no_scraper(src)
            scrape_progress.advance()

    context = build_product_context(product, settings)
    total_before_relevance = len(feedback)
    feedback, relevance_stats = relevance.filter(feedback, context)
    print_relevance_summary(
        total_before_relevance,
        relevance_stats.rejected,
        relevance_stats.kept,
        relevance_stats.relaxed,
    )

    total_before = len(feedback)
    feedback = dedup.filter(feedback)
    print_dedup_summary(total_before, total_before - len(feedback), len(feedback))
    if not feedback:
        from sift.ui.display import print_no_feedback_guidance

        print_no_feedback_guidance(product, sources)

    os.makedirs(output, exist_ok=True)
    slug = product.lower().replace(" ", "_")
    path = os.path.join(output, f"{slug}_raw.json")
    with open(path, "w") as f:
        json.dump([item.to_dict() for item in feedback], f, indent=2)
    print_done_banner(output, [path])


# ---------------------------------------------------------------------------
# Click subcommand wrappers
# ---------------------------------------------------------------------------


@main.command("init")
@click.option("--config", "-c", default="config.yaml", help="Path to config file to generate.")
def init_cmd(config: str) -> None:
    """Generate a default config.yaml and launch the API key setup wizard.

    Run this after installing Sift to create the configuration files you need.
    """
    from sift.ui.config_wizard import run_config_wizard
    from sift.ui.setup import run_setup_wizard

    run_config_wizard(config)
    run_setup_wizard()


@main.command()
@click.argument("products", nargs=-1, required=True)
@click.option("--source", "-s", multiple=True, help=SOURCE_HELP)
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory for reports.")
@click.option(
    "--no-preview", "-P", is_flag=True, default=False,
    help="Skip in-terminal markdown report preview.",
)
@_verbose_option
@click.pass_context
def analyze(
    ctx: click.Context,
    products: tuple[str, ...],
    source: tuple[str, ...],
    config: str,
    output: str,
    verbose: bool,
    no_preview: bool,
) -> None:
    """Analyze feedback for one or more products."""
    settings = load_settings(config)
    sources = _resolve_sources(source, settings)
    run_analyze(
        products=list(products),
        sources=sources,
        settings=settings,
        output=output,
        no_preview=no_preview,
        verbose=verbose,
    )


@main.command("scrape")
@click.argument("product")
@click.option("--source", "-s", multiple=True, help=SOURCE_HELP)
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory.")
@_verbose_option
@click.pass_context
def scrape_cmd(
    ctx: click.Context,
    product: str,
    source: tuple[str, ...],
    config: str,
    output: str,
    verbose: bool,
) -> None:
    """Scrape feedback for a product (no analysis)."""
    settings = load_settings(config)
    sources = _resolve_sources(source, settings)
    run_scrape(
        product=product,
        sources=sources,
        settings=settings,
        output=output,
        verbose=verbose,
    )


@main.command("resolve")
@click.argument("product")
@click.option("--source", "-s", multiple=True, help="Source(s) to resolve. Default: all.")
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--url", default=None, help="Optional homepage URL hint to skip search-based enrichment.")
@_verbose_option
@click.pass_context
def resolve_cmd(
    ctx: click.Context,
    product: str,
    source: tuple[str, ...],
    config: str,
    url: Optional[str],
    verbose: bool,
) -> None:
    """Dry-run resolution: print the ProductProfile and per-source SourceRef.

    Use this to debug why a product isn't being found, or to demo what the
    resolver auto-derives without running a full scrape.
    """
    from sift.scrapers.factory import build_resolver_pipeline

    settings = load_settings(config)
    setup_logging(settings, verbose=verbose)
    pipeline = build_resolver_pipeline(settings)
    if pipeline is None:
        click.echo("Resolver disabled or BRAVE_SEARCH_API_KEY not set. Edit config.yaml or .env.")
        return

    sources = list(source) if source else list(pipeline.resolvers.keys())
    profile = pipeline.get_profile(product, hint_url=url)
    click.echo(f"\nProductProfile for '{product}':")
    click.echo(f"  homepage     : {profile.homepage}")
    click.echo(f"  site_name    : {profile.site_name}")
    click.echo(f"  category     : {profile.category}")
    click.echo(f"  description  : {profile.description[:200]}")
    click.echo(f"  enricher_used: {profile.enricher_used}")
    click.echo(f"  snippets     : {len(profile.search_snippets)}")
    click.echo("\nResolved source refs:")
    for src in sources:
        ref = pipeline.resolve_source(profile, src)
        if ref is None:
            click.echo(f"  {src:<16} : (none)")
        else:
            click.echo(
                f"  {src:<16} : {ref.identifier}  "
                f"[conf={ref.confidence:.2f} via={ref.resolver_used}]"
            )
            if ref.url:
                click.echo(f"  {'':<16}   {ref.url}")


@main.group("cache")
def cache_grp() -> None:
    """Inspect and manage the resolver cache."""


@cache_grp.command("show")
@click.option("--product", "-p", default=None, help="Show only this product's entries.")
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
def cache_show_cmd(product: Optional[str], config: str) -> None:
    """Print cached profiles and source refs."""
    from sift.pipeline.resolver import ResolverCache

    settings = load_settings(config)
    cache = ResolverCache(settings.resolver.cache_path, ttl_days=settings.resolver.cache_ttl_days)
    if product:
        entry = cache.get_profile(product)
        if not entry:
            click.echo(f"No cached profile for '{product}'.")
            return
        click.echo(f"Profile [{entry.resolver_used}, resolved_at={entry.resolved_at.isoformat()}]")
        for k, v in entry.value.to_dict().items():
            if k == "search_snippets":
                click.echo(f"  {k}: {len(v)} snippets")
            elif k == "raw_metadata":
                click.echo(f"  {k}: {len(v)} fields")
            else:
                click.echo(f"  {k}: {v}")
        click.echo("\nRefs:")
        for row in cache.list_refs_for(product):
            r = row["ref"]
            click.echo(
                f"  {row['source']:<16} → {r.identifier}  "
                f"[conf={row['confidence']:.2f} via={row['resolver_used']}]"
            )
        return

    rows = cache.list_profiles()
    if not rows:
        click.echo("Cache is empty.")
        return
    click.echo(f"Cached profiles ({len(rows)}):")
    for row in rows:
        click.echo(f"  {row['name']:<30} {row['resolved_at']}  [{row['resolver_used']}]")


@cache_grp.command("clear")
@click.option("--product", "-p", default=None, help="Clear only this product (all sources).")
@click.option("--source", "-s", default=None, help="When used with --product, clear only this source's ref.")
@click.option("--all", "clear_all", is_flag=True, help="Wipe the entire cache.")
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
def cache_clear_cmd(
    product: Optional[str], source: Optional[str], clear_all: bool, config: str
) -> None:
    """Invalidate cached resolutions when the resolver got it wrong."""
    from sift.pipeline.resolver import ResolverCache

    settings = load_settings(config)
    cache = ResolverCache(settings.resolver.cache_path, ttl_days=settings.resolver.cache_ttl_days)

    if clear_all:
        cache.clear_all()
        click.echo("Cleared entire resolver cache.")
        return
    if not product:
        click.echo("Provide --product, or --all.")
        return
    if source:
        n = cache.clear_ref(product, source)
        click.echo(f"Removed {n} ref for '{product}' / '{source}'.")
    else:
        n = cache.clear_profile(product)
        click.echo(f"Removed {n} cache entries for '{product}'.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_sources(source: tuple[str, ...], settings: Settings) -> List[str]:
    requested = list(source) if source else default_sources(settings)
    unknown = [src for src in requested if src not in AVAILABLE_SOURCES]
    if unknown:
        print_unknown_sources(unknown)
    resolved = [src for src in requested if src in AVAILABLE_SOURCES]

    if source:
        return resolved

    skipped = [
        src
        for src in settings.sources.default_sources
        if src not in settings.sources.disabled_sources
        and src in AVAILABLE_SOURCES
        and not is_source_configured(src, settings)
    ]
    if skipped:
        from sift.ui.display import print_unconfigured_sources

        print_unconfigured_sources(skipped)
    return resolved


if __name__ == "__main__":
    main()
