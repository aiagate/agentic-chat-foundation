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
from app.contracts.messages.generated_content import GeneratedContent
from app.contracts.messages.memory_context import (
    MemoryContextFrame,
    MemoryContextPack,
    MemoryEntity,
    MemoryFrameSection,
    MemoryProfile,
    MemorySource,
    MemoryTimelineEntry,
)
from app.contracts.messages.retrieved_context import (
    RetrievedContext,
    RetrievedContextItem,
)
from app.contracts.messages.tool_contracts import ToolCall
from app.contracts.ports.agent_profile_service import IAgentProfileService
from app.contracts.ports.ai_service import AIServiceError, IAIService
from app.contracts.ports.event_bus import IEventBus
from app.contracts.ports.retrieved_context_store import (
    IRetrievedContextStore,
    RetrievedContextStoreError,
)
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.infrastructure.services.tool_catalog import StaticToolCatalog
from app.infrastructure.stores.retrieved_context_store import (
    InMemoryRetrievedContextStore,
)
from app.infrastructure.stores.tool_call_store import InMemoryToolCallStore
from app.usecases.agent.route_tool_calls import (
    RouteToolCallsCommand,
    RouteToolCallsHandler,
)
from app.usecases.agent.run_agent_turn import (
    RunAgentTurnHandler,
    RunAgentTurnQuery,
)
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery

RUN_AGENT_MODULE = "app.usecases.agent.run_agent_turn"
CHARACTER_ID = "shirasagi-reina"
RELATIONSHIP_ENTITY_ID = f"relationship:{CHARACTER_ID}"


class _FakeAgentProfileService(IAgentProfileService):
    def ensure_agent_profile_bundle(self) -> None:
        return None

    def load_agent_profile_bundle(self) -> AgentProfileBundle:
        return AGENT_PROFILE_BUNDLE


