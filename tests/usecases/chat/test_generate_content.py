"""Tests for generate content use case."""

from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from flow_res import Err, Ok, is_err

from app.contracts.messages.chat_events import (
    CHAT_SEARCH_REQUESTED_TOPIC,
    DISCORD_CHAT_REPLY_READY_TOPIC,
    LINE_CHAT_REPLY_READY_TOPIC,
    build_chat_search_requested_payload,
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
from app.contracts.messages.tool_use import SearchToolArguments, ToolUseRequest
from app.contracts.ports.ai_service import IAIService
from app.contracts.ports.event_bus import IEventBus
from app.domain.aggregates.chat import DiscordChat, LineChat
from app.domain.repositories import IUnitOfWork
from app.domain.value_objects.chat_type import ChatType
from app.domain.value_objects.message_content import MessageContent
from app.infrastructure.orm_mapping import ORMMappingRegistry
from app.infrastructure.orm_models.chat_orm import ChatORM
from app.usecases.chat.generate_content import (
    GenerateContentHandler,
    GenerateContentQuery,
)
from app.usecases.memory.retrieve_memory_context import RetrieveMemoryContextQuery

GEN_CONTENT_MODULE = "app.usecases.chat.generate_content"


@pytest.fixture
def mock_ai_service(mocker: Any) -> IAIService:
    service = mocker.Mock(spec=IAIService)
    service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=[
                    "Generated Content",
                    "Second Generated Content",
                ]
            )
        )
    )
    return service


@pytest.fixture
def mock_event_bus(mocker: Any) -> IEventBus:
    service = mocker.Mock(spec=IEventBus)
    service.publish = mocker.AsyncMock(return_value=None)
    return service


async def _seed_raw_chat(
    uow: IUnitOfWork,
    chat: DiscordChat | LineChat,
    *,
    user_id: str,
    role: str,
) -> None:
    """Insert a raw SQL chat row for generate_content tests."""
    session = cast(Any, getattr(uow, "_session", None))
    if session is None:
        raise RuntimeError("Unit of work session is not available")

    chat_orm = cast(ChatORM, ORMMappingRegistry.to_orm(chat))
    chat_orm.user_id = user_id
    chat_orm.role = role
    session.add(chat_orm)
    await session.flush()


@pytest.mark.anyio
async def test_generate_content_success(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test successful generation and persistence."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    send_stub = mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
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
            role="user",
        )
        await uow.commit()

    handler = GenerateContentHandler(
        mock_ai_service,
        uow,
        mock_event_bus,
    )
    result = await handler.handle(
        GenerateContentQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
        )
    )

    assert not is_err(result)
    assert result.value.contents == [
        "Generated Content",
        "Second Generated Content",
    ]
    ai_stub = cast(Any, mock_ai_service.generate_content)
    ai_stub.assert_called_once()
    assert (
        ai_stub.call_args.kwargs["system_instruction"]
        == "Memory Context:\n## Primary\nUse concise answers."
    )
    assert send_stub.await_count == 1
    mock_event_bus.publish.assert_awaited_once_with(
        DISCORD_CHAT_REPLY_READY_TOPIC,
        {
            "chat_type": "DISCORD",
            "content": "Generated Content\nSecond Generated Content",
            "contents": [
                "Generated Content",
                "Second Generated Content",
            ],
            "guild_id": "DM",
            "channel_id": "123",
        },
    )

    async with uow:
        raw_query = uow.GetRawChatLogQuery()
        raw_history = await raw_query.get_raw_chat_logs(
            "u1",
            ChatType.DISCORD,
            limit=10,
        )
        assert not is_err(raw_history)
        assert [log.role for log in raw_history.value] == [
            "user",
            "assistant",
        ]
        assert raw_history.value[-1].message_content["payload"]["text"] == (
            "Generated Content\nSecond Generated Content"
        )

        query = uow.GetChatHistoryQuery()
        history = await query.get_recent_history(ChatType.DISCORD, limit=10)
        assert not is_err(history)
        assert len(history.value) == 2
        assert (
            history.value[-1].message_content.payload["text"]
            == "Generated Content\nSecond Generated Content"
        )


@pytest.mark.anyio
async def test_generate_content_ai_failure(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test AI failure path."""
    mock_ai_service.generate_content = AsyncMock(
        return_value=Err(Exception("AI Error"))
    )
    mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
        new=AsyncMock(return_value=Ok(_memory_context_pack())),
    )
    handler = GenerateContentHandler(
        mock_ai_service,
        uow,
        mock_event_bus,
    )

    result = await handler.handle(
        GenerateContentQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
        )
    )

    assert is_err(result)


@pytest.mark.anyio
async def test_generate_content_history_failure(
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test history retrieval failure path."""
    send_stub = mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
        new=AsyncMock(),
    )
    uow = mocker.Mock(spec=IUnitOfWork)
    history_query = mocker.Mock()
    history_query.get_recent_history = mocker.AsyncMock(
        return_value=Err(Exception("history error"))
    )
    uow.GetChatHistoryQuery.return_value = history_query
    uow.__aenter__ = mocker.AsyncMock(return_value=uow)
    uow.__aexit__ = mocker.AsyncMock(return_value=None)

    handler = GenerateContentHandler(
        mock_ai_service,
        uow,
        mock_event_bus,
    )

    result = await handler.handle(
        GenerateContentQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
        )
    )

    assert is_err(result)
    ai_stub = cast(Any, mock_ai_service.generate_content)
    ai_stub.assert_not_awaited()
    send_stub.assert_not_awaited()
    publish_stub = mock_event_bus.publish
    publish_stub.assert_not_awaited()


