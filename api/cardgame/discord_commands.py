"""Discord slash commands for the card game.

Exports register_commands(bot) — called once from discord_bot._get_bot().
"""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

import discord
from discord import app_commands

from api.cardgame.constants import (
    BATTLE_MAX_STAKE,
    PACK_PRICES,
    RARITY_COLORS,
    RARITY_NAMES,
    TYPE_ADVANTAGE_BONUS,
)
from api.services.lyra_tools import _escape_ilike
from api.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_pack_limiter = RateLimiter(max_requests=5, window_seconds=60, namespace="discord_packs")
_daily_limiter = RateLimiter(max_requests=2, window_seconds=60, namespace="discord_daily")

# Unicode stat bar characters
_BAR_FULL = "\u2588"  # Full block
_BAR_EMPTY = "\u2591"  # Light shade


def _stat_bar(value: int, max_val: int = 10) -> str:
    """Render a stat bar: [########--] 8/10"""
    filled = min(value, max_val)
    empty = max_val - filled
    return f"`{_BAR_FULL * filled}{_BAR_EMPTY * empty}` **{value}**/{max_val}"


def _get_user_or_none(discord_id: str):
    """Look up DiscordUser by discord_id, return None if not found."""
    from pipeline.database import DiscordUser, get_session

    with get_session() as session:
        user = (
            session.query(DiscordUser)
            .filter(
                DiscordUser.discord_id == discord_id,
            )
            .first()
        )
        if user:
            session.expunge(user)
        return user


