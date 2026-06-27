"""Tests for the shared agent runtime."""

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import Err, Ok, is_err
from sqlalchemy import desc, select

from app.contracts.messages.agent_profile import AgentProfileBundle
from app.contracts.messages.character_definition import (
    CharacterDefinition,
)
from app.contracts.messages.chat_events import (
    CHAT_TOOL_REQUESTED_TOPIC,
    DISCORD_CHAT_REPLY_READY_TOPIC,
)
from app.contracts.messages.chat_history import ChatHistoryItem
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_context import (
    MemoryContextPack,
    MemoryEntity,
    MemoryManifestItem,
    MemoryProfile,
    MemoryTimelineEntry,
)
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.messages.tool_result_context import ToolResultContext
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.tool_result_store import (
    IToolResultStore,
    ToolResultStoreError,
)
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.services.tool_catalog import StaticToolCatalog
from app.infrastructure.stores.tool_call_store import InMemoryToolCallStore
from app.infrastructure.stores.tool_result_store import (
    InMemoryToolResultStore,
)
from app.usecases.agent.route_tool_calls import (
    RouteToolCallsCommand,
    RouteToolCallsHandler,
)
from app.usecases.agent.run_agent_turn import (
    RunAgentTurnHandler,
    RunAgentTurnQuery,
    _latest_session_window,
)
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery

RUN_AGENT_MODULE = "app.usecases.agent.run_agent_turn"
CHARACTER_ID = "shirasagi-reina"
RELATIONSHIP_ENTITY_ID = f"relationship:{CHARACTER_ID}"


def test_session_window_keeps_messages_across_utc_date_change() -> None:
    """A UTC date rollover alone must not break an active conversation."""

    history = [
        ChatHistoryItem(
            id="before-midnight",
            chat_type=ChatType.LINE,
            role="user",
            content="before",
            occurred_at=datetime(2026, 6, 21, 23, 53, tzinfo=UTC),
        ),
        ChatHistoryItem(
            id="after-midnight",
            chat_type=ChatType.LINE,
            role="assistant",
            content="after",
            occurred_at=datetime(2026, 6, 22, 0, 13, tzinfo=UTC),
        ),
    ]

    session, boundary = _latest_session_window(
        history,
        memory_boundary_at=None,
    )

    assert [item.id for item in session] == ["before-midnight", "after-midnight"]
    assert boundary is None


def test_session_window_uses_24_hour_fallback_boundary() -> None:
    """A gap over 24 hours starts a new session without memory sleep."""

    history = [
        ChatHistoryItem(
            id="old",
            chat_type=ChatType.LINE,
            role="user",
            content="old",
            occurred_at=datetime(2026, 6, 20, 0, 0, tzinfo=UTC),
        ),
        ChatHistoryItem(
            id="new",
            chat_type=ChatType.LINE,
            role="user",
            content="new",
            occurred_at=datetime(2026, 6, 21, 0, 1, tzinfo=UTC),
        ),
    ]

    session, boundary = _latest_session_window(
        history,
        memory_boundary_at=None,
    )

    assert [item.id for item in session] == ["new"]
    assert boundary is not None
    assert boundary[2] == 24 * 60 + 1


class _FakeAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AGENT_PROFILE_BUNDLE


AGENT_PROFILE_BUNDLE = AgentProfileBundle(
    profile=MemoryProfile(user_id="ai"),
    character=CharacterDefinition(
        character_id=CHARACTER_ID,
        relationship_entity_id=RELATIONSHIP_ENTITY_ID,
        relationship_entity_label="Relationship with Jon Due",
    ),
    persona_context=(
        "## Persona Contract\n"
        "Identity:\n"
        "- You are Jon Due, a calm host persona.\n"
        "- Speak in natural English with a composed tone.\n"
        "- Do not mention that you are an AI, model, bot, or language model.\n\n"
        "Character:\n"
        "- Treat conversation like hosting a guest: anticipate comfort, answer "
        "clearly, and avoid brusque wording.\n"
        "Relational habits:\n"
        "- Leave a conversational opening with at most one easy-to-answer "
        "question when the topic is not complete."
    ),
    relationship_entity_id=RELATIONSHIP_ENTITY_ID,
    relationship_entity_label="Relationship with Jon Due",
    relationship_entity_type="relationship",
    relationship_tag="agent-growth",
)


@pytest.fixture
def mock_ai_service(mocker: Any) -> IAIService:
    service = mocker.Mock(spec=IAIService)
    service.generate_content = mocker.AsyncMock(
        return_value=Ok(GeneratedContent(contents=["Generated Content"]))
    )
    return service


