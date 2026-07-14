import json
import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from pprint import pformat

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from flow_med import Mediator
from flow_res import is_err
from injector import Injector
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    AsyncApiClient,
    AsyncMessagingApi,
    Configuration,
    MarkMessagesAsReadByTokenRequest,
)
from linebot.v3.webhook import WebhookParser

from app import container
from app.contracts.messages.conversation import IncomingMessage
from app.infrastructure.database import init_db
from app.presentation.conversation_flow import ConversationFlow
from app.presentation.line.line_conversation_sender import LineConversationResultSender
from app.usecases.conversation.accept_incoming_message import (
    AcceptIncomingMessageCommand,
)

logging.basicConfig(
    level=logging.DEBUG,
    format=("%(message)s"),
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_environment() -> None:
    """Load environment variables from .env files."""
    # プロジェクトルートディレクトリを取得
    # app/presentation/line/__main__.py -> app/presentation/line/ -> app/presentation/ -> app/ -> src/ -> root
    root_dir = Path(__file__).parent.parent.parent.parent.parent

    # .env.local が存在すれば優先的に読み込む（開発環境用）
    env_local = root_dir / ".env.local"
    if env_local.exists():
        load_dotenv(env_local, override=True)
        return

    # .env ファイルを読み込む（本番環境用）
    env_file = root_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)


# 環境変数を読み込む
load_environment()

# シークレット/トークンを取得
channel_secret = os.getenv("LINE_CHANNEL_SECRET")
if channel_secret is None:
    logger.error("LINE_CHANNEL_SECRET  environment variable is not set")
    sys.exit(1)
channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
if channel_access_token is None:
    logger.error("LINE_CHANNEL_ACCESS_TOKEN  environment variable is not set")
    sys.exit(1)

configuration = Configuration(access_token=channel_access_token)
parser = WebhookParser(channel_secret)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    async_api_client = AsyncApiClient(configuration)
    app.state.line_bot_api = AsyncMessagingApi(async_api_client)
    db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
    init_db(db_url, echo=True)

    injector = Injector([container.configure])
    app.state.conversation_flow = injector.get(ConversationFlow)
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers["X-Line-Signature"]

    body = await request.body()
    body = body.decode()
    raw_payload = json.loads(body)
    raw_events = raw_payload.get("events", [])

    try:
        if not parser.signature_validator.validate(body, signature):
            raise InvalidSignatureError("Invalid signature")
    except InvalidSignatureError as e:
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    line_bot_api = request.app.state.line_bot_api

    for index, raw_event in enumerate(raw_events):
        if not isinstance(raw_event, dict):
            logger.info("Skipping non-dict LINE event payload: %s", raw_event)
            continue
        raw_source = raw_event.get("source")
        if not isinstance(raw_source, dict):
            raw_source = {}

        logger.info(
            "Received LINE raw event: event_index=%s event_type=%s source_type=%s",
            index,
            raw_event.get("type"),
            raw_source.get("type"),
        )
        logger.info("LINE raw event payload: %s", pformat(raw_event))
        logger.info(
            "LINE event source inspection: event_index=%s source_type=%s source=%s",
            index,
            raw_source.get("type"),
            pformat(raw_source),
        )

        if raw_event.get("type") != "message":
            logger.info("Received non-message LINE event, skipping")
            continue

        message = raw_event.get("message")
        if not isinstance(message, dict):
            logger.info("Skipping LINE message event with invalid message payload")
            continue

        read_token = message.get("markAsReadToken")
        if isinstance(read_token, str) and read_token:
            logger.info(
                "Marking LINE message as read: event_index=%s source_type=%s",
                index,
                raw_source.get("type"),
            )
            try:
                await line_bot_api.mark_messages_as_read_by_token(
                    MarkMessagesAsReadByTokenRequest(markAsReadToken=read_token)
                )
            except Exception:
                logger.exception(
                    "Failed to mark LINE message as read; continuing message handling: "
                    "event_index=%s",
                    index,
                )
        else:
            logger.info(
                "LINE message has no markAsReadToken; continuing message handling: "
                "event_index=%s",
                index,
            )

        content = message.get("text")
        if not isinstance(content, str) or not content.strip():
            logger.info("Skipping LINE message without text content")
            continue

        user_id = raw_source.get("userId")
        if not isinstance(user_id, str) or not user_id:
            logger.info("Skipping LINE message without userId")
            continue

        source_type = raw_source.get("type")
        if source_type != "user":
            logger.info("Skipping LINE non-1:1 source: source_type=%s", source_type)
            continue
        conversation_id = user_id
        destination = user_id
        incoming = IncomingMessage(
            channel="line",
            external_conversation_id=conversation_id,
            external_participant_id=user_id,
            text=content,
            external_message_id=(
                raw_event.get("webhookEventId")
                if isinstance(raw_event.get("webhookEventId"), str)
                else None
            ),
            metadata={
                "source_type": str(source_type or "user"),
                "destination": destination,
            },
        )
        flow = getattr(request.app.state, "conversation_flow", None)
        if flow is None:
            await Mediator.send_async(AcceptIncomingMessageCommand(incoming))
            result = None
        else:
            result = await flow.process(
                incoming,
                LineConversationResultSender(app.state.line_bot_api, destination),
            )
        if result is not None and is_err(result):
            logger.error(
                "Failed to process LINE message: event_index=%s source_type=%s",
                index,
                raw_source.get("type"),
            )

    return "OK"


def start() -> None:
    import uvicorn

    uvicorn.run(
        "app.presentation.line.__main__:app",
        host="0.0.0.0",
        reload=True,
    )


if __name__ == "__main__":
    start()