def register_commands(bot: discord.Client) -> None:
    """Register all card game slash commands on the bot's command tree."""

    # -------------------------------------------------------------------
    # /card <name> — View a single card
    # -------------------------------------------------------------------
    @bot.tree.command(name="card", description="View a card's stats")
    @app_commands.describe(name="Site name to look up")
    @app_commands.checks.cooldown(1, 5.0)
    async def card_command(interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            from api.cardgame.models import CardStats
            from pipeline.database import UnifiedSite, get_session

            with get_session() as session:
                # Fuzzy search by name
                site = (
                    session.query(UnifiedSite)
                    .filter(UnifiedSite.name.ilike(f"%{_escape_ilike(name)}%", escape="\\"))
                    .filter(UnifiedSite.source_id == "ancient_nerds")
                    .first()
                )
                if not site:
                    await interaction.followup.send(
                        f"No card found matching '{name}'.", ephemeral=True
                    )
                    return

                card = session.get(CardStats, site.id)
                if not card:
                    await interaction.followup.send(
                        f"'{site.name}' doesn't have card stats yet.", ephemeral=True
                    )
                    return

                color = RARITY_COLORS.get(card.rarity_tier, 0x9E9E9E)
                rarity_name = RARITY_NAMES.get(card.rarity_tier, "Common")

                embed = discord.Embed(
                    title=site.name,
                    color=color,
                )

                # Header info
                parts = []
                if site.period_name:
                    parts.append(site.period_name)
                if site.country:
                    parts.append(site.country)
                if parts:
                    embed.description = " | ".join(parts)

                # Stats
                embed.add_field(
                    name="Stats",
                    value=(
                        f"Antiquity: {_stat_bar(card.antiquity)}\n"
                        f"Fortification: {_stat_bar(card.fortification)}\n"
                        f"Cultural Influence: {_stat_bar(card.cultural_influence)}\n"
                        f"Mystery: {_stat_bar(card.mystery)}\n"
                        f"Legacy: {_stat_bar(card.legacy)}"
                    ),
                    inline=False,
                )

                # Meta
                embed.add_field(name="Total Power", value=str(card.total_power), inline=True)
                embed.add_field(
                    name="Rarity", value=f"{rarity_name} (Tier {card.rarity_tier})", inline=True
                )
                embed.add_field(name="Type", value=card.category_group, inline=True)

                # Empire affiliations
                from api.cardgame.constants import EMPIRE_DISPLAY_NAMES

                card_empires = card.empires or []
                if card_empires:
                    empire_names = [EMPIRE_DISPLAY_NAMES.get(e, e) for e in card_empires]
                    embed.add_field(name="Empires", value=", ".join(empire_names), inline=False)
                else:
                    embed.add_field(
                        name="Empires", value="Pre-Empire Site (Ancient Anchor)", inline=False
                    )

                if site.thumbnail_url:
                    embed.set_thumbnail(url=site.thumbnail_url)
                embed.set_footer(text="ancientnerds.com")

                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/card error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @card_command.error
    async def card_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /cards — View collection
    # -------------------------------------------------------------------
    @bot.tree.command(name="cards", description="View your card collection")
    @app_commands.describe(
        rarity="Filter by rarity tier (1-5)",
        page="Page number",
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def cards_command(
        interaction: discord.Interaction,
        rarity: int | None = None,
        page: int = 1,
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(str(interaction.user.id))
            if not user:
                await interaction.followup.send(
                    "Sign in at [ancientnerds.com](https://ancientnerds.com/account.html) first.",
                    ephemeral=True,
                )
                return

            from api.cardgame.leaderboard_service import fetch_collection_page
            from pipeline.database import get_session

            with get_session() as session:
                per_page = 10
                rows, total = fetch_collection_page(
                    session, user.id, rarity=rarity, page=page, per_page=per_page
                )

                if not rows:
                    msg = "No cards found." if total == 0 else f"No cards on page {page}."
                    await interaction.followup.send(msg, ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"Your Collection ({total} cards)",
                    color=0xC02023,
                )
                lines = []
                for _coll, card, site in rows:
                    rarity_name = RARITY_NAMES.get(card.rarity_tier, "?")
                    emoji = {1: "", 2: "", 3: "", 4: "", 5: ""}.get(card.rarity_tier, "")
                    lines.append(
                        f"{emoji} **{site.name}** — {rarity_name} | Power: {card.total_power}"
                    )
                embed.description = "\n".join(lines)

                pages = (total + per_page - 1) // per_page
                embed.set_footer(text=f"Page {page}/{pages} | ancientnerds.com")

                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/cards error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @cards_command.error
    async def cards_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /pack <type> — Open a card pack
    # -------------------------------------------------------------------
    @bot.tree.command(name="pack", description="Open a card pack")
    @app_commands.describe(pack_type="Pack type: bronze, silver, gold, legendary")
    @app_commands.choices(
        pack_type=[
            app_commands.Choice(
                name=f"{name.title()} ({p['cost']} credits, {p['cards']} cards)", value=name
            )
            for name, p in PACK_PRICES.items()
        ]
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def pack_command(interaction: discord.Interaction, pack_type: str):
        discord_id = str(interaction.user.id)
        if not _pack_limiter.check(discord_id):
            await interaction.response.send_message("Too fast! Wait a moment.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            from api.cardgame.packs import (
                InsufficientCreditsError,
                InvalidPackTypeError,
                open_pack,
            )
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                user = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.discord_id == discord_id,
                    )
                    .first()
                )
                if not user:
                    await interaction.followup.send(
                        "Sign in at ancientnerds.com first.",
                        ephemeral=True,
                    )
                    return

                try:
                    cards = open_pack(session, user, pack_type)
                except InvalidPackTypeError:
                    await interaction.followup.send("Invalid pack type.", ephemeral=True)
                    return
                except InsufficientCreditsError as e:
                    await interaction.followup.send(str(e), ephemeral=True)
                    return

                # Build result embed
                embed = discord.Embed(
                    title=f"{pack_type.title()} Pack Opened!",
                    color=0xFFC107,
                )
                lines = []
                for card in cards:
                    rarity_name = card.get("rarity_name", "Common")
                    name = card.get("name", "Unknown")
                    power = card.get("total_power", 0)
                    lines.append(f"**{name}** — {rarity_name} | Power: {power}")

                embed.description = (
                    "\n".join(lines) if lines else "No cards received (all duplicates refunded)"
                )
                embed.set_footer(text=f"Credits remaining: {user.credits:,} | ancientnerds.com")

                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/pack error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @pack_command.error
    async def pack_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /daily — Claim daily reward
    # -------------------------------------------------------------------
    @bot.tree.command(name="daily", description="Claim your daily card + credits")
    @app_commands.checks.cooldown(1, 30.0)
    async def daily_command(interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            from api.cardgame.rewards import AlreadyClaimedError, claim_daily
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                user = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.discord_id == discord_id,
                    )
                    .first()
                )
                if not user:
                    await interaction.followup.send(
                        "Sign in at ancientnerds.com first.",
                        ephemeral=True,
                    )
                    return

                try:
                    result = claim_daily(session, user)
                except AlreadyClaimedError:
                    await interaction.followup.send(
                        "You already claimed your daily reward today! Come back tomorrow.",
                        ephemeral=True,
                    )
                    return

                embed = discord.Embed(title="Daily Reward!", color=0x4CAF50)
                lines = [f"+{result['credits']} credits"]
                if result["card"]:
                    card = result["card"]
                    lines.append(f"Card: **{card['name']}** ({card['rarity_name']})")
                lines.append(f"Streak: {result['daily_streak']} days")
                if result.get("streak_reward"):
                    sr = result["streak_reward"]
                    lines.append(f"Streak bonus: **{sr['value'].title()} Pack!**")
                embed.description = "\n".join(lines)
                embed.set_footer(text="ancientnerds.com")

                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/daily error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @daily_command.error
    async def daily_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /deck — Manage decks
    # -------------------------------------------------------------------
    @bot.tree.command(name="deck", description="View or manage your battle deck")
    @app_commands.describe(action="What to do with your deck")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View active deck", value="view"),
            app_commands.Choice(name="List all decks", value="list"),
        ]
    )
    @app_commands.checks.cooldown(1, 5.0)
    async def deck_command(interaction: discord.Interaction, action: str = "view"):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(discord_id)
            if not user:
                await interaction.followup.send(
                    "Sign in at ancientnerds.com first.", ephemeral=True
                )
                return

            from api.cardgame.models import CardDeck, CardStats
            from pipeline.database import UnifiedSite, get_session

            with get_session() as session:
                if action == "list":
                    decks = session.query(CardDeck).filter(CardDeck.user_id == user.id).all()
                    if not decks:
                        await interaction.followup.send(
                            "No decks yet. Build one at ancientnerds.com/cards",
                            ephemeral=True,
                        )
                        return

                    embed = discord.Embed(title="Your Decks", color=0xC02023)
                    for d in decks:
                        status = " (Active)" if d.is_active else ""
                        embed.add_field(
                            name=f"{d.name}{status}",
                            value=f"{len(d.card_ids)} cards",
                            inline=True,
                        )
                    embed.set_footer(text="ancientnerds.com")
                    await interaction.followup.send(embed=embed, ephemeral=True)

                elif action == "view":
                    deck = (
                        session.query(CardDeck)
                        .filter(CardDeck.user_id == user.id, CardDeck.is_active)
                        .first()
                    )
                    if not deck:
                        await interaction.followup.send(
                            "No active deck. Set one at ancientnerds.com/cards",
                            ephemeral=True,
                        )
                        return

                    embed = discord.Embed(title=f"Deck: {deck.name}", color=0xC02023)

                    # Commander info
                    from api.cardgame.constants import EMPIRE_DISPLAY_NAMES, EMPIRE_THEMATIC_STATS

                    if deck.commander_empire_id:
                        cmd_name = EMPIRE_DISPLAY_NAMES.get(
                            deck.commander_empire_id, deck.commander_empire_id
                        )
                        cmd_stat = EMPIRE_THEMATIC_STATS.get(deck.commander_empire_id, "")
                        embed.add_field(
                            name="Commander",
                            value=f"{cmd_name} (+1 {cmd_stat.replace('_', ' ').title()} to homeland sites)",
                            inline=False,
                        )

                    lines = []
                    for cid_str in deck.card_ids:
                        try:
                            cid = uuid.UUID(cid_str)
                        except ValueError:
                            continue
                        card = session.get(CardStats, cid)
                        site = session.get(UnifiedSite, cid)
                        if card and site:
                            rarity_name = RARITY_NAMES.get(card.rarity_tier, "?")
                            lines.append(
                                f"**{site.name}** — {rarity_name} | Power: {card.total_power}"
                            )
                    embed.description = "\n".join(lines) if lines else "Empty deck"

                    # Show active synergies
                    deck_cards = []
                    for cid_str in deck.card_ids:
                        try:
                            card = session.get(CardStats, uuid.UUID(cid_str))
                            if card:
                                deck_cards.append(card)
                        except ValueError:
                            continue
                    if deck_cards:
                        from api.cardgame.synergies import describe_synergies

                        synergy_lines = describe_synergies(
                            deck_cards, commander_empire_id=deck.commander_empire_id
                        )
                        if synergy_lines:
                            embed.add_field(
                                name="Active Synergies",
                                value="\n".join(synergy_lines),
                                inline=False,
                            )

                    embed.set_footer(text="ancientnerds.com")
                    await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"/deck error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @deck_command.error
    async def deck_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /duel @player [stake] — Challenge to battle
    # -------------------------------------------------------------------
    @bot.tree.command(name="duel", description="Challenge another player to a card battle")
    @app_commands.describe(
        opponent="Player to challenge",
        stake="Credits to wager (0 for friendly)",
    )
    @app_commands.checks.cooldown(1, 30.0)
    async def duel_command(
        interaction: discord.Interaction,
        opponent: discord.Member,
        stake: int = 0,
    ):
        discord_id = str(interaction.user.id)
        opponent_discord_id = str(opponent.id)

        if discord_id == opponent_discord_id:
            await interaction.response.send_message("You can't duel yourself!", ephemeral=True)
            return

        if opponent.bot:
            await interaction.response.send_message("You can't duel a bot!", ephemeral=True)
            return

        if stake < 0:
            await interaction.response.send_message("Stake must be 0 or more.", ephemeral=True)
            return

        if stake > BATTLE_MAX_STAKE:
            await interaction.response.send_message(
                f"Maximum stake is {BATTLE_MAX_STAKE:,} credits.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        try:
            from api.cardgame.models import CardBattle, CardDeck, CardStats
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.discord_id == discord_id,
                    )
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.discord_id == opponent_discord_id,
                    )
                    .first()
                )

                if not challenger or not defender:
                    await interaction.followup.send(
                        "Both players must be registered at ancientnerds.com.",
                    )
                    return

                # Check active decks
                c_deck = (
                    session.query(CardDeck)
                    .filter(
                        CardDeck.user_id == challenger.id,
                        CardDeck.is_active,
                    )
                    .first()
                )
                d_deck = (
                    session.query(CardDeck)
                    .filter(
                        CardDeck.user_id == defender.id,
                        CardDeck.is_active,
                    )
                    .first()
                )

                if not c_deck or len(c_deck.card_ids) < 5:
                    await interaction.followup.send(
                        "You need an active deck with at least 5 cards to duel.",
                    )
                    return
                if not d_deck or len(d_deck.card_ids) < 5:
                    await interaction.followup.send(
                        f"{opponent.display_name} doesn't have an active deck with enough cards.",
                    )
                    return

                # Credit check removed — the accept handler's with_for_update()
                # check is the authoritative guard against insufficient funds.

                # Create pending battle
                battle = CardBattle(
                    challenger_id=challenger.id,
                    defender_id=defender.id,
                    stake_credits=stake,
                    status="pending",
                )
                session.add(battle)
                session.flush()
                battle_id = str(battle.id)

            # Send challenge with Accept/Decline buttons
            stake_text = f" for **{stake} credits**" if stake > 0 else ""
            embed = discord.Embed(
                title="Card Battle Challenge!",
                description=(
                    f"{interaction.user.mention} challenges {opponent.mention}"
                    f" to a duel{stake_text}!\n\n"
                    f"5 rounds, 5 stats, may the best deck win."
                ),
                color=0xC02023,
            )
            embed.set_footer(text="Expires in 5 minutes | ancientnerds.com")

            view = DuelView(
                battle_id=battle_id, challenger_id=discord_id, defender_id=opponent_discord_id
            )
            await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            logger.exception(f"/duel error: {e}")
            await interaction.followup.send("Something went wrong.")

    @duel_command.error
    async def duel_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /leaderboard — Rankings
    # -------------------------------------------------------------------
    @bot.tree.command(name="leaderboard", description="Card game rankings")
    @app_commands.describe(sort="Sort by")
    @app_commands.choices(
        sort=[
            app_commands.Choice(name="Wins", value="wins"),
            app_commands.Choice(name="Collection size", value="cards"),
            app_commands.Choice(name="XP", value="power"),
            app_commands.Choice(name="Best streak", value="streak"),
        ]
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def leaderboard_command(interaction: discord.Interaction, sort: str = "wins"):
        await interaction.response.defer(ephemeral=True)
        try:
            from api.cardgame.leaderboard_service import get_leaderboard_entries
            from pipeline.database import get_session

            with get_session() as session:
                rows = get_leaderboard_entries(session, sort, limit=10)
                if not rows:
                    await interaction.followup.send("No players yet!", ephemeral=True)
                    return

                embed = discord.Embed(
                    title=f"Leaderboard — {sort.title()}",
                    color=0xFFC107,
                )
                lines = []
                for i, entry in enumerate(rows, 1):
                    name = entry["username"]
                    if sort == "wins":
                        val = f"{entry['wins']}W / {entry['losses']}L"
                    elif sort == "cards":
                        val = f"{entry['total_cards']} cards"
                    elif sort == "power":
                        val = f"{entry['xp']} XP"
                    elif sort == "streak":
                        val = f"{entry['best_streak']} best streak"
                    lines.append(f"**{i}.** {name} — {val}")

                embed.description = "\n".join(lines)
                embed.set_footer(text="ancientnerds.com")
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception(f"/leaderboard error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @leaderboard_command.error
    async def leaderboard_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /quiz — Daily knowledge quiz (Phase C)
    # -------------------------------------------------------------------
    @bot.tree.command(
        name="quiz", description="Test your archaeology knowledge! 5 questions, earn credits & XP"
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def quiz_command(interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(discord_id)
            if not user:
                await interaction.followup.send(
                    "Sign in at ancientnerds.com first.",
                    ephemeral=True,
                )
                return

            from api.cardgame.quiz import QuizLimitReachedError, generate_quiz
            from pipeline.database import get_session

            with get_session() as session:
                try:
                    quiz_data = generate_quiz(session, user.id)
                except QuizLimitReachedError:
                    await interaction.followup.send(
                        "You've used all your quiz attempts today! Come back tomorrow.",
                        ephemeral=True,
                    )
                    return

            if not quiz_data["questions"]:
                await interaction.followup.send("Couldn't generate quiz questions.", ephemeral=True)
                return

            q = quiz_data["questions"][0]
            embed = discord.Embed(
                title=f"Question 1/{len(quiz_data['questions'])}",
                description=q["question"],
                color=0x2196F3,
            )
            embed.set_footer(text=f"Type: {q['type'].replace('_', ' ').title()}")

            view = QuizView(discord_id, quiz_data)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.exception(f"/quiz error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @quiz_command.error
    async def quiz_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /expedition — PvE campaign (Phase D)
    # -------------------------------------------------------------------
    @bot.tree.command(
        name="expedition", description="Play a themed archaeological expedition (PvE)"
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def expedition_command(interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(discord_id)
            if not user:
                await interaction.followup.send(
                    "Sign in at ancientnerds.com first.",
                    ephemeral=True,
                )
                return

            from api.cardgame.expedition import get_available_expeditions, get_expedition_progress
            from pipeline.database import get_session

            expeditions = get_available_expeditions()

            with get_session() as session:
                progress = get_expedition_progress(session, user.id)

            embed = discord.Embed(
                title="Archaeological Expeditions",
                description="Choose an expedition to explore! Defeat NPC decks themed by region to earn rewards.",
                color=0x795548,
            )

            for exp in expeditions[:10]:
                p = next((pr for pr in progress if pr["expedition_id"] == exp["id"]), None)
                stage = p["current_stage"] if p else 0
                completed = p["completed"] if p else False
                status = "Completed" if completed else f"Stage {stage}/{exp['stages']}"
                embed.add_field(
                    name=exp["name"], value=f"{exp['description']}\n*{status}*", inline=False
                )

            embed.set_footer(text="ancientnerds.com")

            view = ExpeditionListView(discord_id, expeditions, progress)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.exception(f"/expedition error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @expedition_command.error
    async def expedition_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /empire <name> — View an empire card's details
    # -------------------------------------------------------------------
    @bot.tree.command(name="empire", description="View an empire card's details")
    @app_commands.describe(name="Empire name to look up")
    @app_commands.checks.cooldown(1, 5.0)
    async def empire_command(interaction: discord.Interaction, name: str):
        await interaction.response.defer(ephemeral=True)
        try:
            from api.cardgame.constants import (
                EMPIRE_DESCRIPTIONS,
                EMPIRE_DISPLAY_NAMES,
                EMPIRE_THEMATIC_STATS,
            )
            from pipeline.historical_boundaries.empire_metadata import EMPIRE_METADATA

            # Fuzzy match empire name
            name_lower = name.lower()
            matched_id = None
            for eid, display_name in EMPIRE_DISPLAY_NAMES.items():
                if name_lower in display_name.lower() or name_lower in eid.lower():
                    matched_id = eid
                    break

            if not matched_id:
                await interaction.followup.send(
                    f"No empire found matching '{name}'. Try: Roman, Egyptian, Greek, Han, etc.",
                    ephemeral=True,
                )
                return

            meta = EMPIRE_METADATA.get(matched_id, {})
            display_name = EMPIRE_DISPLAY_NAMES.get(matched_id, matched_id)
            thematic_stat = EMPIRE_THEMATIC_STATS.get(matched_id, "unknown")
            description = EMPIRE_DESCRIPTIONS.get(matched_id, "")
            color = meta.get("color", 0x888888)
            region = meta.get("region", "Unknown")
            start = meta.get("startYear", 0)
            end = meta.get("endYear", 0)

            def _year_fmt(y: int) -> str:
                return f"{abs(y)} BCE" if y < 0 else f"{y} CE"

            embed = discord.Embed(
                title=display_name,
                description=description,
                color=color,
            )
            embed.add_field(name="Region", value=region, inline=True)
            embed.add_field(
                name="Period", value=f"{_year_fmt(start)} – {_year_fmt(end)}", inline=True
            )
            embed.add_field(
                name="Thematic Stat",
                value=thematic_stat.replace("_", " ").title(),
                inline=True,
            )
            embed.add_field(
                name="Commander Bonus",
                value=f"+1 {thematic_stat.replace('_', ' ').title()} to up to 3 homeland sites",
                inline=False,
            )
            embed.set_footer(text="Earned by completing expeditions | ancientnerds.com")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"/empire error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @empire_command.error
    async def empire_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /empires — List collected empire cards
    # -------------------------------------------------------------------
    @bot.tree.command(name="empires", description="View your collected empire cards")
    @app_commands.checks.cooldown(1, 5.0)
    async def empires_command(interaction: discord.Interaction):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(discord_id)
            if not user:
                await interaction.followup.send(
                    "Sign in at ancientnerds.com first.",
                    ephemeral=True,
                )
                return

            from api.cardgame.constants import EMPIRE_DISPLAY_NAMES, EMPIRE_THEMATIC_STATS
            from api.cardgame.models import EmpireCollection
            from pipeline.database import get_session

            with get_session() as session:
                owned = (
                    session.query(EmpireCollection)
                    .filter(EmpireCollection.user_id == user.id)
                    .order_by(EmpireCollection.acquired_at)
                    .all()
                )

            if not owned:
                await interaction.followup.send(
                    "No empire cards yet! Complete expeditions to earn them.",
                    ephemeral=True,
                )
                return

            embed = discord.Embed(
                title=f"Your Empire Cards ({len(owned)})",
                color=0xFFC107,
            )
            lines = []
            for ec in owned:
                name = EMPIRE_DISPLAY_NAMES.get(ec.empire_id, ec.empire_id)
                stat = EMPIRE_THEMATIC_STATS.get(ec.empire_id, "?")
                lines.append(
                    f"**{name}** — {stat.replace('_', ' ').title()} | via {ec.acquired_via}"
                )
            embed.description = "\n".join(lines)
            embed.set_footer(text="Use /deck set-commander to equip one | ancientnerds.com")

            await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.exception(f"/empires error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @empires_command.error
    async def empires_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /set-commander <empire> — Equip a commander to your active deck
    # -------------------------------------------------------------------
    @bot.tree.command(
        name="set-commander", description="Equip an empire commander to your active deck"
    )
    @app_commands.describe(empire="Empire name (or 'none' to remove)")
    @app_commands.checks.cooldown(1, 5.0)
    async def set_commander_command(interaction: discord.Interaction, empire: str):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)
        try:
            user = _get_user_or_none(discord_id)
            if not user:
                await interaction.followup.send(
                    "Sign in at ancientnerds.com first.",
                    ephemeral=True,
                )
                return

            from api.cardgame.constants import EMPIRE_DISPLAY_NAMES
            from api.cardgame.models import CardDeck, EmpireCollection
            from pipeline.database import get_session

            with get_session() as session:
                deck = (
                    session.query(CardDeck)
                    .filter(CardDeck.user_id == user.id, CardDeck.is_active)
                    .first()
                )
                if not deck:
                    await interaction.followup.send(
                        "No active deck. Create one at ancientnerds.com/cards first.",
                        ephemeral=True,
                    )
                    return

                if empire.lower() in ("none", "remove", "clear"):
                    deck.commander_empire_id = None
                    await interaction.followup.send(
                        "Commander removed from your active deck.",
                        ephemeral=True,
                    )
                    return

                # Fuzzy match empire name
                empire_lower = empire.lower()
                matched_id = None
                for eid, display_name in EMPIRE_DISPLAY_NAMES.items():
                    if empire_lower in display_name.lower() or empire_lower in eid.lower():
                        matched_id = eid
                        break

                if not matched_id:
                    await interaction.followup.send(
                        f"No empire found matching '{empire}'. Use /empires to see your collection.",
                        ephemeral=True,
                    )
                    return

                # Check user owns it
                owned = (
                    session.query(EmpireCollection)
                    .filter(
                        EmpireCollection.user_id == user.id,
                        EmpireCollection.empire_id == matched_id,
                    )
                    .first()
                )
                if not owned:
                    await interaction.followup.send(
                        f"You don't own the {EMPIRE_DISPLAY_NAMES[matched_id]} empire card. "
                        "Complete expeditions to earn empire cards!",
                        ephemeral=True,
                    )
                    return

                deck.commander_empire_id = matched_id
                display_name = EMPIRE_DISPLAY_NAMES[matched_id]

            await interaction.followup.send(
                f"**{display_name}** set as Commander for your active deck!",
                ephemeral=True,
            )

        except Exception as e:
            logger.exception(f"/set-commander error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @set_commander_command.error
    async def set_commander_error(
        interaction: discord.Interaction, error: app_commands.AppCommandError
    ):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )

    # -------------------------------------------------------------------
    # /lyra [tier] — Challenge Lyra to a duel
    # -------------------------------------------------------------------
    @bot.tree.command(name="lyra", description="Challenge Lyra to a card duel")
    @app_commands.describe(tier="Difficulty tier (1-4, defaults to list if omitted)")
    @app_commands.checks.cooldown(1, 5.0)
    async def lyra_command(interaction: discord.Interaction, tier: int | None = None):
        discord_id = str(interaction.user.id)
        await interaction.response.defer(ephemeral=True)

        try:
            from api.cardgame.constants import LYRA_TIERS
            from api.cardgame.lyra_duel import can_challenge_lyra, get_lyra_status
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                user = (
                    session.query(DiscordUser).filter(DiscordUser.discord_id == discord_id).first()
                )
                if not user:
                    await interaction.followup.send(
                        "Sign in at ancientnerds.com first.", ephemeral=True
                    )
                    return

                status = get_lyra_status(session, user.id)

                # If tier specified, try to play directly
                if tier is not None:
                    if tier not in LYRA_TIERS:
                        await interaction.followup.send(
                            "Tier must be 1-4. Use `/lyra` without a tier to see all options.",
                            ephemeral=True,
                        )
                        return
                    can_play, last_result = can_challenge_lyra(session, user.id, tier)
                    if not can_play:
                        result_text = "won" if last_result == "win" else "lost"
                        await interaction.followup.send(
                            f"You've already challenged {LYRA_TIERS[tier]['name']} today. "
                            f"Result: {result_text}. Come back tomorrow!",
                            ephemeral=True,
                        )
                        return

                    from api.cardgame.lyra_duel import resolve_lyra_duel

                    try:
                        result = resolve_lyra_duel(session, user, tier)
                    except ValueError as e:
                        await interaction.followup.send(str(e), ephemeral=True)
                        return

                    color = 0x4CAF50 if result["player_won"] else 0xF44336
                    title = (
                        f"Victory! You beat {result['lyra_name']}!"
                        if result["player_won"]
                        else f"Defeat... {result['lyra_name']} wins."
                    )
                    embed = discord.Embed(title=title, color=color)
                    embed.add_field(
                        name="Score",
                        value=f"You: {result['player_score']} | Lyra: {result['lyra_score']}",
                        inline=False,
                    )

                    reward_lines = [
                        f"+{result['credits_earned']} credits",
                        f"+{result['xp_earned']} XP",
                    ]
                    if result["pack_reward"]:
                        reward_lines.append(f"+{result['pack_reward'].title()} Pack!")
                    embed.add_field(name="Rewards", value="\n".join(reward_lines), inline=False)

                    embed.set_footer(text="ancientnerds.com")
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    return

            # No tier specified — show the tier selection embed
            embed = discord.Embed(
                title="Challenge Lyra",
                description="Lyra awaits your challenge! Choose your difficulty below.",
                color=0x9C27B0,
            )

            tier_emojis = {1: "\u2605", 2: "\u2605\u2605", 3: "\u2605\u2605\u2605", 4: "\u2b50"}

            for t, cfg in LYRA_TIERS.items():
                status_info = status.get(t, {})
                status_text = status_info.get("status", "available")
                can_play = status_info.get("can_challenge", True)

                if status_text == "win":
                    line = f"~~{cfg['description']}~~ ✅ Won today!"
                elif status_text == "loss":
                    line = f"~~{cfg['description']}~~ ❌ Lost today"
                else:
                    reward_preview = f"Win: {cfg['win_credits']}cr/{cfg['win_xp']}XP" + (
                        f" + {cfg['win_pack'].title()} Pack" if cfg["win_pack"] else ""
                    )
                    line = f"{cfg['description']}\n*{reward_preview}*"

                emoji = tier_emojis.get(t, "\u2605")
                name = f"{emoji} {cfg['name']}"
                embed.add_field(name=name, value=line, inline=False)

            embed.set_footer(text="ancientnerds.com")

            view = LyraView(discord_id)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.exception(f"/lyra error: {e}")
            await interaction.followup.send("Something went wrong.", ephemeral=True)

    @lyra_command.error
    async def lyra_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"Please wait {error.retry_after:.0f}s.",
                ephemeral=True,
            )


# ---------------------------------------------------------------------------
# Lyra duel view
# ---------------------------------------------------------------------------


class LyraView(discord.ui.View):
    """Lyra tier selection with challenge buttons."""

    def __init__(self, discord_id: str):
        super().__init__(timeout=120)
        self.discord_id = discord_id

        from api.cardgame.constants import LYRA_TIERS

        tier_emojis = {1: "\u2605", 2: "\u2605\u2605", 3: "\u2605\u2605\u2605", 4: "\u2b50"}
        tier_labels = {
            1: "Casual",
            2: "Scholar",
            3: "Sage",
            4: "Ancient",
        }
        tier_colors = {
            1: discord.ButtonStyle.green,
            2: discord.ButtonStyle.green,
            3: discord.ButtonStyle.red,
            4: discord.ButtonStyle.red,
        }

        for tier in [1, 2, 3, 4]:
            label = f"{tier_emojis[tier]} {tier_labels[tier]}"
            btn = discord.ui.Button(
                label=label,
                style=tier_colors[tier],
                custom_id=f"lyra_tier_{tier}",
                row=(tier - 1) // 2,
            )
            btn.callback = self._make_callback(tier)
            self.add_item(btn)

    def _make_callback(self, tier: int):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.discord_id:
                await interaction.response.send_message("Not your Lyra duel.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            from api.cardgame.constants import LYRA_TIERS
            from api.cardgame.lyra_duel import can_challenge_lyra, resolve_lyra_duel
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                user = (
                    session.query(DiscordUser)
                    .filter(DiscordUser.discord_id == self.discord_id)
                    .first()
                )
                if not user:
                    await interaction.followup.send(
                        "Sign in at ancientnerds.com first.", ephemeral=True
                    )
                    return

                can_play, last_result = can_challenge_lyra(session, user.id, tier)
                if not can_play:
                    result_text = "won" if last_result == "win" else "lost"
                    await interaction.followup.send(
                        f"You've already challenged {LYRA_TIERS[tier]['name']} today. "
                        f"Result: {result_text}. Come back tomorrow!",
                        ephemeral=True,
                    )
                    return

                try:
                    result = resolve_lyra_duel(session, user, tier)
                except ValueError as e:
                    await interaction.followup.send(str(e), ephemeral=True)
                    return

            color = 0x4CAF50 if result["player_won"] else 0xF44336
            title = (
                f"Victory! You beat {result['lyra_name']}!"
                if result["player_won"]
                else f"Defeat... {result['lyra_name']} wins."
            )
            embed = discord.Embed(title=title, color=color)
            embed.add_field(
                name="Score",
                value=f"You: {result['player_score']} | Lyra: {result['lyra_score']}",
                inline=False,
            )

            reward_lines = [
                f"+{result['credits_earned']} credits",
                f"+{result['xp_earned']} XP",
            ]
            if result["pack_reward"]:
                reward_lines.append(f"+{result['pack_reward'].title()} Pack!")
            embed.add_field(name="Rewards", value="\n".join(reward_lines), inline=False)
            embed.set_footer(text="ancientnerds.com")

            await interaction.followup.send(embed=embed, ephemeral=True)
            self.stop()

        return callback


# ---------------------------------------------------------------------------
# Duel Accept/Decline UI with Snap mechanic (Phase B)
# ---------------------------------------------------------------------------


def _build_round_lines(result: dict, up_to: int | None = None) -> list[str]:
    """Build round-by-round display lines from battle result."""
    from pipeline.database import UnifiedSite, get_session

    rounds = result["rounds"][:up_to] if up_to else result["rounds"]
    lines = []
    with get_session() as session:
        for r in rounds:
            c_site = session.get(UnifiedSite, uuid.UUID(r["challenger_card"]))
            d_site = session.get(UnifiedSite, uuid.UUID(r["defender_card"]))
            c_name = c_site.name if c_site else "?"
            d_name = d_site.name if d_site else "?"
            stat = r["stat"].replace("_", " ").title()
            c_val = r["challenger_value"] + r["challenger_bonus"]
            d_val = r["defender_value"] + r["defender_bonus"]
            syn_note = ""
            if r.get("challenger_synergy") or r.get("defender_synergy"):
                parts = []
                if r.get("challenger_synergy"):
                    parts.append(f"+{r['challenger_synergy']} syn")
                if r.get("defender_synergy"):
                    parts.append(f"+{r['defender_synergy']} syn")
                syn_note = f" ({', '.join(parts)})"
            winner_icon = {
                "challenger": "\u2b05\ufe0f",
                "defender": "\u27a1\ufe0f",
                "draw": "\ud83e\udd1d",
            }[r["winner"]]
            lines.append(
                f"**R{r['round']}** ({stat}): {c_name} [{c_val}] "
                f"{winner_icon} [{d_val}] {d_name}{syn_note}"
            )
    return lines


def _build_result_embed(
    result: dict,
    challenger_id: str,
    defender_id: str,
    snap_multiplier: int = 1,
    retreated_by: str | None = None,
) -> discord.Embed:
    """Build the final battle result embed."""
    embed = discord.Embed(title="Battle Results!", color=0xC02023)

    round_lines = _build_round_lines(result)
    embed.description = "\n".join(round_lines)

    # Synergy summary
    syn_parts = []
    if result.get("challenger_synergies"):
        syn_parts.append(f"<@{challenger_id}>: " + ", ".join(result["challenger_synergies"]))
    if result.get("defender_synergies"):
        syn_parts.append(f"<@{defender_id}>: " + ", ".join(result["defender_synergies"]))
    if syn_parts:
        embed.add_field(name="Active Synergies", value="\n".join(syn_parts), inline=False)

    if retreated_by:
        retreater = f"<@{retreated_by}>"
        winner_id = defender_id if retreated_by == challenger_id else challenger_id
        winner_text = f"{retreater} retreated! <@{winner_id}> wins!"
    else:
        winner_text = {
            "challenger": f"<@{challenger_id}> wins!",
            "defender": f"<@{defender_id}> wins!",
            "draw": "It's a draw!",
        }[result["winner"]]

    score_line = f"Score: {result['challenger_wins']} - {result['defender_wins']}"
    if snap_multiplier > 1:
        score_line += f" | Stakes: **{snap_multiplier}x**"

    embed.add_field(name="Result", value=f"{winner_text}\n{score_line}")
    embed.set_footer(text="ancientnerds.com")
    return embed


class DuelView(discord.ui.View):
    """Accept/Decline buttons for a duel challenge."""

    def __init__(self, battle_id: str, challenger_id: str, defender_id: str):
        super().__init__(timeout=300)  # 5 min
        self.battle_id = battle_id
        self.challenger_id = challenger_id
        self.defender_id = defender_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, emoji="\u2694\ufe0f")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.defender_id:
            await interaction.response.send_message(
                "Only the challenged player can accept.", ephemeral=True
            )
            return

        await interaction.response.defer()
        try:
            from api.cardgame.battle import resolve_battle
            from api.cardgame.models import CardBattle, CardDeck, CardStats
            from pipeline.database import CreditGrant, DiscordUser, get_session

            with get_session() as session:
                battle = session.get(CardBattle, uuid.UUID(self.battle_id))
                if not battle or battle.status != "pending":
                    await interaction.followup.send("This duel is no longer available.")
                    self.stop()
                    return

                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.challenger_id,
                    )
                    .with_for_update()
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.defender_id,
                    )
                    .with_for_update()
                    .first()
                )

                # Escrow stakes
                if battle.stake_credits > 0:
                    if (
                        challenger.credits < battle.stake_credits
                        or defender.credits < battle.stake_credits
                    ):
                        battle.status = "cancelled"
                        await interaction.followup.send(
                            "Not enough credits for the stake. Duel cancelled."
                        )
                        self.stop()
                        return
                    challenger.credits -= battle.stake_credits
                    defender.credits -= battle.stake_credits
                    session.add(
                        CreditGrant(
                            user_id=challenger.id,
                            amount=-battle.stake_credits,
                            reason="card_battle_stake_escrow",
                        )
                    )
                    session.add(
                        CreditGrant(
                            user_id=defender.id,
                            amount=-battle.stake_credits,
                            reason="card_battle_stake_escrow",
                        )
                    )

                battle.status = "active"

                # Load decks
                c_deck_row = (
                    session.query(CardDeck)
                    .filter(
                        CardDeck.user_id == battle.challenger_id,
                        CardDeck.is_active,
                    )
                    .first()
                )
                d_deck_row = (
                    session.query(CardDeck)
                    .filter(
                        CardDeck.user_id == battle.defender_id,
                        CardDeck.is_active,
                    )
                    .first()
                )

                c_cards = [session.get(CardStats, uuid.UUID(cid)) for cid in c_deck_row.card_ids]
                d_cards = [session.get(CardStats, uuid.UUID(cid)) for cid in d_deck_row.card_ids]
                c_cards = [c for c in c_cards if c is not None]
                d_cards = [c for c in d_cards if c is not None]

                # Resolve battle (deterministic, instant)
                c_commander = c_deck_row.commander_empire_id if c_deck_row else None
                d_commander = d_deck_row.commander_empire_id if d_deck_row else None
                result = resolve_battle(
                    c_cards,
                    d_cards,
                    self.battle_id,
                    challenger_commander=c_commander,
                    defender_commander=d_commander,
                )

                # No stake → apply results in the same transaction
                stake_credits = battle.stake_credits
                if stake_credits == 0:
                    from api.cardgame.battle import apply_battle_result

                    apply_battle_result(session, battle, result, challenger, defender)

            # Disable accept/decline buttons
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)

            # If there's a stake, show partial results with snap opportunity
            if stake_credits > 0:
                preview_lines = _build_round_lines(result, up_to=2)
                preview_embed = discord.Embed(
                    title="Battle in progress...",
                    description="\n".join(preview_lines) + "\n\n*3 rounds remaining...*",
                    color=0xFFA000,
                )
                preview_embed.add_field(
                    name="Snap?",
                    value=(
                        f"Current stake: **{stake_credits}** credits each\n"
                        "Snap to **double** the stakes! Or continue to see results."
                    ),
                )
                preview_embed.set_footer(text="30 seconds to decide | ancientnerds.com")

                snap_view = SnapView(
                    battle_id=self.battle_id,
                    challenger_id=self.challenger_id,
                    defender_id=self.defender_id,
                    result=result,
                    original_stake=stake_credits,
                )
                snap_msg = await interaction.followup.send(
                    embed=preview_embed, view=snap_view, wait=True
                )
                snap_view.message = snap_msg
            else:
                embed = _build_result_embed(result, self.challenger_id, self.defender_id)
                await interaction.followup.send(embed=embed)

            self.stop()

        except Exception as e:
            logger.exception(f"Duel accept error: {e}")
            await interaction.followup.send("Something went wrong resolving the duel.")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red, emoji="\u274c")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.defender_id:
            await interaction.response.send_message(
                "Only the challenged player can decline.", ephemeral=True
            )
            return

        from api.cardgame.models import CardBattle
        from pipeline.database import get_session

        with get_session() as session:
            battle = (
                session.query(CardBattle)
                .filter(CardBattle.id == uuid.UUID(self.battle_id), CardBattle.status == "pending")
                .with_for_update()
                .first()
            )
            if battle:
                battle.status = "declined"

        if not battle:
            await interaction.response.send_message(
                "This duel is no longer pending.", ephemeral=True
            )
            return

        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(
            content="Duel declined.",
            embed=None,
            view=self,
        )
        self.stop()

    async def on_timeout(self):
        from api.cardgame.models import CardBattle
        from pipeline.database import get_session

        with get_session() as session:
            battle = session.get(CardBattle, uuid.UUID(self.battle_id))
            if battle and battle.status == "pending":
                battle.status = "expired"


class SnapView(discord.ui.View):
    """Snap / Continue buttons shown after first 2 rounds (staked battles only)."""

    def __init__(
        self,
        battle_id: str,
        challenger_id: str,
        defender_id: str,
        result: dict,
        original_stake: int,
    ):
        super().__init__(timeout=30)
        self.battle_id = battle_id
        self.challenger_id = challenger_id
        self.defender_id = defender_id
        self.result = result
        self.original_stake = original_stake
        self.continued: set[str] = set()  # discord IDs who pressed Continue

    @discord.ui.button(
        label="Snap! (2x stakes)", style=discord.ButtonStyle.danger, emoji="\ud83d\udca5"
    )
    async def snap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id not in (self.challenger_id, self.defender_id):
            await interaction.response.send_message("You're not in this duel.", ephemeral=True)
            return

        await interaction.response.defer()

        # Record snap in DB
        from api.cardgame.models import CardBattle
        from pipeline.database import get_session

        with get_session() as session:
            battle = session.get(CardBattle, uuid.UUID(self.battle_id))
            if battle:
                battle.snapped_by = [user_id]
                battle.snap_multiplier = 2

        opponent_id = self.defender_id if user_id == self.challenger_id else self.challenger_id

        snap_embed = discord.Embed(
            title="\ud83d\udca5 SNAP!",
            description=(
                f"<@{user_id}> snapped! Stakes doubled to "
                f"**{self.original_stake * 2}** credits each!\n\n"
                f"<@{opponent_id}> — accept the higher stakes or retreat?"
            ),
            color=0xFF0000,
        )

        # Disable snap buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        response_view = SnapResponseView(
            battle_id=self.battle_id,
            challenger_id=self.challenger_id,
            defender_id=self.defender_id,
            result=self.result,
            snapper_id=user_id,
            opponent_id=opponent_id,
            new_stake=self.original_stake * 2,
        )
        await interaction.followup.send(embed=snap_embed, view=response_view)
        self.stop()

    @discord.ui.button(label="Continue", style=discord.ButtonStyle.secondary)
    async def continue_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        if user_id not in (self.challenger_id, self.defender_id):
            await interaction.response.send_message("You're not in this duel.", ephemeral=True)
            return

        self.continued.add(user_id)

        if len(self.continued) < 2:
            await interaction.response.send_message("Waiting for opponent...", ephemeral=True)
            return

        await interaction.response.defer()
        await self._finalize(interaction)

    async def on_timeout(self):
        """No snap — apply results and send the outcome via the stored message."""
        self._apply_and_stop(snap_multiplier=1)
        embed = _build_result_embed(self.result, self.challenger_id, self.defender_id)
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)
            await self.message.reply(embed=embed)

    async def _finalize(self, interaction: discord.Interaction):
        """Both continued or timed out — show full results at original stakes."""
        self._apply_and_stop(snap_multiplier=1)

        embed = _build_result_embed(self.result, self.challenger_id, self.defender_id)
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(embed=embed)
        self.stop()

    def _apply_and_stop(self, snap_multiplier: int):
        """Apply battle result to DB."""
        from api.cardgame.battle import apply_battle_result
        from api.cardgame.models import CardBattle
        from pipeline.database import DiscordUser, get_session

        with get_session() as session:
            battle = (
                session.query(CardBattle)
                .filter(CardBattle.id == uuid.UUID(self.battle_id), CardBattle.status == "active")
                .with_for_update()
                .first()
            )
            if battle:
                battle.snap_multiplier = snap_multiplier
                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.challenger_id,
                    )
                    .with_for_update()
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.defender_id,
                    )
                    .with_for_update()
                    .first()
                )
                apply_battle_result(session, battle, self.result, challenger, defender)