@pytest.fixture
def mock_event_bus(mocker: Any) -> IEventBus:
    service = mocker.Mock(spec=IEventBus)
    service.publish = mocker.AsyncMock(return_value=None)
    return service


@pytest.fixture
def mock_agent_profile_service() -> IAgentProfileService:
    return _FakeAgentProfileService()


@pytest.fixture
def mock_tool_result_store(mocker: Any) -> IToolResultStore:
    store = mocker.Mock(spec=IToolResultStore)
    store.get = mocker.AsyncMock(
        return_value=Ok(
            ToolResultContext(
                tool_call_id="tool-1",
                character_id=CHARACTER_ID,
                tool_name="web_search",
                status="ok",
                rendered_text="## Retrieved Context\n- example",
            )
        )
    )
    return store


@pytest.fixture
def mock_tool_catalog() -> StaticToolCatalog:
    return StaticToolCatalog()


@pytest.fixture
def tool_call_store() -> InMemoryToolCallStore:
    return InMemoryToolCallStore()


async def _seed_raw_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    *,
    user_id: str,
    created_at: datetime | None = None,
) -> str:
    session = cast(Any, getattr(uow, "_session", None))
    if session is None:
        raise RuntimeError("Unit of work session is not available")

    chat_orm = cast(ChatORM, ORMMappingRegistry.to_orm(chat))
    chat_orm.user_id = user_id
    chat_orm.role = "user"
    if created_at is not None:
        chat_orm.created_at = created_at
        chat_orm.updated_at = created_at
    session.add(chat_orm)
    await session.flush()
    return chat.id.to_primitive()


