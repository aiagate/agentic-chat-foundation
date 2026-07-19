import logging
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from injector import Injector

from app.bootstrap.character_selection import resolve_active_character_id
from app.infrastructure.database import init_db, sqlalchemy_echo_enabled
from app.presentation.bot.cogs.autonomous_topic_cog import (
    AutonomousTopicCog,
    AutonomousTopicCogSettings,
)
from app.presentation.bot.cogs.discussion_cog import (
    DiscordDiscussionCog,
    DiscussionCogSettings,
)
from app.presentation.bot.cogs.dm_response_cog import DirectMessageResponseCog


class MyBot(commands.Bot):
    injector: Injector

    def __init__(self, command_prefix: str = "!") -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(
            intents=intents,
            command_prefix=command_prefix,
        )

    async def setup_hook(self) -> None:
        await self._init_database()
        await self.load_cogs()

    async def _init_database(self) -> None:
        """Initialize database connection and create tables."""
        from app import container

        db_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot.db")
        init_db(db_url, echo=sqlalchemy_echo_enabled())

        injector = Injector([container.configure])
        self.injector = injector

    async def load_cogs(self) -> None:
        await self.add_cog(DirectMessageResponseCog(self))
        await self.add_cog(
            DiscordDiscussionCog(
                self,
                DiscussionCogSettings(
                    channel_ids=_discussion_channel_ids(),
                    character_id=resolve_active_character_id(),
                    backfill_limit=_positive_int_env(
                        "DISCORD_DISCUSSION_BACKFILL_LIMIT", 50
                    ),
                    response_delay_min_seconds=_nonnegative_float_env(
                        "DISCORD_RESPONSE_DELAY_MIN_SECONDS", 2.0
                    ),
                    response_delay_max_seconds=_nonnegative_float_env(
                        "DISCORD_RESPONSE_DELAY_MAX_SECONDS", 8.0
                    ),
                ),
            )
        )
        await self.add_cog(
            AutonomousTopicCog(
                self,
                AutonomousTopicCogSettings(
                    enabled=_boolean_env("DISCORD_AUTONOMOUS_TOPICS_ENABLED", False),
                    channel_ids=_discussion_channel_ids(),
                    character_id=resolve_active_character_id(),
                    initial_delay_seconds=_nonnegative_float_env(
                        "DISCORD_AUTONOMOUS_TOPIC_INITIAL_DELAY_SECONDS", 300.0
                    ),
                    interval_seconds=float(
                        _positive_int_env(
                            "DISCORD_AUTONOMOUS_TOPIC_INTERVAL_SECONDS", 900
                        )
                    ),
                    publication_delay_min_seconds=_nonnegative_float_env(
                        "DISCORD_RESPONSE_DELAY_MIN_SECONDS", 2.0
                    ),
                    publication_delay_max_seconds=_nonnegative_float_env(
                        "DISCORD_RESPONSE_DELAY_MAX_SECONDS", 8.0
                    ),
                ),
            )
        )

    async def close(self) -> None:
        await super().close()


def load_environment() -> None:
    """Load environment variables from .env files."""
    # プロジェクトルートディレクトリを取得
    # app/presentation/bot/__main__.py -> app/presentation/bot/ -> app/presentation/ -> app/ -> src/ -> root
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


def main() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format=(
            "[ %(levelname)-8s] %(asctime)s | %(name)-16s %(funcName)-16s| %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 環境変数を読み込む
    load_environment()

    # Bot トークンを取得
    token = os.getenv("DISCORD_BOT_TOKEN")
    if token is None:
        logging.error("DISCORD_BOT_TOKEN environment variable is not set")
        logging.error("Please set it in .env.local or .env file")
        sys.exit(1)

    bot = MyBot()
    bot.run(token)


def _discussion_channel_ids() -> frozenset[int]:
    raw_value = os.getenv("DISCORD_DISCUSSION_CHANNEL_IDS", "")
    channel_ids: set[int] = set()
    for item in raw_value.split(","):
        normalized = item.strip()
        if not normalized:
            continue
        try:
            channel_ids.add(int(normalized))
        except ValueError:
            logging.warning(
                "Ignoring invalid Discord discussion channel id: %r", normalized
            )
    return frozenset(channel_ids)


def _positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def _nonnegative_float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value >= 0 else default


def _boolean_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
