import asyncio
import discord
from discord.ext import commands
from config import DISCORD_TOKEN, SIGNUP_CHANNEL_ID

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def in_signup_channel():
    """Check that commands are used in the designated signup channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if SIGNUP_CHANNEL_ID and interaction.channel_id != SIGNUP_CHANNEL_ID:
            await interaction.response.send_message(
                f"This command can only be used in <#{SIGNUP_CHANNEL_ID}>.",
                ephemeral=True,
            )
            return False
        return True
    return discord.app_commands.check(predicate)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


async def load_extensions():
    cog_files = ["cogs.events", "cogs.signups", "cogs.reminders"]
    for cog in cog_files:
        try:
            await bot.load_extension(cog)
            print(f"Loaded {cog}")
        except Exception as e:
            print(f"Failed to load {cog}: {e}")


async def main():
    async with bot:
        await load_extensions()
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
