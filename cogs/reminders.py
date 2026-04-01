"""Automatic reminders and deadline-based event closing."""
from __future__ import annotations

from datetime import datetime, timedelta
import discord
from discord.ext import commands, tasks
from config import SIGNUP_CHANNEL_ID
import sheets


class RemindersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_deadlines.start()

    def cog_unload(self):
        self.check_deadlines.cancel()

    @tasks.loop(minutes=30)
    async def check_deadlines(self):
        """Check for approaching deadlines and auto-close expired events."""
        if not SIGNUP_CHANNEL_ID:
            return

        channel = self.bot.get_channel(SIGNUP_CHANNEL_ID)
        if not channel:
            return

        now = datetime.utcnow()
        open_events = sheets.get_open_events()

        for event in open_events:
            deadline_str = str(event.get("Deadline", "None"))
            if deadline_str == "None" or not deadline_str.strip():
                continue

            try:
                deadline = datetime.strptime(deadline_str.strip(), "%Y-%m-%d %H:%M")
            except ValueError:
                continue

            event_name = event["Event Name"]

            # Auto-close if deadline has passed
            if now >= deadline:
                sheets.close_event(event_name)
                signups = sheets.get_signups_for_event(event_name)
                embed = discord.Embed(
                    title="Signups Closed",
                    description=(
                        f"The signup deadline for **{event_name}** has passed.\n"
                        f"**{len(signups)}** driver(s) signed up."
                    ),
                    color=discord.Color.red(),
                )
                await channel.send(embed=embed)
                continue

            # 24-hour reminder
            time_left = deadline - now
            if timedelta(hours=23, minutes=30) <= time_left <= timedelta(hours=24, minutes=30):
                signups = sheets.get_signups_for_event(event_name)
                embed = discord.Embed(
                    title="Signup Reminder - 24 Hours Left!",
                    description=(
                        f"Signups for **{event_name}** close in ~24 hours!\n"
                        f"Currently **{len(signups)}** driver(s) signed up.\n"
                        f"Use `/signup` to sign up before it's too late."
                    ),
                    color=discord.Color.orange(),
                )
                await channel.send(embed=embed)

            # 1-hour reminder
            elif timedelta(minutes=30) <= time_left <= timedelta(hours=1, minutes=30):
                signups = sheets.get_signups_for_event(event_name)
                embed = discord.Embed(
                    title="LAST CALL - Signups Closing Soon!",
                    description=(
                        f"Signups for **{event_name}** close in ~1 hour!\n"
                        f"Currently **{len(signups)}** driver(s) signed up.\n"
                        f"Use `/signup` NOW if you want in."
                    ),
                    color=discord.Color.red(),
                )
                await channel.send(embed=embed)

    @check_deadlines.before_loop
    async def before_check_deadlines(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(RemindersCog(bot))
