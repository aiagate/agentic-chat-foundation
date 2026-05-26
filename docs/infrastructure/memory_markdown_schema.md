# Memory Markdown Schema

This document is the implementation contract for the local long-term memory
store. The store uses Markdown files with YAML Front Matter so memory remains
human-readable while still being safe for deterministic parsing, indexing, and
context-frame assembly.

## Goals

- Keep storage local, simple, and reviewable.
- Keep user-specific data scoped by user to avoid cross-user leakage.
- Keep persisted Markdown schema separate from application DTOs.
- Return parse, validation, and I/O failures through `MemoryServiceError`
  instead of leaking parser exceptions.
- Support a 3-layer memory model: Profile, Timeline, and Entity.
- Treat SQL raw chat logs as the canonical source for raw interaction history.
- Keep raw Timeline Markdown only for legacy import, manual notes, or temporary
  transition data; normal writers must persist abstract memory, not raw chat.
- Do not store external web search results or short-lived search workflow state
  in this schema.

## Memory Layers

### Profile

Profile memory is stable context about an actor.

- Agent profile: durable assistant-side identity, style, traits, and operating
  preferences. This is global, not scoped to an end user.
- User profile: durable user-side preferences, stable facts, and interaction
  preferences. This is scoped by `user_id`.
- Profile is not an event log. If a fact has a timestamped origin, keep the
  origin in Timeline and summarize only the stable conclusion in Profile.

### Timeline

Timeline memory is chronological episodic memory.

- Daily Timeline documents are consolidated summaries produced by sleep jobs
  from SQL raw chat logs.
- Raw Timeline Markdown documents are not the canonical raw log. They are
  allowed only as legacy/manual/temporary records during the migration.
- Timeline should answer "what happened, when, and where did this come from?"
- Timeline can reference Entity IDs but should not become the canonical place
  for normalized Entity attributes.

### Entity

Entity memory is normalized memory for concrete objects, concepts,
specifications, projects, people, or unresolved placeholders.

- Entity should answer "what is this thing, what do we know about it, and what
  is still unresolved?"
- Entity is user-scoped because the same label can mean different things for
  different users.
- Unknown facts must remain explicit using `missing_attributes` or
  `status: unresolved`; implementation must not invent values to force
  completion.

## Not Stored Here

The following data does not belong in long-term memory Markdown:

- raw web search results
- search session workflow state
- short-lived retrieved context used only for re-prompting

## Storage Layout

The target layout is:

```text
memory/
  profiles/
    agent.md
    users/
      <user_scope>.md
  timeline/
    <user_scope>/
      daily/
        YYYY/
          MM/
            YYYY-MM-DD.md
  entities/
    <user_scope>/
      <entity_id>.md
  catalog.json
```

`catalog.json` is optional for the first implementation. If it is absent, the
indexer must scan Markdown files.

### Path Segment Rules

- `<user_scope>` is derived from `user_id`.
- `<entity_id>` is derived from the Entity `id`.
- Path segments must be deterministic and safe on Windows, macOS, and Linux.
- If an ID contains only `A-Z`, `a-z`, `0-9`, `.`, `_`, or `-`, the segment may
  be the ID as-is except for reserved values.
- If an ID contains other characters, percent-encode the UTF-8 bytes. For
  example, `discord:123` becomes `discord%3A123`.
- Reject or encode path separators, drive prefixes, empty segments, `.`, and
  `..`. Implementations must never join an unvalidated ID directly into a path.
- The front matter `user_id` and `id` fields keep the original logical IDs.
  Path encoding is only a storage concern.

### Legacy Path Compatibility

Earlier documentation used `memory/profile/user.md`,
`memory/timeline/YYYY/MM/...`, and `memory/entities/<entity-id>.md`.
The target implementation must write only the user-scoped paths in this
document.

Temporary readers may scan legacy paths during the refactor, but only as a
compatibility fallback. If both a legacy file and a user-scoped file describe
the same logical record, the user-scoped file wins. New tests should assert the
target user-scoped paths, especially:

- `memory/profiles/agent.md`
- `memory/profiles/users/<user_scope>.md`
- `memory/timeline/<user_scope>/daily/YYYY/MM/YYYY-MM-DD.md`
- `memory/entities/<user_scope>/<entity_id>.md`