@pytest.mark.anyio
async def test_generate_content_memory_retrieve_failure(
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test memory retrieval failure path."""
    uow = mocker.Mock(spec=IUnitOfWork)
    uow.__aenter__ = mocker.AsyncMock(return_value=uow)
    uow.__aexit__ = mocker.AsyncMock(return_value=None)
    history_query = mocker.Mock()
    history_query.get_recent_history = mocker.AsyncMock(return_value=Ok([]))
    uow.GetChatHistoryQuery.return_value = history_query
    send_stub = mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
        AsyncMock(return_value=Err(Exception("memory error"))),
    )
    handler = GenerateContentHandler(
        mock_ai_service,
        uow,
        mock_event_bus,
    )

    result = await handler.handle(
        GenerateContentQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
        )
    )

    assert is_err(result)
    ai_stub = cast(Any, mock_ai_service.generate_content)
    ai_stub.assert_not_awaited()
    send_stub.assert_awaited_once()


@pytest.mark.anyio
async def test_generate_content_line_success(
    uow: IUnitOfWork,
    mock_ai_service: IAIService,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test LINE generation and persistence."""

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )
    async with uow:
        await _seed_raw_chat(
            uow,
            LineChat.create_user_chat(
                line_user_id="u1",
                message_content=MessageContent.text("hello"),
            ),
            user_id="u1",
            role="user",
        )
        await uow.commit()

    handler = GenerateContentHandler(
        mock_ai_service,
        uow,
        mock_event_bus,
    )
    result = await handler.handle(
        GenerateContentQuery(
            prompt="hello",
            chat_id="chat-1",
            guild_id="LINE",
            channel_id="u1",
            user_id="u1",
            chat_type=ChatType.LINE,
        )
    )

    assert not is_err(result)
    assert result.value.contents == [
        "Generated Content",
        "Second Generated Content",
    ]
    mock_event_bus.publish.assert_awaited_once_with(
        LINE_CHAT_REPLY_READY_TOPIC,
        {
            "chat_type": "LINE",
            "content": "Generated Content\nSecond Generated Content",
            "contents": [
                "Generated Content",
                "Second Generated Content",
            ],
            "user_id": "u1",
        },
    )

    async with uow:
        raw_query = uow.GetRawChatLogQuery()
        raw_history = await raw_query.get_raw_chat_logs(
            "u1",
            ChatType.LINE,
            limit=10,
        )
        assert not is_err(raw_history)
        assert [log.role for log in raw_history.value] == [
            "user",
            "assistant",
        ]
        assert raw_history.value[-1].message_content["payload"]["text"] == (
            "Generated Content\nSecond Generated Content"
        )

        query = uow.GetChatHistoryQuery()
        history = await query.get_recent_history(ChatType.LINE, limit=10)
        assert not is_err(history)
        assert len(history.value) == 2
        assert (
            history.value[-1].message_content.payload["text"]
            == "Generated Content\nSecond Generated Content"
        )


@pytest.mark.anyio
async def test_generate_content_emits_search_request(
    uow: IUnitOfWork,
    mock_event_bus: Any,
    mocker: Any,
) -> None:
    """Test that tool requests publish a search event instead of a reply."""

    ai_service = mocker.Mock(spec=IAIService)
    ai_service.generate_content = mocker.AsyncMock(
        return_value=Ok(
            GeneratedContent(
                contents=[],
                tool_use_request=ToolUseRequest(
                    search_session_id="search-1",
                    tool_name="web_search",
                    arguments=SearchToolArguments(
                        query="ollama web search",
                        max_results=3,
                        source_request_id="chat-1",
                    ),
                    user_message="ちょっと検索してみます",
                ),
            )
        )
    )

    async def send_async(request: Any) -> Any:
        if isinstance(request, RetrieveMemoryContextQuery):
            return Ok(_memory_context_pack())
        raise AssertionError(f"Unexpected request: {type(request)!r}")

    mocker.patch(
        f"{GEN_CONTENT_MODULE}.Mediator.send_async",
        new=AsyncMock(side_effect=send_async),
    )

    handler = GenerateContentHandler(
        ai_service,
        uow,
        mock_event_bus,
    )
    result = await handler.handle(
        GenerateContentQuery(
            prompt="ollama web search",
            chat_id="chat-1",
            guild_id="DM",
            channel_id="123",
            user_id="u1",
            chat_type=ChatType.DISCORD,
        )
    )

    assert not is_err(result)
    assert result.value.contents == ["ちょっと検索してみます"]
    mock_event_bus.publish.assert_awaited_once_with(
        CHAT_SEARCH_REQUESTED_TOPIC,
        build_chat_search_requested_payload(
            search_session_id="search-1",
            source_request_id="chat-1",
            chat_id="chat-1",
            user_id="u1",
            chat_type="DISCORD",
            prompt="ollama web search",
            query="ollama web search",
            tool_name="web_search",
            user_message="ちょっと検索してみます",
            max_results=3,
            guild_id="DM",
            channel_id="123",
        ),
    )


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