@pytest.mark.anyio
async def test_run_agent_turn_persists_reply(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test the happy path for a non-tool response."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    async with uow:
        await _seed_raw_chat(
            uow,
            DiscordChat.create(
                guild_id="DM",
                channel_id="123",
                message_content=MessageContent.text("hello"),
            ),
            user_id="u1",
        )
        await uow.commit()

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == ["Generated Content"]
    async with uow:
        session = cast(Any, getattr(uow, "_session", None))
        if session is None:
            raise RuntimeError("Unit of work session is not available")
        table = cast(Any, ChatORM).__table__
        statement = (
            select(table)
            .where(
                table.c.type == ChatType.DISCORD.to_primitive(),
                table.c.user_id == "u1",
                table.c.role == "assistant",
            )
            .order_by(desc(table.c.created_at), desc(table.c.id))
            .limit(1)
        )
        saved_result = await session.execute(statement)
        saved_chat = saved_result.mappings().one()
        assert saved_chat["message_content"]["payload"]["texts"] == [
            "Generated Content"
        ]
    ai_stub: Any = mock_ai_service.generate_content
    ai_stub.assert_awaited_once()
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert {tool.name for tool in tool_definitions} == {
        "web_search",
        "memory.read",
        "memory.write_candidate",
        "discord.send",
    }
    tool_result_store_mock: Any = mock_tool_result_store.get
    tool_result_store_mock.assert_not_awaited()
    publish_mock = mock_event_bus.publish
    publish_mock.assert_awaited_once_with(
        DISCORD_CHAT_REPLY_READY_TOPIC,
        {
            "chat_type": "DISCORD",
            "contents": ["Generated Content"],
            "guild_id": "DM",
            "channel_id": "123",
            "character_id": CHARACTER_ID,
        },
    )


@pytest.mark.anyio
async def test_run_agent_turn_resolves_prompt_from_chat_id(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that the handler can recover the prompt from persisted chat data."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    async with uow:
        chat_id = await _seed_raw_chat(
            uow,
            DiscordChat.create(
                guild_id="DM",
                channel_id="123",
                message_content=MessageContent.text("hello"),
            ),
            user_id="u1",
        )
        await uow.commit()

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            chat_id=chat_id,
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    assert ai_stub.call_args.args[0] == "hello"


@pytest.mark.anyio
async def test_run_agent_turn_filters_previous_session_history(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that the handler isolates the current session before prompting."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    async with uow:
        previous_user_id = await _seed_raw_chat(
            uow,
            DiscordChat.create(
                guild_id="DM",
                channel_id="123",
                message_content=MessageContent.text("yesterday dinner"),
            ),
            user_id="u1",
            created_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
        )
        previous_assistant_id = await _seed_raw_chat(
            uow,
            DiscordChat.create(
                guild_id="DM",
                channel_id="123",
                message_content=MessageContent.text("assistant follow-up"),
            ),
            user_id="u1",
            created_at=datetime(2026, 6, 1, 18, 5, tzinfo=UTC),
        )
        await _seed_raw_chat(
            uow,
            DiscordChat.create(
                guild_id="DM",
                channel_id="123",
                message_content=MessageContent.text("today dinner"),
            ),
            user_id="u1",
            created_at=datetime(2026, 6, 2, 12, 0, tzinfo=UTC),
        )
        mark_result = await (
            uow.GetMemoryConsolidatedChatSourceRepository().mark_consolidated(
                [previous_user_id, previous_assistant_id],
                consolidated_at=datetime(2026, 6, 2, 3, 0, tzinfo=UTC),
            )
        )
        assert not is_err(mark_result)
        await uow.commit()

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="today dinner",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    assert ai_stub.call_args.args[1] == []
    system_instruction = ai_stub.call_args.kwargs["system_instruction"]
    assert "chat_scope: DISCORD guild_id=DM channel_id=123 user_id=u1" in (
        system_instruction
    )
    assert "has_session_boundary: true" in system_instruction
    assert "current_session_started_at: 2026-06-02T12:00:00+00:00" in (
        system_instruction
    )


@pytest.mark.anyio
async def test_run_agent_turn_limits_tools_for_line_chat(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that LINE chats only receive LINE reply tools."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    async with uow:
        await _seed_raw_chat(
            uow,
            LineChat.create_user_chat(
                line_user_id="U1234567890",
                message_content=MessageContent.text("hello"),
            ),
            user_id="U1234567890",
        )
        await uow.commit()

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="LINE",
            channel_id="chat-1",
            user_id="U1234567890",
            chat_type=ChatType.LINE,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert {tool.name for tool in tool_definitions} == {
        "web_search",
        "memory.read",
        "memory.write_candidate",
        "line.send",
    }


@pytest.mark.anyio
async def test_run_agent_turn_includes_retrieved_context(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that retrieved context becomes the current tool-result input."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    assert "## Retrieved Context" in ai_stub.call_args.args[0]
    system_instruction = ai_stub.call_args.kwargs["system_instruction"]
    assert "Memory manifest:" in system_instruction
    assert "Identity:" in system_instruction
    assert "Do not mention that you are an AI" in system_instruction
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert any(tool.name == "web_search" for tool in tool_definitions)
    tool_result_store_mock: Any = mock_tool_result_store.get
    tool_result_store_mock.assert_awaited_once_with(
        "tool-1",
        character_id=CHARACTER_ID,
    )


@pytest.mark.anyio
async def test_run_agent_turn_prefers_direct_answering_in_system_instruction(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that the agent persona context discourages self-disclosure."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="What kind of food do you like?",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    system_instruction = ai_stub.call_args.kwargs["system_instruction"]
    assert "Treat conversation like hosting a guest" in system_instruction
    assert "Speak in natural English with a composed tone" in system_instruction


@pytest.mark.anyio
async def test_in_memory_tool_result_store_returns_copy() -> None:
    """Test that the in-memory retrieved context store returns a copy."""

    store = InMemoryToolResultStore()
    saved = ToolResultContext(
        tool_call_id="tool-1",
        character_id=CHARACTER_ID,
        tool_name="web_search",
        status="ok",
        rendered_text="## Retrieved Context\n- example",
    )
    await store.save(saved)

    result = await store.get("tool-1", character_id=CHARACTER_ID)

    assert not is_err(result)
    assert result.value.tool_call_id == "tool-1"
    assert result.value is not saved


@pytest.mark.anyio
async def test_run_agent_turn_continues_when_search_context_is_missing(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that missing retrieved context does not suppress the final reply."""

    mock_tool_result_store.get = AsyncMock(
        return_value=Err(ToolResultStoreError("Retrieved context not found"))
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            tool_call_id="tool-1",
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == ["Generated Content"]
    tool_result_store_mock: Any = mock_tool_result_store.get
    tool_result_store_mock.assert_awaited_once_with(
        "tool-1",
        character_id=CHARACTER_ID,
    )
    publish_mock = mock_event_bus.publish
    publish_mock.assert_awaited_once()


@pytest.mark.anyio
async def test_run_agent_turn_includes_tool_failure_context(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that tool failure notes become the current tool-result input."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            tool_failure_context=(
                "Tool failure context: web_search failed with error: HTTP 500."
            ),
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    ai_stub: Any = mock_ai_service.generate_content
    assert "Tool result received with an error." in ai_stub.call_args.args[0]
    assert (
        "Tool failure context: web_search failed with error: HTTP 500."
        in (ai_stub.call_args.args[0])
    )
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert any(tool.name == "web_search" for tool in tool_definitions)


@pytest.mark.anyio
async def test_run_agent_turn_preserves_ai_service_error_message(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that AI service failures keep their original message."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Err(AIServiceError("Gemini API Error: boom"))
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert is_err(result)
    assert "Gemini API Error: boom" in result.error.message


@pytest.mark.anyio
async def test_run_agent_turn_routes_generic_tool_calls(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Visible contents and tool calls are both processed."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=["Searching now."],
                tool_calls=[
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="web_search",
                        arguments={
                            "query": "ollama web search",
                            "max_results": 3,
                            "source_request_id": "chat-1",
                        },
                    )
                ],
            )
        )
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        if isinstance(request, RouteToolCallsCommand):
            handler = RouteToolCallsHandler(
                mock_event_bus,
                mock_tool_catalog,
                tool_call_store,
            )
            return await handler.handle(request)
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="ollama web search",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == ["Searching now."]
    publish_mock = mock_event_bus.publish
    assert publish_mock.await_count == 2
    reply_topic, reply_payload = publish_mock.await_args_list[0].args
    assert reply_topic == DISCORD_CHAT_REPLY_READY_TOPIC
    assert reply_payload["contents"] == ["Searching now."]
    topic, payload = publish_mock.await_args_list[1].args
    assert topic == CHAT_TOOL_REQUESTED_TOPIC
    assert payload["tool_name"] == "web_search"
    assert payload["character_id"] == CHARACTER_ID
    assert "arguments" not in payload
    stored = await tool_call_store.get(
        payload["tool_call_id"],
        character_id=CHARACTER_ID,
    )
    assert not is_err(stored)
    assert stored.value.character_id == CHARACTER_ID


@pytest.mark.anyio
async def test_run_agent_turn_routes_memory_read_tool_calls(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Test that memory read tool calls flow through the generic runtime."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=[],
                tool_calls=[
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="memory.read",
                        arguments={
                            "memory_id": "entity:memory-lookup",
                        },
                    )
                ],
            )
        )
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        if isinstance(request, RouteToolCallsCommand):
            handler = RouteToolCallsHandler(
                mock_event_bus,
                mock_tool_catalog,
                tool_call_store,
            )
            return await handler.handle(request)
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="read memory",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == []
    publish_mock = mock_event_bus.publish
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == CHAT_TOOL_REQUESTED_TOPIC
    assert payload["tool_name"] == "memory.read"
    assert "arguments" not in payload
    stored = await tool_call_store.get(
        payload["tool_call_id"],
        character_id=CHARACTER_ID,
    )
    assert not is_err(stored)
    assert stored.value.arguments == {"memory_id": "entity:memory-lookup"}


@pytest.mark.anyio
async def test_run_agent_turn_routes_all_tool_calls_per_turn(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_tool_result_store: IToolResultStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Test that every requested tool is routed independently."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=[],
                tool_calls=[
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="web_search",
                        arguments={
                            "query": "ollama web search",
                            "max_results": 3,
                            "source_request_id": "chat-1",
                        },
                    ),
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="memory.read",
                        arguments={
                            "memory_id": "entity:memory-lookup",
                        },
                    ),
                ],
            )
        )
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        if isinstance(request, RouteToolCallsCommand):
            handler = RouteToolCallsHandler(
                mock_event_bus,
                mock_tool_catalog,
                tool_call_store,
            )
            return await handler.handle(request)
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{RUN_AGENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = RunAgentTurnHandler(
        ai_service,
        mock_tool_result_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="mixed retrieval",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == []
    publish_mock = mock_event_bus.publish
    assert publish_mock.await_count == 2
    tool_names = [call.args[1]["tool_name"] for call in publish_mock.await_args_list]
    assert tool_names == ["web_search", "memory.read"]


def _memory_context_pack() -> MemoryContextPack:
    return MemoryContextPack(
        user_id="u1",
        assembled_context=(
            "Memory manifest:\n"
            "Use memory.read with a memory_id when detailed memory is needed.\n"
            "- profile:u1 | profile | Dorothy | Likes concise answers."
        ),
        manifest_items=[
            MemoryManifestItem(
                memory_id="profile:u1",
                memory_type="profile",
                title="Dorothy",
                summary="Likes concise answers.",
                tags=[],
                updated_at="2026-05-11T00:00:00Z",
            )
        ],
        profile=MemoryProfile(
            user_id="u1",
            display_name="Dorothy",
            summary="Likes concise answers.",
            traits=["pragmatic"],
            preferences=["short replies"],
        ),
        timelines=[
            MemoryTimelineEntry(
                id="timeline-1",
                user_id="u1",
                kind="message",
                content="Remember the short answer preference.",
                occurred_at="2026-05-11T00:00:00Z",
                source="chat",
                entity_ids=[],
                metadata={},
            )
        ],
        entities=[
            MemoryEntity(
                id="entity-1",
                user_id="u1",
                label="desktop app",
                entity_type="project",
                status="active",
                aliases=["app"],
                attributes={},
                confidence=0.9,
            )
        ],
    )