This resolves the Entity path mismatch: the canonical Entity path is
`memory/entities/<user_scope>/<entity_id>.md`, not
`memory/entities/<entity-id>.md`.

## Markdown Document Rules

- Every memory document must start with YAML Front Matter delimited by `---`.
- `schema_version` is required and currently must be `1`.
- `memory_type` is required and must be one of `profile`, `timeline`, or
  `entity`.
- The Markdown body is human-readable descriptive text.
- Parsers must use front matter for structured data and may index the body as
  searchable text.
- Writers must preserve Unicode text and write UTF-8.
- Unknown front matter fields are allowed only under `metadata` or
  `properties`. Top-level unknown fields should be treated as validation
  warnings at first and may become hard errors after implementation stabilizes.

## Common Front Matter

These fields are shared by all memory document types.

| Field | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `schema_version` | yes | integer | none | Schema version. Must be `1`. |
| `memory_type` | yes | string | none | `profile`, `timeline`, or `entity`. |
| `id` | yes | string | none | Stable logical document ID. |
| `user_id` | conditional | string or null | null | Required for user-scoped documents. Must be null or omitted for the global agent profile. |
| `created_at` | yes | ISO-8601 string | write time | UTC creation time. |
| `updated_at` | yes | ISO-8601 string | write time | UTC last update time. |
| `tags` | no | list of strings | `[]` | Search and filtering tags. |
| `importance` | no | number | `0.5` | Manual or computed importance from `0.0` to `1.0`. |
| `confidence` | no | number | `1.0` | Confidence from `0.0` to `1.0`. |
| `pinned` | no | boolean | `false` | Pinned documents must not be archived or compressed automatically. |
| `metadata` | no | map string to scalar | `{}` | Source-specific opaque metadata. |

All timestamps must be timezone-aware ISO-8601 strings. UTC with a `Z` suffix
or `+00:00` offset is preferred.

## Profile Schema

Profile files are:

- Agent profile: `memory/profiles/agent.md`
- User profile: `memory/profiles/users/<user_scope>.md`

Profile front matter fields:

| Field | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `schema_version` | yes | integer | none | Must be `1`. |
| `memory_type` | yes | string | none | Must be `profile`. |
| `id` | yes | string | none | `agent` for the agent profile, otherwise `profile:<user_id>`. |
| `profile_scope` | yes | string | none | `agent` or `user`. |
| `user_id` | conditional | string or null | null | Required when `profile_scope` is `user`; null or omitted when `agent`. |
| `display_name` | no | string or null | null | Human-readable name. |
| `summary` | no | string | `""` | Stable profile summary. |
| `traits` | no | list of strings | `[]` | Stable traits. |
| `preferences` | no | list of strings | `[]` | Stable preferences. |
| `communication_style` | no | list of strings | `[]` | Useful response-style guidance. |
| `known_constraints` | no | list of strings | `[]` | Durable constraints that affect future work. |
| `source_timeline_ids` | no | list of strings | `[]` | Timeline records that justify this profile. |
| `created_at` | yes | ISO-8601 string | write time | UTC creation time. |
| `updated_at` | yes | ISO-8601 string | write time | UTC last update time. |
| `tags` | no | list of strings | `[]` | Search and filtering tags. |
| `importance` | no | number | `0.8` | Profile defaults higher than Timeline. |
| `confidence` | no | number | `1.0` | Confidence from `0.0` to `1.0`. |
| `pinned` | no | boolean | `true` for agent, `false` for user | Archival protection. |
| `metadata` | no | map string to scalar | `{}` | Source-specific metadata. |

Profile body:

- H1 should be the display name or profile title.
- Body may contain sections such as `## Summary`, `## Traits`,
  `## Preferences`, and `## Communication Style`.
- The body should explain context for humans; structured readers should rely on
  front matter.

Example:

```markdown
---
schema_version: 1
memory_type: profile
id: profile:u1
profile_scope: user
user_id: u1
display_name: Dorothy
summary: Prefers direct, implementation-oriented answers.
traits: []
preferences:
  - Run verification commands when asked.
communication_style:
  - Keep summaries concise.
known_constraints: []
source_timeline_ids: []
created_at: 2026-05-18T00:00:00+00:00
updated_at: 2026-05-18T00:00:00+00:00
tags:
  - profile
importance: 0.8
confidence: 1.0
pinned: false
metadata: {}
---

# Dorothy

Stable user profile summary.
```

