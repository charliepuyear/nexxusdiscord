import asyncio
import os
import discord
from discord.ext import commands
from config import DISCORD_TOKEN

# Debug: check all env vars
print(f"DEBUG: DISCORD_TOKEN from os.environ: {os.environ.get('DISCORD_TOKEN') is not None}")
print(f"DEBUG: DISCORD_TOKEN from config: {DISCORD_TOKEN is not None}")
print(f"DEBUG: All env var keys: {[k for k in os.environ.keys() if not k.startswith('_')]}")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


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


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    print(f"Command error: {error}")
    if isinstance(error, discord.app_commands.CheckFailure):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "You don't have permission to use this command.", ephemeral=True,
            )
    else:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"An error occurred: {error}", ephemeral=True,
            )


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
