"""
Discord bot service for Lyra Whiskerbyte.

Provides slash commands (/ask, /credits, /link) and DM support.
Started as an asyncio task within the FastAPI lifespan.
"""

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

_credits_limiter = RateLimiter(max_requests=6, window_seconds=60, namespace="bot_credits")
_link_limiter = RateLimiter(max_requests=1, window_seconds=60, namespace="bot_link")

# Minimum Discord account age (7 days) — derived from snowflake
_MIN_ACCOUNT_AGE_SECONDS = 7 * 24 * 3600
_DISCORD_EPOCH = 1420070400000  # ms

# Anti-exploit: same low-credit cap as web
LOW_CREDIT_THRESHOLD = 20
LOW_CREDIT_MAX_HISTORY = 5


def _account_age_seconds(discord_id: str) -> float:
    """Calculate account age from Discord snowflake ID."""
    snowflake = int(discord_id)
    created_ms = ((snowflake >> 22) + _DISCORD_EPOCH)
    return time.time() - (created_ms / 1000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_response(text: str, limit: int = 1900) -> list[str]:
    """Split text into chunks that fit Discord's message limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        # Find split point: prefer paragraph, then newline, then space
        split = text.rfind("\n\n", 0, limit)
        if split == -1:
            split = text.rfind("\n", 0, limit)
        if split == -1:
            split = text.rfind(" ", 0, limit)
        if split == -1:
            split = limit
        chunks.append(text[:split])
        text = text[split:].lstrip()
    return chunks


async def _build_history(
    channel: discord.abc.Messageable,
    current_msg: discord.Message | None = None,
    limit: int = 20,
) -> list[dict]:
    """Build conversation history from channel messages."""
    history = []
    async for msg in channel.history(limit=limit + 1, before=current_msg):
        role = "assistant" if msg.author.bot else "user"
        if msg.content:
            history.append({"role": role, "content": msg.content})
    history.reverse()  # oldest first
    return history



def _build_sites_embed(sites: list[dict]) -> discord.Embed:
    """Build a compact embed showing referenced archaeological sites."""
    embed = discord.Embed(title="Referenced Sites", color=0xC02023)
    lines = []
    for s in sites[:10]:  # cap at 10 to avoid embed limits
        name = s.get("name", "Unknown")
        period = s.get("period_name", "")
        country = s.get("country", "")
        parts = [p for p in (period, country) if p]
        detail = f" ({', '.join(parts)})" if parts else ""
        lines.append(f"**{name}**{detail}")
    embed.description = "\n".join(lines)
    embed.set_footer(text="ancientnerds.com")
    return embed


# ---------------------------------------------------------------------------
# Core ask logic
# ---------------------------------------------------------------------------

async def _handle_ask(
    discord_id: str,
    question: str,
    *,
    history: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    """Core ask logic shared by /ask command and DM handler.

    Returns (response_text, sites). Raises ValueError with user-facing message on error.
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
        deposit_remaining = user.credits

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
            deposit_remaining = user.credits - 1

    # Anti-exploit: limit history length for low-credit users
    if history and deposit_remaining < LOW_CREDIT_THRESHOLD and len(history) > LOW_CREDIT_MAX_HISTORY:
        history = history[-LOW_CREDIT_MAX_HISTORY:]

    # Run the agent (non-streaming, collect full response)
    from api.services.lyra_agent import run_agent_stream

    full_text = ""
    metadata = {}
    all_sites: list[dict] = []
    try:
        async for chunk in run_agent_stream(
            message=question,
            images=None,
            history=history,
            context_type="global",
            context_id=None,
            context_year=None,
        ):
            event_type = chunk.get("type", "token")
            if event_type == "token":
                full_text += chunk.get("content", "")
            elif event_type == "sites":
                all_sites.extend(chunk.get("sites", []))
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

    response_text = full_text or "I wasn't able to generate a response. Please try again."
    return response_text, all_sites


async def _send_response(
    channel: discord.abc.Messageable,
    text: str,
    sites: list[dict],
) -> None:
    """Send a (possibly multi-part) response and optional sites embed to a channel."""
    for chunk in _split_response(text):
        await channel.send(chunk)
    if sites:
        await channel.send(embed=_build_sites_embed(sites))


# ---------------------------------------------------------------------------
# Bot class
# ---------------------------------------------------------------------------

class LyraBot(discord.Client):
    """Discord bot client for Lyra Whiskerbyte."""

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
        print(f"[DISCORD] Slash commands synced to guild {DISCORD_GUILD_ID}", flush=True)

    async def on_ready(self):
        print(f"[DISCORD] Bot ready as {self.user} (ID: {self.user.id})", flush=True)

    async def on_message(self, message: discord.Message):
        """Handle DMs and thread follow-ups."""
        if message.author == self.user or message.author.bot:
            return

        # --- Thread follow-ups (threads created by /ask) ---
        if isinstance(message.channel, discord.Thread):
            if message.channel.owner_id != self.user.id:
                return
            await self._handle_thread_message(message)
            return

        # --- DMs ---
        if isinstance(message.channel, discord.DMChannel):
            await self._handle_dm_message(message)
            return

    async def _handle_dm_message(self, message: discord.Message):
        """Handle a DM with conversation history."""
        discord_id = str(message.author.id)

        async with message.channel.typing():
            try:
                history = await _build_history(message.channel, current_msg=message)
                text, sites = await _handle_ask(
                    discord_id, message.content, history=history,
                )
                for chunk in _split_response(text):
                    await message.reply(chunk)
                if sites:
                    await message.reply(embed=_build_sites_embed(sites))
            except ValueError as e:
                await message.reply(str(e))
            except Exception:
                logger.exception(f"DM handler error for {discord_id}")
                await message.reply("Something went wrong. Please try again later.")

    async def _handle_thread_message(self, message: discord.Message):
        """Handle a follow-up message in a bot-created thread."""
        discord_id = str(message.author.id)

        async with message.channel.typing():
            try:
                history = await _build_history(message.channel, current_msg=message)
                text, sites = await _handle_ask(
                    discord_id, message.content, history=history,
                )
                await _send_response(message.channel, text, sites)
            except ValueError as e:
                await message.channel.send(str(e))
            except Exception:
                logger.exception(f"Thread handler error for {discord_id}")
                await message.channel.send("Something went wrong. Please try again later.")


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
    async def ask_command(interaction: discord.Interaction, question: str):
        discord_id = str(interaction.user.id)

        await interaction.response.defer(thinking=True)

        try:
            text, sites = await _handle_ask(discord_id, question)

            # Try to create a thread for the conversation
            display_name = interaction.user.display_name
            followup_msg = await interaction.followup.send(
                f"**{display_name}** asked: {question[:200]}", wait=True,
            )
            try:
                thread_name = f"Lyra | {question[:90]}"
                thread = await interaction.channel.create_thread(
                    name=thread_name,
                    message=discord.Object(id=followup_msg.id),
                )
                await _send_response(thread, text, sites)
            except discord.Forbidden:
                # No thread permission — send response directly in channel
                for chunk in _split_response(text):
                    await interaction.followup.send(chunk)
                if sites:
                    await interaction.followup.send(embed=_build_sites_embed(sites))
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
        try:
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
                # Read all values while session is open
                roles = user.roles or []
                credits = user.credits
                is_unlimited = user.is_unlimited

            tier = get_user_tier(roles)
            tier_names = {
                "scholar": "Scholar (Patron)",
                "archaeologist": "Archaeologist (Patron)",
                "explorer": "Explorer (Patron)",
                "founder": "Founder",
                "team": "Team",
                "researcher": "Researcher",
                "og_nerd": "OG Nerd",
                "free": "Free",
            }
            tier_display = tier_names.get(tier, tier.replace("_", " ").title())

            embed = discord.Embed(
                title="Lyra Credits",
                color=0xC02023,
            )
            embed.add_field(
                name="Balance",
                value="Unlimited" if is_unlimited else f"{credits:,}",
                inline=True,
            )
            embed.add_field(name="Tier", value=tier_display, inline=True)
            if tier != "scholar":
                embed.add_field(
                    name="Upgrade",
                    value="[Subscribe on Patreon](https://www.patreon.com/join/AncientNerds)",
                    inline=False,
                )
            embed.set_footer(text="ancientnerds.com")

            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"[DISCORD] /credits error: {e}", flush=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Something went wrong checking credits.", ephemeral=True,
                )

    @credits_command.error
    async def credits_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s before checking credits again.",
                ephemeral=True,
            )
        else:
            print(f"[DISCORD] /credits command error: {error}", flush=True)
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "Something went wrong.", ephemeral=True,
                )

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

    from api.cardgame import register_commands
    register_commands(_bot)

    return _bot


async def start_bot() -> None:
    """Start the Discord bot. Call from FastAPI lifespan."""
    if not DISCORD_BOT_TOKEN:
        print("[DISCORD] No token set, skipping bot startup", flush=True)
        return

    bot = _get_bot()
    try:
        print("[DISCORD] Starting bot...", flush=True)
        await bot.start(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"[DISCORD] Bot failed to start: {e}", flush=True)
        logger.exception("Discord bot failed to start")


async def stop_bot() -> None:
    """Gracefully shut down the Discord bot."""
    global _bot
    if _bot is not None and not _bot.is_closed():
        await _bot.close()
        _bot = None
        logger.info("Discord bot shut down")