## Timeline Schema

Daily Timeline summary files are:

```text
memory/timeline/<user_scope>/daily/YYYY/MM/YYYY-MM-DD.md
```

Legacy/manual/temporary raw Timeline files may exist during migration:

```text
memory/timeline/<user_scope>/raw/YYYY/MM/YYYY-MM-DD_<role>-<id>.md
```

New automatic writers must not create raw Timeline Markdown for chat messages.
The SQL chat tables are the source of truth for raw conversation history.

Timeline front matter fields:

| Field | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `schema_version` | yes | integer | none | Must be `1`. |
| `memory_type` | yes | string | none | Must be `timeline`. |
| `id` | yes | string | none | Stable timeline ID. |
| `user_id` | yes | string | none | Logical user ID. |
| `timeline_type` | yes | string | none | `daily_summary`, `archived_summary`, or legacy/manual/temporary `raw`. |
| `kind` | yes | string | none | Event kind such as `user`, `assistant`, `system`, `tool`, or `summary`. |
| `content` | yes | string | none | Canonical event or summary text. |
| `occurred_at` | yes | ISO-8601 string | none | Event time for raw records, summary day start for daily summaries. |
| `source` | yes | string | none | Source system such as `chat`, `discord`, `line`, `api`, or `consolidation`. |
| `entity_ids` | no | list of strings | `[]` | Related Entity IDs. |
| `source_chat_ids` | no | list of strings | `[]` | SQL chat IDs used as source evidence for this abstract memory. |
| `summary_of` | no | list of strings | `[]` | Timeline summary IDs summarized or superseded by this document. Do not put SQL chat IDs here. |
| `consolidation_state` | no | string | `pending` for raw, `complete` for daily | Sleep/consolidation state. |
| `retention_state` | no | string | `active` | `active`, `compressed`, or `archived`. |
| `last_accessed_at` | no | ISO-8601 string or null | null | Last time used in context. |
| `access_count` | no | integer | `0` | Number of context-frame uses. |
| `decay_score` | no | number | `1.0` | Computed retention/search score. |
| `created_at` | yes | ISO-8601 string | write time | UTC creation time. |
| `updated_at` | yes | ISO-8601 string | write time | UTC last update time. |
| `tags` | no | list of strings | `[]` | Search and filtering tags. |
| `importance` | no | number | `0.5` | Importance from `0.0` to `1.0`. |
| `confidence` | no | number | `1.0` | Confidence from `0.0` to `1.0`. |
| `pinned` | no | boolean | `false` | Prevents automatic archival or compression. |
| `metadata` | no | map string to scalar | `{}` | Source-specific metadata. |

Timeline body:

- H1 should identify the Timeline kind, for example `# User memory` or
  `# Daily summary`.
- Daily body should include a concise summary and may include `## Source
  Chat IDs` and `## Summary Of`.

### Timeline Source Reference Policy

- `source_chat_ids` references canonical SQL raw chat rows.
- `summary_of` references other Markdown Timeline summary IDs only.
- Entity `referenced_in` should point to Timeline summary IDs when the Entity
  fact is derived from a summary, and may use `source_chat_ids` only when
  direct SQL evidence is intentionally retained.
- Legacy/manual raw Timeline Markdown may be read for attribution during the
  transition, but it must not become the source of truth for chat history.

## Entity Schema

Entity files are:

```text
memory/entities/<user_scope>/<entity_id>.md
```

Entity front matter fields:

