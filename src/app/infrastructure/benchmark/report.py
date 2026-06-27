"""Utilities for turning benchmark JSONL outputs into human-readable reports."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts.messages.chat_history import ChatHistoryItem

_DEFAULT_MODEL_ORDER = (
    "gpt-5.5",
    "gpt-5.4",
    "gemini-3.5-flash",
    "gemini-2.5-pro",
    "gemini-3.1-pro",
)


@dataclass(frozen=True, slots=True)
class BenchmarkRecord:
    """One model response for a single benchmark case."""

    case_id: str
    character_id: str
    scenario_label: str
    memory_packet_id: str
    system_prompt: str
    conversation_history: tuple[ChatHistoryItem, ...]
    user_prompt: str
    model_provider: str
    model_id: str
    generation_params: dict[str, Any]
    raw_output: Any
    created_at: datetime | None
    token_usage: dict[str, Any]
    latency_ms: int | None


@dataclass(frozen=True, slots=True)
class BenchmarkCaseReport:
    """Grouped benchmark case with all model responses."""

    case_id: str
    character_id: str
    scenario_label: str
    memory_packet_id: str
    system_prompt: str
    conversation_history: tuple[ChatHistoryItem, ...]
    user_prompt: str
    records: tuple[BenchmarkRecord, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    """Rendered benchmark report payload."""

    title: str
    generated_at: datetime
    total_cases: int
    total_records: int
    case_reports: tuple[BenchmarkCaseReport, ...]
    model_ids: tuple[str, ...]


def load_benchmark_records(path: Path) -> list[BenchmarkRecord]:
    """Load benchmark records from a JSONL file."""

    records: list[BenchmarkRecord] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        records.append(_record_from_mapping(payload, line_number=line_number))
    return records


def build_benchmark_report(
    records: Sequence[BenchmarkRecord],
    *,
    title: str = "LLM Benchmark Report",
    generated_at: datetime | None = None,
    model_order: Sequence[str] | None = None,
) -> BenchmarkReport:
    """Group flat records into a report structure."""

    grouped: dict[str, list[BenchmarkRecord]] = defaultdict(list)
    for record in records:
        grouped[record.case_id].append(record)

    ordered_case_reports = [
        BenchmarkCaseReport(
            case_id=case_id,
            character_id=case_records[0].character_id,
            scenario_label=case_records[0].scenario_label,
            memory_packet_id=case_records[0].memory_packet_id,
            system_prompt=case_records[0].system_prompt,
            conversation_history=case_records[0].conversation_history,
            user_prompt=case_records[0].user_prompt,
            records=tuple(_sort_records(case_records, model_order=model_order)),
        )
        for case_id, case_records in sorted(grouped.items(), key=lambda item: item[0])
    ]

    ordered_model_ids = _ordered_model_ids(records, model_order=model_order)
    return BenchmarkReport(
        title=title,
        generated_at=generated_at or datetime.now(tz=UTC),
        total_cases=len(ordered_case_reports),
        total_records=len(records),
        case_reports=tuple(ordered_case_reports),
        model_ids=ordered_model_ids,
    )


def render_benchmark_markdown_report(report: BenchmarkReport) -> str:
    """Render a benchmark report as Markdown."""

    lines: list[str] = [
        f"# {report.title}",
        "",
        f"- Generated at: {report.generated_at.isoformat()}",
        f"- Cases: {report.total_cases}",
        f"- Responses: {report.total_records}",
        f"- Models: {', '.join(report.model_ids) if report.model_ids else 'none'}",
        "",
    ]

    for case in report.case_reports:
        lines.extend(
            [
                f"## Case {case.case_id}",
                "",
                f"- Character: `{case.character_id}`",
                f"- Scenario: `{case.scenario_label}`",
                f"- Memory packet: `{case.memory_packet_id}`",
                "",
                "### Input",
                "",
                "#### System prompt",
                "",
                "```text",
                case.system_prompt.rstrip(),
                "```",
                "",
                "#### Conversation history",
                "",
            ]
        )
        if case.conversation_history:
            for item in case.conversation_history:
                lines.extend(
                    [
                        f"- `{item.role}`: {item.content}",
                    ]
                )
        else:
            lines.append("- (empty)")
        lines.extend(
            [
                "",
                "#### User prompt",
                "",
                "```text",
                case.user_prompt.rstrip(),
                "```",
                "",
                "### Model outputs",
                "",
            ]
        )
        for record in case.records:
            lines.extend(
                [
                    f"#### {record.model_provider} / {record.model_id}",
                    "",
                    f"- Generated at: {record.created_at.isoformat() if record.created_at else 'null'}",
                    f"- Latency ms: {_render_optional_int(record.latency_ms)}",
                    f"- Generation params: `{_json_compact(record.generation_params)}`",
                    f"- Token usage: `{_json_compact(record.token_usage)}`",
                    "",
                    "```text",
                    _render_raw_output_text(record.raw_output).rstrip(),
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def render_benchmark_html_report(report: BenchmarkReport) -> str:
    """Render a benchmark report as standalone HTML."""

    summary_cards = "\n".join(
        [
            _html_summary_card("Generated", report.generated_at.isoformat()),
            _html_summary_card("Cases", str(report.total_cases)),
            _html_summary_card("Responses", str(report.total_records)),
            _html_summary_card(
                "Models",
                ", ".join(report.model_ids) if report.model_ids else "none",
            ),
        ]
    )
    case_sections = "\n".join(
        _render_case_section_html(case) for case in report.case_reports
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(report.title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f1e8;
      --panel: #fffaf3;
      --panel-2: #f1e7d8;
      --text: #201913;
      --muted: #6f6357;
      --accent: #8b5e34;
      --border: rgba(32, 25, 19, 0.14);
      --shadow: 0 18px 45px rgba(43, 31, 20, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(139, 94, 52, 0.12), transparent 36%),
        radial-gradient(circle at top right, rgba(97, 72, 39, 0.10), transparent 28%),
        linear-gradient(180deg, #f8f3ea 0%, var(--bg) 100%);
      color: var(--text);
    }}
    .page {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 32px 24px 56px;
    }}
    .hero {{
      background: linear-gradient(135deg, var(--panel), var(--panel-2));
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 28px;
      box-shadow: var(--shadow);
      margin-bottom: 24px;
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: clamp(2rem, 4vw, 3.3rem);
      letter-spacing: -0.03em;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      font-size: 0.98rem;
      line-height: 1.6;
    }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }}
    .summary-card {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 18px;
      box-shadow: var(--shadow);
    }}
    .summary-card .label {{
      color: var(--muted);
      font-size: 0.84rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .summary-card .value {{
      font-size: 1.2rem;
      font-weight: 700;
      line-height: 1.3;
      word-break: break-word;
    }}
    .case {{
      background: rgba(255, 250, 243, 0.88);
      border: 1px solid var(--border);
      border-radius: 22px;
      box-shadow: var(--shadow);
      padding: 22px;
      margin-bottom: 22px;
      backdrop-filter: blur(4px);
    }}
    .case-header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: flex-start;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    .case-header h2 {{
      margin: 0;
      font-size: 1.6rem;
      letter-spacing: -0.02em;
    }}
    .pill-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(139, 94, 52, 0.10);
      color: var(--accent);
      font-size: 0.84rem;
      font-weight: 600;
    }}
    .section-title {{
      margin: 20px 0 10px;
      font-size: 1.05rem;
      letter-spacing: -0.01em;
    }}
    .prompt-box, .model-box {{
      background: #fffdf9;
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 16px;
      overflow-x: auto;
    }}
    .history-list {{
      display: grid;
      gap: 10px;
    }}
    .history-item {{
      background: #fffdf9;
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 12px 14px;
    }}
    .history-role {{
      font-size: 0.82rem;
      font-weight: 700;
      color: var(--accent);
      margin-bottom: 6px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .model-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }}
    .model-card {{
      background: #fffdf9;
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 16px;
    }}
    .model-card h3 {{
      margin: 0 0 10px;
      font-size: 1.02rem;
      letter-spacing: -0.01em;
    }}
    .meta {{
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 12px;
      line-height: 1.5;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.6;
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 0.92rem;
    }}
    code {{
      font-family: inherit;
    }}
    @media (max-width: 720px) {{
      .page {{ padding: 18px 14px 42px; }}
      .hero {{ padding: 20px; }}
      .case {{ padding: 16px; }}
      .model-grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>{html.escape(report.title)}</h1>
      <p>Each case is grouped with the same input context and all model outputs side by side for manual review.</p>
    </header>
    <section class="summary-grid">
      {summary_cards}
    </section>
    {case_sections}
  </div>
</body>
</html>
"""


