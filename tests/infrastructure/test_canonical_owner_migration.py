"""Tests for the canonical owner migration safety guard."""

from importlib import util
from pathlib import Path

from sqlalchemy import Column, MetaData, String, Table, create_engine, insert

_migration_path = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "202607141600_add_canonical_chat_owner.py"
)
_migration_spec = util.spec_from_file_location(
    "canonical_owner_migration", _migration_path
)
if _migration_spec is None or _migration_spec.loader is None:
    raise RuntimeError("Could not load canonical owner migration.")
_migration = util.module_from_spec(_migration_spec)
_migration_spec.loader.exec_module(_migration)


def _chats_table(metadata: MetaData) -> Table:
    return Table(
        "chats",
        metadata,
        Column("id", String(26), primary_key=True),
        Column("external_participant_id", String(255)),
    )


def test_migration_guard_rejects_unresolved_participants() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    chats = _chats_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            insert(chats),
            [
                {"id": "legacy-unknown", "external_participant_id": "unknown"},
                {"id": "legacy-empty", "external_participant_id": ""},
                {"id": "legacy-known", "external_participant_id": "provider-1"},
            ],
        )
        result = _migration._unresolved_legacy_chat_ids(connection)

    assert result == ["legacy-unknown", "legacy-empty"]
    engine.dispose()


def test_migration_guard_allows_fully_identified_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    chats = _chats_table(metadata)
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            insert(chats).values(
                id="legacy-known",
                external_participant_id="provider-1",
            )
        )
        assert _migration._unresolved_legacy_chat_ids(connection) == []
    engine.dispose()
