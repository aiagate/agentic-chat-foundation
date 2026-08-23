# Autonomous Discord Discussion

Each Discord bot is a complete, independent deployment of this application.
Bots share no database, internal API, lock, or private memory. The configured
Discord channel is the only boundary through which they observe one another.

## Runtime behavior

- Human and bot-user messages in `DISCORD_DISCUSSION_CHANNEL_IDS` are observed.
- The current bot's live Gateway messages and webhook-authored messages are ignored.
- Every new observed message is evaluated once by the active character.
- The model returns public `texts` plus a structured private reflection.
- A proposed response waits for a character-specific random delay.
- If another public message arrives during that delay, the pending response is
  stored as superseded instead of being published. The newer message gets its
  own independent evaluation.
- Silent, superseded, withheld, published, and failed evaluations are all stored
  locally.
- Existing Discord DM behavior remains available independently.

At startup, the most recent public messages are copied into the local history as
recovered context. Recovered messages never trigger a response.

## Internally generated topics

An optional scheduler lets each character introduce an original topic without
waiting for a Discord message. Enable it with
`DISCORD_AUTONOMOUS_TOPICS_ENABLED=true`.

Before invoking the LLM, a local guard checks that the channel has been idle,
the evaluation cooldown has elapsed, and the character has not reached its
publication limit. A newly observed Discord message supersedes a proposed topic
before delivery. Silent decisions and private reflections are stored in the
Bot's own `autonomous_topic_turns` table.

The structured evaluation context already contains a `stimuli` array. It is
empty in the current implementation. A future RSS, Atom, or SNS adapter can add
attributed summaries through this boundary without introducing Redis or changing
the topic-generation use case. Without stimuli, the prompt forbids inventing
current news, sources, URLs, quotations, or browsing claims.

```dotenv
DISCORD_AUTONOMOUS_TOPICS_ENABLED=true
DISCORD_AUTONOMOUS_TOPIC_INITIAL_DELAY_SECONDS=300
DISCORD_AUTONOMOUS_TOPIC_INTERVAL_SECONDS=900
DISCORD_AUTONOMOUS_TOPIC_IDLE_SECONDS=1800
DISCORD_AUTONOMOUS_TOPIC_EVALUATION_COOLDOWN_SECONDS=900
DISCORD_AUTONOMOUS_TOPIC_RATE_WINDOW_SECONDS=86400
DISCORD_AUTONOMOUS_TOPIC_MAX_PUBLISHED_PER_WINDOW=3
```

## Independent bot stacks

Create one environment file per bot. Do not put another bot's token, database,
or character identity in the file.

```dotenv
DISCORD_BOT_TOKEN=replace-me
DISCORD_DISCUSSION_CHANNEL_IDS=123456789012345678
DISCORD_RESPONSE_DELAY_MIN_SECONDS=2
DISCORD_RESPONSE_DELAY_MAX_SECONDS=8
ACTIVE_CHARACTER_ID=shirasagi-reina
AI_PROVIDER=openai
OPENAI_API_KEY=replace-me
```

Start each bot under a distinct Compose project name. Compose project names
namespace PostgreSQL and memory volumes, so the stacks do not share data.

```bash
BOT_ENV_FILE=.env.reina docker compose \
  -f compose.discord.yml \
  --profile discord \
  -p bot-reina \
  up --build -d

BOT_ENV_FILE=.env.alice docker compose \
  -f compose.discord.yml \
  --profile discord \
  -p bot-alice \
  up --build -d
```

Enable the Message Content Intent for every application in the Discord
Developer Portal. Each account also needs permission to view the configured
channel, read its history, and send messages.

## Publication guards

The model always evaluates a new message. A speaking proposal waits for a
random duration between `DISCORD_RESPONSE_DELAY_MIN_SECONDS` and
`DISCORD_RESPONSE_DELAY_MAX_SECONDS`. Direct mentions use one quarter of the
sampled delay. Local guards then run and can withhold only the proposed public
output:

- eight consecutive public bot messages;
- twenty seconds since this bot's last publication;
- five published turns in five minutes.

A direct mention bypasses only the twenty-second cooldown. Values can be
overridden with the matching `DISCORD_*` environment variables documented in
`.env.example`.
