"""
Discord bot service for Lyra Wiskerbyte.

Provides slash commands (/ask, /credits, /link) and DM support.
Started as an asyncio task within the FastAPI lifespan.
"""

import asyncio
import logging
import os
import time
from math import ceil

import discord
from discord import app_commands

from api.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID", "932330696956063765")

# Per-user rate limiters for slash commands
_ask_limiters: dict[str, RateLimiter] = {}
_credits_limiter = RateLimiter(max_requests=6, window_seconds=60, namespace="bot_credits")
_link_limiter = RateLimiter(max_requests=1, window_seconds=60, namespace="bot_link")

# Minimum Discord account age (7 days) — derived from snowflake
_MIN_ACCOUNT_AGE_SECONDS = 7 * 24 * 3600
_DISCORD_EPOCH = 1420070400000  # ms


def _account_age_seconds(discord_id: str) -> float:
    """Calculate account age from Discord snowflake ID."""
    snowflake = int(discord_id)
    created_ms = ((snowflake >> 22) + _DISCORD_EPOCH)
    return time.time() - (created_ms / 1000)


def _get_ask_limiter(discord_id: str) -> RateLimiter:
    """Get or create a per-user rate limiter for /ask, tier-aware."""
    from api.routes.auth import TIER_RATE_LIMITS, get_user_tier
    from pipeline.database import DiscordUser, get_session

    with get_session() as session:
        user = session.query(DiscordUser).filter(
            DiscordUser.discord_id == discord_id,
        ).first()
        if not user:
            max_req = TIER_RATE_LIMITS["free"]
        else:
            tier = get_user_tier(user.roles or [])
            max_req = TIER_RATE_LIMITS.get(tier, 10)

    key = f"{discord_id}:{max_req}"
    if key not in _ask_limiters:
        # Evict oldest entries when the cache exceeds 1000 users
        if len(_ask_limiters) >= 1000:
            oldest_key = next(iter(_ask_limiters))
            del _ask_limiters[oldest_key]
        _ask_limiters[key] = RateLimiter(
            max_requests=max_req, window_seconds=3600, namespace=f"bot_ask_{discord_id}",
        )
    return _ask_limiters[key]


# Anti-exploit: same low-credit cap as web
LOW_CREDIT_THRESHOLD = 20


def _truncate_response(text: str, limit: int = 1900) -> str:
    """Truncate response to fit Discord's 2000-char message limit."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n*...response truncated*"


async def _handle_ask(discord_id: str, question: str) -> str:
    """Core ask logic shared by /ask command and DM handler.

    Returns the response text. Raises ValueError with user-facing message on error.
    """
    from pipeline.database import DiscordUser, TokenUsageLog, get_session

    # Account age check
    if _account_age_seconds(discord_id) < _MIN_ACCOUNT_AGE_SECONDS:
        raise ValueError("Your Discord account must be at least 7 days old to use Lyra.")

    # Look up user
    with get_session() as session:
        user = session.query(DiscordUser).filter(
            DiscordUser.discord_id == discord_id,
        ).first()
        if not user:
            raise ValueError(
                "You need to sign in at [ancientnerds.com](https://ancientnerds.com/account.html) first."
            )

        is_unlimited = user.is_unlimited
        user_id = user.id

        if not is_unlimited and user.credits <= 0:
            raise ValueError("No credits remaining. Visit ancientnerds.com to check your balance.")

        # Pre-deduct 1 credit deposit (non-unlimited users)
        if not is_unlimited:
            from sqlalchemy import update
            session.execute(
                update(DiscordUser)
                .where(DiscordUser.id == user_id)
                .values(credits=DiscordUser.credits - 1)
            )
            session.commit()

    # Run the agent (non-streaming, collect full response)
    from api.services.lyra_agent import run_agent_stream

    full_text = ""
    metadata = {}
    try:
        async for chunk in run_agent_stream(
            message=question,
            images=None,
            history=None,
            context_type="global",
            context_id=None,
            context_year=None,
        ):
            event_type = chunk.get("type", "token")
            if event_type == "token":
                full_text += chunk.get("content", "")
            elif event_type == "done":
                metadata = chunk.get("metadata", {})
    except Exception:
        # Refund deposit on error
        if not is_unlimited:
            with get_session() as session:
                from sqlalchemy import update
                session.execute(
                    update(DiscordUser)
                    .where(DiscordUser.id == user_id)
                    .values(credits=DiscordUser.credits + 1)
                )
                session.commit()
        raise

    # Reconcile credits
    if not is_unlimited:
        tokens = metadata.get("tokens", {})
        input_tokens = tokens.get("input", 0)
        output_tokens = tokens.get("output", 0)
        voyage_tokens = tokens.get("voyage", 0)
        credits_used = max(1, ceil((input_tokens + output_tokens) / 100))
        additional = credits_used - 1  # 1 already deducted as deposit

        with get_session() as session:
            from sqlalchemy import update
            if additional > 0:
                session.execute(
                    update(DiscordUser)
                    .where(DiscordUser.id == user_id)
                    .values(credits=DiscordUser.credits - additional)
                )
            session.add(TokenUsageLog(
                user_id=user_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                voyage_tokens=voyage_tokens,
                credits_used=credits_used,
            ))
            session.commit()

    return full_text or "I wasn't able to generate a response. Please try again."


class LyraBot(discord.Client):
    """Discord bot client for Lyra Wiskerbyte."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Register slash commands on startup."""
        guild = discord.Object(id=int(DISCORD_GUILD_ID))
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info(f"Discord bot slash commands synced to guild {DISCORD_GUILD_ID}")

    async def on_ready(self):
        logger.info(f"Discord bot ready as {self.user} (ID: {self.user.id})")

    async def on_message(self, message: discord.Message):
        """Handle DMs to the bot."""
        # Ignore non-DM messages and bot's own messages
        if not isinstance(message.channel, discord.DMChannel):
            return
        if message.author == self.user:
            return
        if message.author.bot:
            return

        discord_id = str(message.author.id)

        # Rate limit
        limiter = _get_ask_limiter(discord_id)
        if not limiter.check(discord_id):
            await message.reply("You're sending messages too quickly. Please wait a bit.")
            return

        async with message.channel.typing():
            try:
                response = await _handle_ask(discord_id, message.content)
                await message.reply(_truncate_response(response))
            except ValueError as e:
                await message.reply(str(e))
            except Exception:
                logger.exception(f"DM handler error for {discord_id}")
                await message.reply("Something went wrong. Please try again later.")


