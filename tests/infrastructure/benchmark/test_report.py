"""Tests for benchmark report generation."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.infrastructure.benchmark.report import (
    BenchmarkRecord,
    build_benchmark_report,
    load_benchmark_records,
    render_benchmark_html_report,
    render_benchmark_markdown_report,
)


def _make_record(
    *,
    model_provider: str,
    model_id: str,
    raw_output: object,
) -> BenchmarkRecord:
    return BenchmarkRecord(
        case_id="case-1",
        character_id="shirasagi-reina",
        scenario_label="greeting",
        memory_packet_id="memory-001",
        system_prompt="You are Reina.",
        conversation_history=(),
        user_prompt="How are you today?",
        model_provider=model_provider,
        model_id=model_id,
        generation_params={"temperature": 0.2},
        raw_output=raw_output,
        created_at=datetime(2026, 6, 11, 9, 0, tzinfo=UTC),
        token_usage={"input_tokens": 10, "output_tokens": 20},
        latency_ms=123,
    )


def test_load_benchmark_records(tmp_path: Path) -> None:
    """JSONL benchmark records should load into typed records."""

    input_path = tmp_path / "benchmark.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "case_id": "case-1",
                        "character_id": "shirasagi-reina",
                        "scenario_label": "greeting",
                        "memory_packet_id": "memory-001",
                        "system_prompt": "You are Reina.",
                        "conversation_history": [],
                        "user_prompt": "How are you today?",
                        "model_provider": "openai",
                        "model_id": "gpt-5.5",
                        "generation_params": {"temperature": 0.2},
                        "raw_output": {"contents": ["Hello."], "tool_calls": []},
                        "created_at": "2026-06-11T09:00:00+00:00",
                        "token_usage": {"input_tokens": 10, "output_tokens": 20},
                        "latency_ms": 123,
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    records = load_benchmark_records(input_path)

    assert len(records) == 1
    assert records[0].model_id == "gpt-5.5"
    assert records[0].conversation_history == ()


def test_render_benchmark_reports_group_cases_and_escape_output() -> None:
    """Reports should group records by case and escape HTML content."""

    records = [
        _make_record(
            model_provider="openai",
            model_id="gpt-5.5",
            raw_output={"contents": ["Hello <world>."], "tool_calls": []},
        ),
        _make_record(
            model_provider="google",
            model_id="gemini-2.5-pro",
            raw_output="こんにちは。",
        ),
    ]
    report = build_benchmark_report(
        records,
        title="Benchmark",
        generated_at=datetime(2026, 6, 11, 10, 0, tzinfo=UTC),
    )

    markdown = render_benchmark_markdown_report(report)
    html_report = render_benchmark_html_report(report)

    assert report.total_cases == 1
    assert report.total_records == 2
    assert "Case case-1" in markdown
    assert "openai / gpt-5.5" in markdown
    assert "gemini-2.5-pro" in markdown
    assert "Hello <world>." in markdown
    assert "&lt;world&gt;" in html_report
    assert "Conversation history" in html_report