| Field | Required | Type | Default | Description |
| --- | --- | --- | --- | --- |
| `schema_version` | yes | integer | none | Must be `1`. |
| `memory_type` | yes | string | none | Must be `entity`. |
| `id` | yes | string | none | Stable logical Entity ID. |
| `user_id` | yes | string | none | Logical user ID. |
| `label` | yes | string | none | Primary human-readable label. |
| `entity_type` | yes | string | none | Type such as `person`, `project`, `object`, `spec`, `place`, or `concept`. |
| `status` | no | string | `active` | `active`, `unresolved`, `deprecated`, `merged`, or `archived`. |
| `aliases` | no | list of strings | `[]` | Alternate labels. |
| `properties` | no | map string to scalar/list | `{}` | Normalized known facts. |
| `attributes` | no | map string to scalar/list | `{}` | Backward-compatible alias for `properties`; writers should prefer `properties`. |
| `missing_attributes` | no | list of strings | `[]` | Explicit unknown fields that need future resolution. |
| `referenced_in` | no | list of strings | `[]` | Timeline IDs that mention this Entity. |
| `source_chat_ids` | no | list of strings | `[]` | SQL chat IDs used as direct evidence when the Entity is updated from raw chat. |
| `merged_into` | no | string or null | null | Target Entity ID when `status` is `merged`. |
| `last_observed_at` | no | ISO-8601 string or null | null | Latest source observation time. |
| `last_accessed_at` | no | ISO-8601 string or null | null | Last time used in context. |
| `access_count` | no | integer | `0` | Number of context-frame uses. |
| `decay_score` | no | number | `1.0` | Computed retention/search score. |
| `created_at` | yes | ISO-8601 string | write time | UTC creation time. |
| `updated_at` | yes | ISO-8601 string | write time | UTC last update time. |
| `tags` | no | list of strings | `[]` | Search and filtering tags. |
| `importance` | no | number | `0.6` | Entity default is slightly above Timeline summaries. |
| `confidence` | no | number | `1.0` | Confidence from `0.0` to `1.0`. |
| `pinned` | no | boolean | `false` | Prevents automatic archival. |
| `metadata` | no | map string to scalar | `{}` | Source-specific metadata. |

Entity body:

- H1 should be the Entity `label`.
- Body should summarize what the Entity means to this user.
- Use `## Known Facts`, `## Missing Attributes`, and `## References` when
  helpful for human review.

Entity status rules:

- `active`: usable as normal context.
- `unresolved`: important but incomplete. Search should allow boosting when the
  query matches `label`, `aliases`, or `missing_attributes`.
- `deprecated`: kept for history but should be ranked below active records.
- `merged`: do not surface directly unless the query matches the old name;
  resolve to `merged_into` when possible.
- `archived`: kept on disk but excluded from normal context unless explicitly
  requested or pinned.

## Search-Indexed Fields

The first implementation should use simple dependency-free keyword scoring over
normalized lowercase text. Later implementations may replace the index without
changing persisted schema.

### Profile Indexed Fields

- `display_name`
- `summary`
- `traits`
- `preferences`
- `communication_style`
- `known_constraints`
- `tags`
- Markdown body

Profile search behavior:

- Agent profile is always eligible for context-frame assembly, even with no
  query match.
- User profile is eligible only for the requested `user_id`.
- Profile matches should be weighted as stable background, not as fresh
  evidence.

### Timeline Indexed Fields

- `content`
- `kind`
- `source`
- `entity_ids`
- `source_chat_ids`
- `summary_of`
- `tags`
- `metadata` scalar values
- Markdown body

Timeline search behavior:

- Filter by requested `user_id` before scoring.
- Prefer `daily_summary` over raw records when both match the same topic.
- Raw Timeline Markdown is excluded by default unless explicitly requested for
  legacy/manual/temporary diagnostics.
- `retention_state: archived` is excluded by default unless explicitly
  requested.

### Entity Indexed Fields

- `label`
- `entity_type`
- `status`
- `aliases`
- `properties`
- `attributes`
- `missing_attributes`
- `referenced_in`
- `source_chat_ids`
- `tags`
- Markdown body

Entity search behavior:

- Filter by requested `user_id` before scoring.
- Exact `label` or `aliases` matches should rank highly.
- `status: unresolved` can be boosted when the query asks about missing or
  unknown information.
- `status: merged` should resolve to `merged_into` when available.

### Supported Filters

The search layer should support these filters:

- `user_id`
- `memory_type`
- `tags`
- date range over `occurred_at`, `created_at`, or `updated_at`
- Entity `status`
- Entity `entity_type`
- Timeline `timeline_type`
- `consolidation_state`
- `retention_state`
- unresolved-only flag, equivalent to Entity `status: unresolved` or non-empty
  `missing_attributes`

