import json
import click
from src.config import load_settings
from src.scrapers.factory import get_scraper, get_all_scrapers
from src.pipeline.embedder import Embedder
from src.pipeline.clusterer import Clusterer
from src.pipeline.analyzer import Analyzer
from src.pipeline.comparator import Comparator
from src.pipeline.report_generator import save_reports
from src.models.feedback import FeedbackItem
from src.models.report import ProductReport


@click.group()
def main():
    """Sift - scrape, cluster, and analyze product feedback."""
    pass


@main.command()
@click.argument("products", nargs=-1, required=True)
@click.option("--source", "-s", multiple=True, help="Data source to use (reddit, g2). Default: all available.")
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory for reports.")
def analyze(products, source, config, output):
    """Analyze feedback for one or more products."""
    settings = load_settings(config)
    sources = list(source) if source else ["reddit", "g2"]

    all_feedback: dict[str, list[FeedbackItem]] = {}
    for product in products:
        feedback = []
        for src in sources:
            scraper = get_scraper(src, settings)
            if scraper:
                print(f"[Scrape] Collecting {src} feedback for '{product}'...")
                items = scraper.scrape(product)
                feedback.extend(items)
            else:
                print(f"[Scrape] No scraper available for '{src}'")

        all_feedback[product] = feedback[:settings.max_feedback_per_source]
        print(f"[Scrape] Total feedback for '{product}': {len(all_feedback[product])}")

    embedder = Embedder(settings.clustering)
    clusterer = Clusterer(settings.clustering)
    analyzer = Analyzer(settings.llm)
    comparator = Comparator(settings.llm)

    product_reports = {}
    for product, feedback in all_feedback.items():
        if len(feedback) < 3:
            print(f"[Pipeline] Too few feedback items for '{product}' ({len(feedback)}), skipping analysis")
            continue

        print(f"[Pipeline] Embedding {len(feedback)} feedback items for '{product}'...")
        embeddings = embedder.embed(feedback)

        print(f"[Pipeline] Clustering embeddings...")
        clusters = clusterer.cluster(embeddings, feedback)

        print(f"[Pipeline] Analyzing {len(clusters)} clusters with LLM...")
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

    if len(product_reports) >= 2:
        print(f"[Pipeline] Generating multi-product comparison...")
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
    print(f"\n[Done] Reports saved to '{output}/' directory")


@main.command()
@click.argument("product")
@click.option("--source", "-s", multiple=True, help="Data source (reddit, g2).")
@click.option("--config", "-c", default="config.yaml", help="Path to config file.")
@click.option("--output", "-o", default="output", help="Output directory.")
def scrape_cmd(product, source, config, output):
    """Just scrape feedback for a product (no analysis)."""
    settings = load_settings(config)
    sources = list(source) if source else ["reddit", "g2"]

    feedback = []
    for src in sources:
        scraper = get_scraper(src, settings)
        if scraper:
            print(f"[Scrape] Collecting {src} feedback for '{product}'...")
            items = scraper.scrape(product)
            feedback.extend(items)

    import os
    os.makedirs(output, exist_ok=True)
    slug = product.lower().replace(" ", "_")
    path = os.path.join(output, f"{slug}_raw.json")
    with open(path, "w") as f:
        json.dump([item.to_dict() for item in feedback], f, indent=2)
    print(f"[Scrape] Saved {len(feedback)} items to {path}")


# Rename command to "scrape" for CLI display
scrape_cmd.name = "scrape"


if __name__ == "__main__":
    main()
