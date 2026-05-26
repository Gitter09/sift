import json
import logging
import os

import click

from src.config import load_settings, setup_logging
from src.scrapers.factory import AVAILABLE_SOURCES, default_sources, get_scraper
from src.pipeline.dedup import DedupFilter
from src.pipeline.embedder import Embedder
from src.pipeline.clusterer import Clusterer
from src.pipeline.analyzer import Analyzer
from src.pipeline.comparator import Comparator
from src.pipeline.report_generator import save_reports
from src.models.feedback import FeedbackItem
from src.models.report import ProductReport

logger = logging.getLogger(__name__)

SOURCE_HELP = "Data source to use. Default: configured active sources."

# Shared verbose option decorator
_verbose_option = click.option(
    "--verbose", "-v", is_flag=True, default=False,
    help="Enable debug-level logging output.",
)


@click.group()
@_verbose_option
@click.pass_context
def main(ctx, verbose):
    """Sift - scrape, cluster, and analyze product feedback."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.argument("products", nargs=-1, required=True)
@click.option("--source", "-s", multiple=True, help=SOURCE_HELP)
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory for reports.")
@_verbose_option
@click.pass_context
def analyze(ctx, products, source, config, output, verbose):
    """Analyze feedback for one or more products."""
    settings = load_settings(config)
    setup_logging(settings, verbose=verbose)
    sources = _resolve_sources(source, settings)

    dedup = DedupFilter()
    all_feedback: dict[str, list[FeedbackItem]] = {}

    for product in products:
        feedback: list[FeedbackItem] = []
        for src in sources:
            scraper = get_scraper(src, settings)
            if scraper:
                click.echo(f"Scraping {src} feedback for '{product}'...")
                try:
                    items = scraper.scrape(product)
                    feedback.extend(items)
                except Exception:
                    logger.exception("Scraper '%s' failed for '%s'.", src, product)
                    click.echo(
                        f"[WARNING] {src} scraper encountered an error for '{product}'. "
                        f"Check logs for details.", err=True,
                    )
            else:
                click.echo(f"No enabled scraper available for '{src}'", err=True)

        # Deduplicate and cap
        feedback = dedup.filter(feedback)
        if len(feedback) > settings.max_feedback_per_source:
            feedback = feedback[:settings.max_feedback_per_source]

        all_feedback[product] = feedback
        click.echo(f"Collected {len(feedback)} unique items for '{product}'.")

    embedder = Embedder(settings.clustering)
    clusterer = Clusterer(settings.clustering)
    analyzer = Analyzer(settings.llm)
    comparator = Comparator(settings.llm)

    product_reports = {}
    for product, feedback in all_feedback.items():
        if len(feedback) < 3:
            click.echo(
                f"[SKIP] Too few feedback items for '{product}' ({len(feedback)}), "
                f"need at least 3 for analysis.", err=True,
            )
            continue

        click.echo(f"[{product}] Generating embeddings for {len(feedback)} items...")
        embeddings = embedder.embed(feedback)

        click.echo(f"[{product}] Clustering feedback...")
        clusters = clusterer.cluster(embeddings, feedback)

        click.echo(f"[{product}] Analyzing {len(clusters)} clusters with LLM...")
        clusters = analyzer.analyze_clusters(clusters)

        insights = analyzer.generate_overall_insights(product, clusters)
        report = ProductReport(
            product=product,
            total_feedback_count=len(feedback),
            clusters=clusters,
            overall_insights=insights.get("overall_insights", ""),
            top_pain_points=insights.get("top_pain_points", []),
        )
        product_reports[product] = report

    if not product_reports:
        click.echo("No reports generated because no product had enough feedback for analysis.", err=True)
        return

    if len(product_reports) >= 2:
        click.echo("Generating multi-product comparison...")
        comparison = comparator.compare(product_reports)
    else:
        from src.models.report import ComparisonReport
        report = list(product_reports.values())[0]
        comparison = ComparisonReport(
            products=list(product_reports.keys()),
            product_reports=product_reports,
            shared_pain_points=report.top_pain_points,
            unique_pain_points={report.product: report.top_pain_points},
            competitive_insights="Single product analyzed - no comparison available.",
        )

    save_reports(product_reports, comparison, output)
    click.echo(f"\nDone! Reports saved to '{output}/' directory")


@main.command("scrape")
@click.argument("product")
@click.option("--source", "-s", multiple=True, help=SOURCE_HELP)
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory.")
@_verbose_option
@click.pass_context
def scrape_cmd(ctx, product, source, config, output, verbose):
    """Scrape feedback for a product (no analysis)."""
    settings = load_settings(config)
    setup_logging(settings, verbose=verbose)
    sources = _resolve_sources(source, settings)

    dedup = DedupFilter()
    feedback: list[FeedbackItem] = []
    for src in sources:
        scraper = get_scraper(src, settings)
        if scraper:
            click.echo(f"Scraping {src} feedback for '{product}'...")
            try:
                items = scraper.scrape(product)
                feedback.extend(items)
            except Exception:
                logger.exception("Scraper '%s' failed for '%s'.", src, product)
                click.echo(
                    f"[WARNING] {src} scraper encountered an error for '{product}'. "
                    f"Check logs for details.", err=True,
                )
        else:
            click.echo(f"No enabled scraper available for '{src}'", err=True)

    feedback = dedup.filter(feedback)

    os.makedirs(output, exist_ok=True)
    slug = product.lower().replace(" ", "_")
    path = os.path.join(output, f"{slug}_raw.json")
    with open(path, "w") as f:
        json.dump([item.to_dict() for item in feedback], f, indent=2)
    click.echo(f"Saved {len(feedback)} unique items to {path}")


def _resolve_sources(source: tuple[str, ...], settings) -> list[str]:
    requested = list(source) if source else default_sources(settings)
    unknown = [src for src in requested if src not in AVAILABLE_SOURCES]
    if unknown:
        click.echo(f"Unknown source(s): {', '.join(unknown)}", err=True)
    return [src for src in requested if src in AVAILABLE_SOURCES]


if __name__ == "__main__":
    main()
