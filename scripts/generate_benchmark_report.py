"""Generate Markdown and HTML benchmark reports from JSONL records."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.infrastructure.benchmark.report import (
    load_benchmark_records,
    write_benchmark_reports,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate human-readable benchmark reports from JSONL data.",
    )
    parser.add_argument(
        "input",
        type=Path,
        help="Path to the benchmark JSONL file.",
    )
    parser.add_argument(
        "--markdown",
        type=Path,
        default=None,
        help="Output Markdown file. Defaults to <input>.report.md",
    )
    parser.add_argument(
        "--html",
        type=Path,
        default=None,
        help="Output HTML file. Defaults to <input>.report.html",
    )
    parser.add_argument(
        "--title",
        type=str,
        default="LLM Benchmark Report",
        help="Report title.",
    )
    parser.add_argument(
        "--model-order",
        action="append",
        default=None,
        dest="model_order",
        help="Preferred display order for models. Repeat to specify multiple values.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    input_path: Path = args.input
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    markdown_path = args.markdown or input_path.with_suffix(".report.md")
    html_path = args.html or input_path.with_suffix(".report.html")

    records = load_benchmark_records(input_path)
    report = write_benchmark_reports(
        records,
        markdown_path=markdown_path,
        html_path=html_path,
        title=args.title,
        model_order=args.model_order,
    )
    print(
        "Wrote benchmark report: "
        f"{markdown_path} and {html_path} "
        f"({report.total_cases} cases, {report.total_records} responses)"
    )


if __name__ == "__main__":
    main()