AGENT_PROFILE_BUNDLE = AgentProfileBundle(
    profile=MemoryProfile(
        user_id="ai",
        display_name="Jon Due",
        summary="A test host persona.",
        traits=["calm"],
        preferences=["quiet places"],
    ),
    character=CharacterDefinition(
        character_id=CHARACTER_ID,
        display_name="Jon Due",
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
    communication_style=("Speak naturally in English",),
    known_constraints=("Do not mention being an AI",),
    atmosphere=("A quiet evening with city lights in the distance.",),
    behavior=("Maintain a composed, respectful tone.",),
    relationship_entity_id=RELATIONSHIP_ENTITY_ID,
    relationship_entity_label="Relationship with Jon Due",
    relationship_entity_type="relationship",
    relationship_tag="agent-growth",
    relationship=("Minimal self-disclosure",),
    fallback=("Choose something seasonal and quiet",),
    memory_reading_rules=("Test bundle is read from memory files.",),
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
def mock_retrieved_context_store(mocker: Any) -> IRetrievedContextStore:
    store = mocker.Mock(spec=IRetrievedContextStore)
    store.get = mocker.AsyncMock(
        return_value=Ok(
            RetrievedContext(
                tool_call_id="tool-1",
                character_id=CHARACTER_ID,
                query="ollama web search",
                tool_name="web_search",
                items=[
                    RetrievedContextItem(
                        title="Result",
                        url="https://example.com",
                        snippet="Example snippet",
                    )
                ],
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test the happy path for a non-tool response."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            assert request.prompt == "hello"
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
        mock_retrieved_context_store,
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
        statement = (
            select(ChatORM)
            .where(
                ChatORM.type == ChatType.DISCORD.to_primitive(),
                ChatORM.user_id == "u1",
                ChatORM.role == "assistant",
            )
            .order_by(desc(ChatORM.created_at), desc(ChatORM.id))
            .limit(1)
        )
        saved_result = await session.execute(statement)
        saved_chat = saved_result.scalars().one()
        assert saved_chat.message_content["payload"]["texts"] == [
            "Generated Content"
        ]
    ai_stub: Any = mock_ai_service.generate_content
    ai_stub.assert_awaited_once()
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert {tool.name for tool in tool_definitions} == {
        "web_search",
        "memory.search",
        "memory.write_candidate",
        "discord.reply",
        "discord.post_channel",
    }
    retrieved_store_mock: Any = mock_retrieved_context_store.get
    retrieved_store_mock.assert_not_awaited()
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that the handler can recover the prompt from persisted chat data."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            assert request.prompt == "hello"
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
        mock_retrieved_context_store,
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that the handler isolates the current session before prompting."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            assert [item.content for item in request.history] == ["today dinner"]
            assert request.prompt == "today dinner"
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
                message_content=MessageContent.text("yesterday dinner"),
            ),
            user_id="u1",
            created_at=datetime(2026, 6, 1, 18, 0, tzinfo=UTC),
        )
        await _seed_raw_chat(
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
        await uow.commit()

    handler = RunAgentTurnHandler(
        mock_ai_service,
        mock_retrieved_context_store,
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that LINE chats only receive LINE reply tools."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            assert request.prompt == "hello"
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
        mock_retrieved_context_store,
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
        "memory.search",
        "memory.write_candidate",
        "line.reply",
    }


@pytest.mark.anyio
async def test_run_agent_turn_includes_retrieved_context(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that retrieved context is appended to the system instruction."""

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
        mock_retrieved_context_store,
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
    system_instruction = ai_stub.call_args.kwargs["system_instruction"]
    assert "Memory Context" in system_instruction
    assert "Identity:" in system_instruction
    assert "Do not mention that you are an AI" in system_instruction
    assert "## Retrieved Context" in system_instruction
    assert "Web search results are already provided above." in system_instruction
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert all(tool.name != "web_search" for tool in tool_definitions)
    retrieved_store_mock: Any = mock_retrieved_context_store.get
    retrieved_store_mock.assert_awaited_once_with(
        "tool-1",
        character_id=CHARACTER_ID,
    )


@pytest.mark.anyio
async def test_run_agent_turn_prefers_direct_answering_in_system_instruction(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mock_agent_profile_service: IAgentProfileService,
    mock_retrieved_context_store: IRetrievedContextStore,
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
        mock_retrieved_context_store,
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
async def test_in_memory_retrieved_context_store_returns_copy() -> None:
    """Test that the in-memory retrieved context store returns a copy."""

    store = InMemoryRetrievedContextStore()
    saved = RetrievedContext(
        tool_call_id="tool-1",
        character_id=CHARACTER_ID,
        query="ollama web search",
        tool_name="web_search",
        items=[
            RetrievedContextItem(
                title="Result",
                url="https://example.com",
                snippet="Example snippet",
            )
        ],
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that missing retrieved context does not suppress the final reply."""

    mock_retrieved_context_store.get = AsyncMock(
        return_value=Err(RetrievedContextStoreError("Retrieved context not found"))
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
        mock_retrieved_context_store,
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
    retrieved_store_mock: Any = mock_retrieved_context_store.get
    retrieved_store_mock.assert_awaited_once_with(
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    mocker: Any,
) -> None:
    """Test that tool failure notes are appended to the system instruction."""

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
        mock_retrieved_context_store,
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
    assert (
        "Tool failure context: web_search failed with error: HTTP 500."
        in (ai_stub.call_args.kwargs["system_instruction"])
    )
    tool_definitions = ai_stub.call_args.kwargs["tool_definitions"]
    assert all(tool.name != "web_search" for tool in tool_definitions)


@pytest.mark.anyio
async def test_run_agent_turn_preserves_ai_service_error_message(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_retrieved_context_store: IRetrievedContextStore,
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
        mock_retrieved_context_store,
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
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Test that canonical tool calls are routed through the generic path."""

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
                        user_message="ちょっと検索してみます",
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
        mock_retrieved_context_store,
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
    assert result.value.contents == ["ちょっと検索してみます"]
    publish_mock = mock_event_bus.publish
    publish_mock.assert_awaited()
    topic, payload = publish_mock.await_args.args
    assert topic == CHAT_TOOL_REQUESTED_TOPIC
    assert payload["tool_name"] == "web_search"
    assert payload["character_id"] == CHARACTER_ID
    assert "arguments" not in payload
    assert "user_message" not in payload
    stored = await tool_call_store.get(
        payload["tool_call_id"],
        character_id=CHARACTER_ID,
    )
    assert not is_err(stored)
    assert stored.value.character_id == CHARACTER_ID
    assert stored.value.user_message == "ちょっと検索してみます"


@pytest.mark.anyio
async def test_run_agent_turn_routes_memory_search_tool_calls(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Test that memory search tool calls flow through the generic runtime."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=[],
                tool_calls=[
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="memory.search",
                        arguments={
                            "query": "memory lookup",
                        },
                        user_message="記憶を確認します",
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
        mock_retrieved_context_store,
        mock_tool_catalog,
        uow,
        mock_event_bus,
        agent_profile_service=mock_agent_profile_service,
    )
    result = await handler.handle(
        RunAgentTurnQuery(
            prompt="memory lookup",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
            character_id=CHARACTER_ID,
        )
    )

    assert not is_err(result)
    assert result.value.contents == ["記憶を確認します"]
    publish_mock = mock_event_bus.publish
    publish_mock.assert_awaited_once()
    topic, payload = publish_mock.await_args.args
    assert topic == CHAT_TOOL_REQUESTED_TOPIC
    assert payload["tool_name"] == "memory.search"
    assert "arguments" not in payload
    assert "user_message" not in payload
    stored = await tool_call_store.get(
        payload["tool_call_id"],
        character_id=CHARACTER_ID,
    )
    assert not is_err(stored)
    assert stored.value.arguments == {"query": "memory lookup"}


@pytest.mark.anyio
async def test_run_agent_turn_routes_only_one_retrieval_tool_call_per_turn(
    uow: IUnitOfWork,
    mock_agent_profile_service: IAgentProfileService,
    mock_event_bus: Any,
    mock_retrieved_context_store: IRetrievedContextStore,
    mock_tool_catalog: StaticToolCatalog,
    tool_call_store: InMemoryToolCallStore,
    mocker: Any,
) -> None:
    """Test that only one retrieved-context-producing tool is routed per turn."""

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
                        user_message="ちょっと検索してみます",
                    ),
                    ToolCall(
                        character_id=CHARACTER_ID,
                        tool_name="memory.search",
                        arguments={
                            "query": "memory lookup",
                        },
                        user_message="記憶を確認します",
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
        mock_retrieved_context_store,
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
    assert result.value.contents == ["ちょっと検索してみます"]
    publish_mock = mock_event_bus.publish
    assert publish_mock.await_count == 1
    topic, payload = publish_mock.await_args.args
    assert topic == CHAT_TOOL_REQUESTED_TOPIC
    assert payload["tool_name"] == "web_search"


def _memory_context_pack() -> MemoryContextPack:
    return MemoryContextPack(
        user_id="u1",
        assembled_context="Memory Context:\n## Primary\nUse concise answers.",
        context_frame=MemoryContextFrame(
            assembled_context="Memory Context:\n## Primary\nUse concise answers.",
            sections=[
                MemoryFrameSection(
                    name="primary",
                    content="Use concise answers.",
                    sources=[
                        MemorySource(
                            id="profile:u1",
                            memory_type="profile",
                            title="Dorothy",
                            user_id="u1",
                            reference="profile:u1",
                        )
                    ],
                )
            ],
        ),
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