class SnapResponseView(discord.ui.View):
    """Accept / Retreat after opponent snaps."""

    def __init__(
        self,
        battle_id: str,
        challenger_id: str,
        defender_id: str,
        result: dict,
        snapper_id: str,
        opponent_id: str,
        new_stake: int,
    ):
        super().__init__(timeout=30)
        self.battle_id = battle_id
        self.challenger_id = challenger_id
        self.defender_id = defender_id
        self.result = result
        self.snapper_id = snapper_id
        self.opponent_id = opponent_id
        self.new_stake = new_stake

    @discord.ui.button(label="Accept (2x stakes)", style=discord.ButtonStyle.green)
    async def accept_snap(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message(
                "Only the opponent can respond.", ephemeral=True
            )
            return

        await interaction.response.defer()

        from api.cardgame.battle import apply_battle_result
        from api.cardgame.models import CardBattle
        from pipeline.database import CreditGrant, DiscordUser, get_session

        with get_session() as session:
            battle = (
                session.query(CardBattle)
                .filter(CardBattle.id == uuid.UUID(self.battle_id), CardBattle.status == "active")
                .with_for_update()
                .first()
            )
            if battle:
                battle.snap_multiplier = 2
                # Escrow additional stake from both players
                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.challenger_id,
                    )
                    .with_for_update()
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.defender_id,
                    )
                    .with_for_update()
                    .first()
                )

                additional = battle.stake_credits  # double means pay original again
                if challenger.credits >= additional and defender.credits >= additional:
                    challenger.credits -= additional
                    defender.credits -= additional
                    session.add(
                        CreditGrant(
                            user_id=challenger.id,
                            amount=-additional,
                            reason="card_battle_snap_escrow",
                        )
                    )
                    session.add(
                        CreditGrant(
                            user_id=defender.id,
                            amount=-additional,
                            reason="card_battle_snap_escrow",
                        )
                    )
                else:
                    battle.snap_multiplier = 1  # revert — can't afford snap
                apply_battle_result(session, battle, self.result, challenger, defender)
                snap_mult = battle.snap_multiplier
            else:
                snap_mult = 1
        embed = _build_result_embed(
            self.result,
            self.challenger_id,
            self.defender_id,
            snap_multiplier=snap_mult,
        )
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(embed=embed)
        self.stop()

    @discord.ui.button(label="Retreat", style=discord.ButtonStyle.red, emoji="\ud83c\udff3\ufe0f")
    async def retreat_snap(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.opponent_id:
            await interaction.response.send_message(
                "Only the opponent can respond.", ephemeral=True
            )
            return

        await interaction.response.defer()

        from api.cardgame.battle import apply_battle_result
        from api.cardgame.models import CardBattle
        from pipeline.database import DiscordUser, get_session

        # Retreat = forfeit at original stakes. Snapper wins by default.
        with get_session() as session:
            battle = (
                session.query(CardBattle)
                .filter(CardBattle.id == uuid.UUID(self.battle_id), CardBattle.status == "active")
                .with_for_update()
                .first()
            )
            if battle:
                battle.snap_multiplier = 1
                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.challenger_id,
                    )
                    .with_for_update()
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.defender_id,
                    )
                    .with_for_update()
                    .first()
                )

                # Override result: snapper wins by retreat
                retreat_result = dict(self.result)
                if self.snapper_id == self.challenger_id:
                    retreat_result["winner"] = "challenger"
                else:
                    retreat_result["winner"] = "defender"

                apply_battle_result(session, battle, retreat_result, challenger, defender)

        embed = _build_result_embed(
            self.result,
            self.challenger_id,
            self.defender_id,
            retreated_by=self.opponent_id,
        )
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        await interaction.followup.send(embed=embed)
        self.stop()

    async def on_timeout(self):
        """No response = retreat by default."""
        from api.cardgame.battle import apply_battle_result
        from api.cardgame.models import CardBattle
        from pipeline.database import DiscordUser, get_session

        with get_session() as session:
            battle = (
                session.query(CardBattle)
                .filter(CardBattle.id == uuid.UUID(self.battle_id), CardBattle.status == "active")
                .with_for_update()
                .first()
            )
            if battle:
                battle.snap_multiplier = 1
                challenger = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.challenger_id,
                    )
                    .with_for_update()
                    .first()
                )
                defender = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.id == battle.defender_id,
                    )
                    .with_for_update()
                    .first()
                )

                retreat_result = dict(self.result)
                if self.snapper_id == self.challenger_id:
                    retreat_result["winner"] = "challenger"
                else:
                    retreat_result["winner"] = "defender"
                apply_battle_result(session, battle, retreat_result, challenger, defender)