## Context Frame Rules

The memory service should assemble a context frame before returning memory to
use cases. Use cases should not rank, search, or directly inspect storage paths.

### Frame Sections

Context frames are ordered as:

1. Primary
2. Functional
3. Peripheral

Primary:

- Directly query-matched Entities.
- User profile facts that directly affect the current answer.
- Recent or high-confidence Timeline summaries that directly support the query.

Functional:

- Agent profile and response-style constraints.
- User communication preferences.
- Entity facts needed to perform the task safely but not directly requested.
- Unresolved Entities that should prevent overconfident answers.

Peripheral:

- Supporting Timeline summaries.
- Low-score but potentially relevant Entities.
- Source notes that can be omitted first under budget pressure.

### Ordering and Budget

- Always filter by `user_id` before assembly, except the global agent profile.
- Include source headers for every surfaced document:
  `## Source: <relative-memory-path>`.
- Prefer daily Timeline summaries over legacy/manual raw Timeline entries.
- Prefer active or pinned documents over archived documents.
- Prefer higher `importance`, `confidence`, and query score.
- Apply decay to lower stale, low-importance, low-access records.
- Under size pressure, remove Peripheral first, then low-score Functional
  entries. Keep Primary entries unless the frame would exceed the hard budget.
- The assembled text must not include another user's scoped files.

## Sleep and Consolidation

Sleep/consolidation jobs convert SQL raw chat logs into denser long-term
Markdown memory. Scheduling is outside this schema, but persisted states are
defined here.

### Consolidation States

`consolidation_state` values:

- `pending`: source record has not been processed.
- `candidate`: selected for a consolidation run.
- `processing`: currently being consolidated. Jobs should use this only while
  they can recover stale locks.
- `complete`: processed into Profile, daily Timeline, Entity, or explicitly
  determined to need no update.
- `skipped`: intentionally ignored with a reason in `metadata.skip_reason`.
- `failed`: consolidation failed; `metadata.error` should contain a concise
  reason.

Daily Timeline summaries should normally use `complete`.

### Retention States

`retention_state` values:

- `active`: normal search and context behavior.
- `compressed`: original detail was summarized elsewhere; rank below active
  records.
- `archived`: retained on disk but excluded from normal retrieval.

Pinned records must not be moved to `compressed` or `archived` automatically.

### Decay Inputs

Decay scoring should be deterministic and based on persisted fields:

- `importance`
- `confidence`
- `pinned`
- `occurred_at` or `updated_at`
- `last_accessed_at`
- `access_count`
- `retention_state`

The exact score formula belongs in `memory_decay.py`, but the result should be
written to `decay_score` when materialized.

## Malformed File Handling

Malformed files must not crash chat generation or leak parser exceptions.
Infrastructure should convert failures into `MemoryServiceError` and include
enough location information for diagnostics.

Hard errors:

- Missing front matter block.
- Unterminated front matter block.
- YAML front matter that is not a mapping.
- Missing required fields.
- Unsupported `schema_version`.
- Invalid `memory_type`.
- Invalid timestamp format for required timestamp fields.
- Path scope and front matter `user_id` disagree.

Soft compatibility warnings:

- Top-level unknown fields outside `metadata` or `properties`.
- Legacy `attributes` used instead of `properties`.
- Legacy paths scanned during the transition.

Recommended read behavior:

- For single-document operations, return `Err(MemoryServiceError)` on hard
  errors.
- For index scans, collect malformed file diagnostics and return
  `Err(MemoryServiceError)` if any selected user-scoped file cannot be parsed.
- Do not silently ignore malformed files for the requested user; silent skips
  make memory loss hard to diagnose.
- Files outside the requested user scope must not be returned even if they parse
  successfully.

## Implementation Acceptance Criteria

- Writers create only the target user-scoped paths.
- Readers never return another user's Profile, Timeline, or Entity data.
- `schema_version: 1` is present in every new file.
- Entity files use `memory/entities/<user_scope>/<entity_id>.md`.
- Search uses the layer-specific indexed fields defined above.
- Context frames are assembled in Primary, Functional, Peripheral order.
- Malformed files become `MemoryServiceError` results.
- Sleep/consolidation states use the exact enum values in this document.