# Global bot instance (created on demand)
_bot: LyraBot | None = None


def _get_bot() -> LyraBot:
    """Get or create the bot instance and register commands."""
    global _bot
    if _bot is not None:
        return _bot

    _bot = LyraBot()

    @_bot.tree.command(name="ask", description="Ask Lyra about archaeology")
    @app_commands.describe(question="Your question for Lyra")
    @app_commands.checks.cooldown(1, 30.0)
    async def ask_command(interaction: discord.Interaction, question: str):
        discord_id = str(interaction.user.id)

        limiter = _get_ask_limiter(discord_id)
        if not limiter.check(discord_id):
            await interaction.response.send_message(
                "You're asking too quickly. Please wait a bit.", ephemeral=True,
            )
            return

        await interaction.response.defer(thinking=True)

        try:
            response = await _handle_ask(discord_id, question)
            await interaction.followup.send(_truncate_response(response))
        except ValueError as e:
            await interaction.followup.send(str(e), ephemeral=True)
        except Exception:
            logger.exception(f"/ask error for {discord_id}")
            await interaction.followup.send(
                "Something went wrong. Please try again later.", ephemeral=True,
            )

    @ask_command.error
    async def ask_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s before using /ask again.",
                ephemeral=True,
            )
        else:
            logger.error(f"/ask command error: {error}")

    @_bot.tree.command(name="credits", description="Check your Lyra credit balance")
    @app_commands.checks.cooldown(1, 10.0)
    async def credits_command(interaction: discord.Interaction):
        from api.routes.auth import get_user_tier
        from pipeline.database import DiscordUser, get_session

        discord_id = str(interaction.user.id)

        with get_session() as session:
            user = session.query(DiscordUser).filter(
                DiscordUser.discord_id == discord_id,
            ).first()

        if not user:
            await interaction.response.send_message(
                "You haven't signed in yet. Visit [ancientnerds.com](https://ancientnerds.com/account.html) to connect your account.",
                ephemeral=True,
            )
            return

        tier = get_user_tier(user.roles or [])
        tier_display = tier.replace("_", " ").title()

        embed = discord.Embed(
            title="Lyra Credits",
            color=0xC02023,
        )
        embed.add_field(
            name="Balance",
            value="Unlimited" if user.is_unlimited else f"{user.credits:,}",
            inline=True,
        )
        embed.add_field(name="Tier", value=tier_display, inline=True)
        embed.set_footer(text="ancientnerds.com")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @credits_command.error
    async def credits_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s before checking credits again.",
                ephemeral=True,
            )
        else:
            logger.error(f"/credits command error: {error}")

    @_bot.tree.command(name="link", description="Link your Discord to your Ancient Nerds account")
    @app_commands.checks.cooldown(1, 60.0)
    async def link_command(interaction: discord.Interaction):
        await interaction.response.send_message(
            "Sign in at **[ancientnerds.com/account](https://ancientnerds.com/account.html)** to link your Discord account and start chatting with Lyra!",
            ephemeral=True,
        )

    @link_command.error
    async def link_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.", ephemeral=True,
            )
        else:
            logger.error(f"/link command error: {error}")

    return _bot


async def start_bot() -> None:
    """Start the Discord bot. Call from FastAPI lifespan."""
    if not DISCORD_BOT_TOKEN:
        logger.info("DISCORD_BOT_TOKEN not set, skipping Discord bot startup")
        return

    bot = _get_bot()
    try:
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception:
        logger.exception("Discord bot failed to start")


async def stop_bot() -> None:
    """Gracefully shut down the Discord bot."""
    global _bot
    if _bot is not None and not _bot.is_closed():
        await _bot.close()
        _bot = None
        logger.info("Discord bot shut down")