# ---------------------------------------------------------------------------
# Quiz UI (Phase C)
# ---------------------------------------------------------------------------


class QuizView(discord.ui.View):
    """Interactive quiz — shows one question at a time with answer buttons."""

    def __init__(self, discord_id: str, quiz_data: dict):
        super().__init__(timeout=120)  # 2 min for entire quiz
        self.discord_id = discord_id
        self.quiz_data = quiz_data
        self.answers: list[str] = []
        self.current_q = 0
        self._update_buttons()

    def _update_buttons(self):
        self.clear_items()
        if self.current_q >= len(self.quiz_data["questions"]):
            return
        q = self.quiz_data["questions"][self.current_q]
        for i, choice in enumerate(q["choices"]):
            label = choice[:80]  # Discord button label limit
            btn = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"quiz_{self.current_q}_{i}",
                row=i // 2,
            )
            btn.callback = self._make_callback(choice)
            self.add_item(btn)

    def _make_callback(self, choice: str):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.discord_id:
                await interaction.response.send_message(
                    "This is someone else's quiz.", ephemeral=True
                )
                return

            self.answers.append(choice)
            self.current_q += 1

            if self.current_q >= len(self.quiz_data["questions"]):
                # All answered — submit
                await interaction.response.defer()
                await self._submit_quiz(interaction)
                self.stop()
            else:
                # Show next question
                self._update_buttons()
                q = self.quiz_data["questions"][self.current_q]
                embed = discord.Embed(
                    title=f"Question {self.current_q + 1}/{len(self.quiz_data['questions'])}",
                    description=q["question"],
                    color=0x2196F3,
                )
                embed.set_footer(text=f"Type: {q['type'].replace('_', ' ').title()}")
                await interaction.response.edit_message(embed=embed, view=self)

        return callback

    async def _submit_quiz(self, interaction: discord.Interaction):
        from api.cardgame.quiz import submit_quiz_answers
        from pipeline.database import DiscordUser, get_session

        with get_session() as session:
            user = (
                session.query(DiscordUser)
                .filter(
                    DiscordUser.discord_id == self.discord_id,
                )
                .first()
            )
            if not user:
                await interaction.followup.send("User not found.", ephemeral=True)
                return

            result = submit_quiz_answers(
                session,
                user,
                self.quiz_data["session_id"],
                self.answers,
            )

        embed = discord.Embed(
            title=f"Quiz Results: {result['score']}/{result['total']}",
            color=0x4CAF50 if result["score"] == result["total"] else 0xFFA000,
        )
        lines = []
        for r in result["results"]:
            icon = "\u2705" if r["is_correct"] else "\u274c"
            lines.append(f"{icon} {r['explanation']}")
        embed.description = "\n".join(lines)

        reward_parts = []
        if result["rewards"]["credits"]:
            reward_parts.append(f"+{result['rewards']['credits']} credits")
        if result["rewards"]["xp"]:
            reward_parts.append(f"+{result['rewards']['xp']} XP")
        if result["rewards"]["bonus_card"]:
            card = result["rewards"]["bonus_card"]
            reward_parts.append(f"Bonus card: **{card['name']}** ({card['rarity_name']})")
        if reward_parts:
            embed.add_field(name="Rewards", value="\n".join(reward_parts))
        embed.set_footer(text="ancientnerds.com")

        await interaction.followup.send(embed=embed, ephemeral=True)