def write_benchmark_reports(
    records: Sequence[BenchmarkRecord],
    *,
    markdown_path: Path,
    html_path: Path,
    title: str = "LLM Benchmark Report",
    generated_at: datetime | None = None,
    model_order: Sequence[str] | None = None,
) -> BenchmarkReport:
    """Build the report and write Markdown and HTML outputs."""

    report = build_benchmark_report(
        records,
        title=title,
        generated_at=generated_at,
        model_order=model_order,
    )
    markdown_path.write_text(
        render_benchmark_markdown_report(report),
        encoding="utf-8",
    )
    html_path.write_text(
        render_benchmark_html_report(report),
        encoding="utf-8",
    )
    return report


def _record_from_mapping(
    payload: dict[str, Any],
    *,
    line_number: int,
) -> BenchmarkRecord:
    try:
        conversation_history = _parse_history(payload.get("conversation_history"))
        created_at = _parse_datetime(payload.get("created_at"))
        return BenchmarkRecord(
            case_id=_require_string(payload, "case_id", line_number=line_number),
            character_id=_require_string(
                payload, "character_id", line_number=line_number
            ),
            scenario_label=_require_string(
                payload, "scenario_label", line_number=line_number
            ),
            memory_packet_id=_require_string(
                payload, "memory_packet_id", line_number=line_number
            ),
            system_prompt=_require_string(
                payload, "system_prompt", line_number=line_number
            ),
            conversation_history=conversation_history,
            user_prompt=_require_string(
                payload, "user_prompt", line_number=line_number
            ),
            model_provider=_require_string(
                payload, "model_provider", line_number=line_number
            ),
            model_id=_require_string(payload, "model_id", line_number=line_number),
            generation_params=_parse_mapping(
                payload.get("generation_params"),
            ),
            raw_output=payload.get("raw_output", payload.get("response")),
            created_at=created_at,
            token_usage=_parse_mapping(payload.get("token_usage")),
            latency_ms=_parse_optional_int(payload.get("latency_ms")),
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise ValueError(
            f"Invalid benchmark record on line {line_number}: {exc}"
        ) from exc


def _ordered_model_ids(
    records: Sequence[BenchmarkRecord],
    *,
    model_order: Sequence[str] | None,
) -> tuple[str, ...]:
    preferred_order = (
        tuple(model_order) if model_order is not None else _DEFAULT_MODEL_ORDER
    )
    seen = {record.model_id for record in records}
    ordered: list[str] = [model_id for model_id in preferred_order if model_id in seen]
    ordered.extend(sorted(seen.difference(ordered)))
    return tuple(ordered)


def _sort_records(
    records: Sequence[BenchmarkRecord],
    *,
    model_order: Sequence[str] | None,
) -> list[BenchmarkRecord]:
    order_index = {
        model_id: index
        for index, model_id in enumerate(
            _ordered_model_ids(records, model_order=model_order)
        )
    }
    return sorted(
        records,
        key=lambda record: (
            order_index.get(record.model_id, len(order_index)),
            record.model_provider,
            record.model_id,
        ),
    )


def _render_case_section_html(case: BenchmarkCaseReport) -> str:
    history_html = (
        "\n".join(_render_history_item_html(item) for item in case.conversation_history)
        if case.conversation_history
        else '<div class="history-item"><div class="history-role">none</div><pre>(empty)</pre></div>'
    )
    model_cards = "\n".join(_render_model_card_html(record) for record in case.records)
    return f"""
    <article class="case">
      <div class="case-header">
        <div>
          <h2>Case {html.escape(case.case_id)}</h2>
          <div class="pill-row">
            <span class="pill">character: {html.escape(case.character_id)}</span>
            <span class="pill">scenario: {html.escape(case.scenario_label)}</span>
            <span class="pill">memory: {html.escape(case.memory_packet_id)}</span>
          </div>
        </div>
      </div>
      <div class="section-title">System prompt</div>
      <div class="prompt-box"><pre>{html.escape(case.system_prompt)}</pre></div>
      <div class="section-title">Conversation history</div>
      <div class="history-list">{history_html}</div>
      <div class="section-title">User prompt</div>
      <div class="prompt-box"><pre>{html.escape(case.user_prompt)}</pre></div>
      <div class="section-title">Model outputs</div>
      <div class="model-grid">{model_cards}</div>
    </article>
    """


def _render_history_item_html(item: ChatHistoryItem) -> str:
    return (
        '<div class="history-item">'
        f'<div class="history-role">{html.escape(item.role)}</div>'
        f"<pre>{html.escape(item.content)}</pre>"
        "</div>"
    )


def _render_model_card_html(record: BenchmarkRecord) -> str:
    created_at = record.created_at.isoformat() if record.created_at else "null"
    return f"""
    <div class="model-card">
      <h3>{html.escape(record.model_provider)} / {html.escape(record.model_id)}</h3>
      <div class="meta">
        generated_at: {html.escape(created_at)}<br />
        latency_ms: {html.escape(_render_optional_int(record.latency_ms))}<br />
        generation_params: {html.escape(_json_compact(record.generation_params))}<br />
        token_usage: {html.escape(_json_compact(record.token_usage))}
      </div>
      <pre>{html.escape(_render_raw_output_text(record.raw_output))}</pre>
    </div>
    """


def _html_summary_card(label: str, value: str) -> str:
    return f'<div class="summary-card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div></div>'


def _render_raw_output_text(raw_output: Any) -> str:
    if raw_output is None:
        return "null"
    if isinstance(raw_output, str):
        return raw_output
    try:
        return json.dumps(raw_output, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        return str(raw_output)


def _render_optional_int(value: int | None) -> str:
    if value is None:
        return "null"
    return str(value)


def _json_compact(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_history(value: object) -> tuple[ChatHistoryItem, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TypeError("conversation_history must be a list")
    return tuple(ChatHistoryItem.model_validate(item) for item in value)


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("created_at must be a string or null")
    return datetime.fromisoformat(value)


def _parse_mapping(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("expected a JSON object")
    return dict(value)


def _parse_optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    raise TypeError("expected an integer or null")


def _require_string(
    payload: dict[str, Any],
    key: str,
    *,
    line_number: int,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or empty required field '{key}'")
    return value.strip()