# ---------------------------------------------------------------------------
# Expedition UI (Phase D)
# ---------------------------------------------------------------------------


class ExpeditionListView(discord.ui.View):
    """List expeditions with Play buttons."""

    def __init__(self, discord_id: str, expeditions: list[dict], progress: list[dict]):
        super().__init__(timeout=120)
        self.discord_id = discord_id
        # Show up to 5 expeditions as buttons
        for i, exp in enumerate(expeditions[:5]):
            prog = next((p for p in progress if p["expedition_id"] == exp["id"]), None)
            stage = prog["current_stage"] if prog else 0
            completed = prog["completed"] if prog else False
            label = (
                f"{exp['name']} ({stage}/{exp['stages']})"
                if not completed
                else f"{exp['name']} (Done)"
            )
            style = discord.ButtonStyle.secondary if completed else discord.ButtonStyle.green
            btn = discord.ui.Button(
                label=label[:80],
                style=style,
                disabled=completed,
                custom_id=f"expedition_{exp['id']}",
                row=i // 3,
            )
            btn.callback = self._make_callback(exp["id"])
            self.add_item(btn)

    def _make_callback(self, expedition_id: str):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.discord_id:
                await interaction.response.send_message("Not your expedition list.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)

            from api.cardgame.expedition import play_expedition_stage
            from pipeline.database import DiscordUser, get_session

            with get_session() as session:
                user = (
                    session.query(DiscordUser)
                    .filter(
                        DiscordUser.discord_id == self.discord_id,
                    )
                    .first()
                )
                if not user:
                    await interaction.followup.send("User not found.", ephemeral=True)
                    return

                try:
                    result = play_expedition_stage(session, user, expedition_id)
                except ValueError as e:
                    await interaction.followup.send(str(e), ephemeral=True)
                    return

            # Build result embed
            color = 0x4CAF50 if result["player_won"] else 0xF44336
            embed = discord.Embed(
                title=f"{result['expedition']} — Stage {result['stage']}/{result['total_stages']}",
                color=color,
            )

            # Battle summary
            br = result["battle_result"]
            outcome = "Victory!" if result["player_won"] else "Defeat..."
            embed.add_field(
                name=outcome,
                value=f"Score: {br['challenger_wins']} - {br['defender_wins']}",
                inline=True,
            )

            # Lore
            if result["lore"]:
                embed.add_field(name="Did you know?", value=f"*{result['lore']}*", inline=False)

            # Rewards
            if result["player_won"]:
                reward_parts = []
                if result["rewards"]["credits"]:
                    reward_parts.append(f"+{result['rewards']['credits']} credits")
                if result["rewards"]["xp"]:
                    reward_parts.append(f"+{result['rewards']['xp']} XP")
                if result["rewards"]["pack"]:
                    reward_parts.append(
                        f"Completion reward: **{result['rewards']['pack'].title()} Pack!**"
                    )
                if result["rewards"].get("empire_card"):
                    ec = result["rewards"]["empire_card"]
                    reward_parts.append(f"Empire Card unlocked: **{ec['name']}**!")
                if reward_parts:
                    embed.add_field(name="Rewards", value="\n".join(reward_parts))

            if result["completed"]:
                embed.set_footer(text="Expedition complete! | ancientnerds.com")
            else:
                embed.set_footer(text="ancientnerds.com")

            await interaction.followup.send(embed=embed, ephemeral=True)

        return callback
