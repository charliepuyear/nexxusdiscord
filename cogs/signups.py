"""Signup commands — users sign up, edit, cancel, and view race signups."""
from __future__ import annotations

import asyncio
import io
import csv
import discord
from discord import app_commands
from discord.ext import commands
from config import ADMIN_ROLE
import sheets


def _run_sync(func, *args):
    """Run a blocking function in a thread so it doesn't block the event loop."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, func, *args)


def in_signup_channel():
    """Check that commands are used in a designated signup channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed = await _run_sync(sheets.get_signup_channels)
        if allowed and interaction.channel_id not in allowed:
            channel_mentions = ", ".join(f"<#{ch}>" for ch in allowed)
            await interaction.response.send_message(
                f"This command can only be used in: {channel_mentions}",
                ephemeral=True,
            )
            return False
        return True
    return app_commands.check(predicate)


def is_admin():
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member):
            return any(role.name == ADMIN_ROLE for role in interaction.user.roles)
        return False
    return app_commands.check(predicate)


# ── Role helpers ──


async def _assign_event_role(interaction: discord.Interaction, event_name: str):
    """Create an event role if needed and assign it to the user."""
    guild = interaction.guild
    if not guild:
        return
    role_name = f"Event: {event_name}"
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        try:
            role = await guild.create_role(
                name=role_name,
                mentionable=True,
                reason=f"Auto-created for race event: {event_name}",
            )
        except discord.Forbidden:
            print(f"Missing permissions to create role: {role_name}")
            return
    try:
        await interaction.user.add_roles(role, reason=f"Signed up for {event_name}")
    except discord.Forbidden:
        print(f"Missing permissions to assign role: {role_name}")


async def _remove_event_role(interaction: discord.Interaction, event_name: str):
    """Remove the event role from the user."""
    guild = interaction.guild
    if not guild:
        return
    role_name = f"Event: {event_name}"
    role = discord.utils.get(guild.roles, name=role_name)
    if role and role in interaction.user.roles:
        try:
            await interaction.user.remove_roles(role, reason=f"Cancelled signup for {event_name}")
        except discord.Forbidden:
            print(f"Missing permissions to remove role: {role_name}")


# ── Step 1: Select event via dropdown ──


class EventSelectView(discord.ui.View):
    """Dropdown to pick which event to sign up for."""

    def __init__(self, events: list[dict], user_id: int, mode: str = "signup"):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.mode = mode

        options = [
            discord.SelectOption(label=e["Event Name"], value=e["Event Name"])
            for e in events
        ]
        select = EventSelect(options=options, mode=mode)
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your signup flow.", ephemeral=True,
            )
            return False
        return True


class EventSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], mode: str):
        self.mode = mode
        super().__init__(
            placeholder="Select an event...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        event_name = self.values[0]

        # Defer immediately so Discord knows we're working on it
        await interaction.response.defer(ephemeral=True)

        event = await _run_sync(sheets.get_event, event_name)
        if not event:
            await interaction.followup.send("Event not found.", ephemeral=True)
            return

        if self.mode == "signup":
            existing = await _run_sync(sheets.get_user_signup_for_event, event_name, str(interaction.user.id))
            if existing:
                await interaction.followup.send(
                    f"You're already signed up for **{event_name}**. "
                    f"Use `/edit-signup` to change your signup.",
                    ephemeral=True,
                )
                return
            # Step 2: Show timeslot selection
            view = TimeslotSelectView(event, interaction.user.id, mode="signup")
            await interaction.edit_original_response(
                content=f"**{event_name}** — Select your available timeslots:",
                view=view,
            )

        elif self.mode == "edit":
            existing = await _run_sync(sheets.get_user_signup_for_event, event_name, str(interaction.user.id))
            if not existing:
                await interaction.followup.send(
                    f"You don't have a signup for **{event_name}**.",
                    ephemeral=True,
                )
                return
            view = TimeslotSelectView(event, interaction.user.id, mode="edit", existing=existing)
            await interaction.edit_original_response(
                content=f"**{event_name}** — Update your available timeslots:",
                view=view,
            )

        elif self.mode == "cancel":
            existing = await _run_sync(sheets.get_user_signup_for_event, event_name, str(interaction.user.id))
            if not existing:
                await interaction.followup.send(
                    f"You don't have a signup for **{event_name}**.",
                    ephemeral=True,
                )
                return
            await interaction.edit_original_response(
                content=f"Are you sure you want to cancel your signup for **{event_name}**?",
                view=ConfirmCancelView(event_name, interaction.user.id),
            )


# ── Step 2: Timeslot selection via dropdowns ──


class TimeslotSelectView(discord.ui.View):
    """Multi-select for available timeslots + single-select for preferred."""

    def __init__(self, event: dict, user_id: int, mode: str = "signup", existing: dict = None):
        super().__init__(timeout=180)
        self.event = event
        self.user_id = user_id
        self.mode = mode
        self.existing = existing
        self.selected_available = []
        self.selected_preferred = None

        timeslot_strs = [s.strip() for s in str(event["Timeslots"]).split(",") if s.strip()]

        # Figure out which slots were previously selected (for edit mode)
        prev_available = []
        if existing:
            prev_available = [s.strip() for s in str(existing["Available Timeslots"]).split(",") if s.strip()]

        # Multi-select for available timeslots
        available_options = []
        for slot in timeslot_strs:
            opt = discord.SelectOption(label=slot, value=slot)
            if slot in prev_available:
                opt.default = True
            available_options.append(opt)

        self.available_select = discord.ui.Select(
            placeholder="Select ALL timeslots you're available for...",
            min_values=1,
            max_values=len(timeslot_strs),
            options=available_options,
            row=0,
        )
        self.available_select.callback = self.on_available_select
        self.add_item(self.available_select)

        # Single-select for preferred timeslot
        preferred_options = [discord.SelectOption(label=slot, value=slot) for slot in timeslot_strs]
        self.preferred_select = discord.ui.Select(
            placeholder="Select your PREFERRED timeslot...",
            min_values=1,
            max_values=1,
            options=preferred_options,
            row=1,
        )
        self.preferred_select.callback = self.on_preferred_select
        self.add_item(self.preferred_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "This isn't your signup flow.", ephemeral=True,
            )
            return False
        return True

    async def on_available_select(self, interaction: discord.Interaction):
        self.selected_available = self.available_select.values
        if self.selected_preferred:
            await self._proceed(interaction)
        else:
            await interaction.response.edit_message(
                content=f"**{self.event['Event Name']}** — Available: {', '.join(self.selected_available)}\nNow select your **preferred** timeslot:",
                view=self,
            )

    async def on_preferred_select(self, interaction: discord.Interaction):
        self.selected_preferred = self.preferred_select.values[0]
        if self.selected_available:
            await self._proceed(interaction)
        else:
            await interaction.response.edit_message(
                content=f"**{self.event['Event Name']}** — Preferred: {self.selected_preferred}\nNow select **all timeslots you're available** for:",
                view=self,
            )

    async def _proceed(self, interaction: discord.Interaction):
        """Both selects are done — open the class/car modal."""
        if self.mode == "signup":
            modal = SignupModal(
                self.event,
                available_timeslots=", ".join(self.selected_available),
                preferred_timeslot=self.selected_preferred,
            )
            await interaction.response.send_modal(modal)
        elif self.mode == "edit":
            modal = EditSignupModal(
                self.event,
                self.existing,
                available_timeslots=", ".join(self.selected_available),
                preferred_timeslot=self.selected_preferred,
            )
            await interaction.response.send_modal(modal)


# ── Step 3: Class/Car modal ──


class SignupModal(discord.ui.Modal, title="Race Signup"):
    def __init__(self, event: dict, available_timeslots: str, preferred_timeslot: str):
        super().__init__()
        self.event_name = event["Event Name"]
        self.available_timeslots = available_timeslots
        self.preferred_timeslot = preferred_timeslot
        classes = event["Classes"]
        cars = event["Cars"]

        self.primary_class = discord.ui.TextInput(
            label="Primary Class",
            placeholder=f"Choose from: {classes}"[:100],
            max_length=100,
        )
        self.secondary_class = discord.ui.TextInput(
            label="Secondary Class (optional)",
            placeholder=f"Choose from: {classes}"[:100],
            required=False,
            max_length=100,
        )
        self.cars_input = discord.ui.TextInput(
            label="Car(s) you want to drive",
            placeholder=f"Available: {cars}"[:100],
            style=discord.TextStyle.paragraph,
            max_length=500,
        )

        self.add_item(self.primary_class)
        self.add_item(self.secondary_class)
        self.add_item(self.cars_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Defer so the Sheets write doesn't time us out
        await interaction.response.defer()

        try:
            success = await _run_sync(
                sheets.add_signup,
                self.event_name,
                interaction.user.display_name,
                str(interaction.user.id),
                self.primary_class.value.strip(),
                self.secondary_class.value.strip() if self.secondary_class.value else "None",
                self.cars_input.value.strip(),
                self.available_timeslots,
                self.preferred_timeslot,
            )
        except Exception as e:
            await interaction.followup.send(
                f"Error saving signup: {e}", ephemeral=True,
            )
            return

        if not success:
            await interaction.followup.send(
                f"You're already signed up for **{self.event_name}**.",
                ephemeral=True,
            )
            return

        # Auto-assign event role
        await _assign_event_role(interaction, self.event_name)

        embed = discord.Embed(
            title="Signup Confirmed!",
            description=f"**{interaction.user.display_name}** signed up for **{self.event_name}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Primary Class", value=self.primary_class.value, inline=True)
        if self.secondary_class.value:
            embed.add_field(name="Secondary Class", value=self.secondary_class.value, inline=True)
        embed.add_field(name="Car(s)", value=self.cars_input.value, inline=False)
        embed.add_field(name="Available Slots", value=self.available_timeslots, inline=False)
        embed.add_field(name="Preferred Slot", value=self.preferred_timeslot, inline=True)

        await interaction.followup.send(embed=embed)


# ── Edit signup modal ──


class EditSignupModal(discord.ui.Modal, title="Edit Your Signup"):
    def __init__(self, event: dict, existing: dict, available_timeslots: str, preferred_timeslot: str):
        super().__init__()
        self.event_name = event["Event Name"]
        self.available_timeslots = available_timeslots
        self.preferred_timeslot = preferred_timeslot
        classes = event["Classes"]
        cars = event["Cars"]

        self.primary_class = discord.ui.TextInput(
            label="Primary Class",
            placeholder=f"Choose from: {classes}"[:100],
            default=str(existing["Primary Class"]),
            max_length=100,
        )
        self.secondary_class = discord.ui.TextInput(
            label="Secondary Class (optional)",
            placeholder=f"Choose from: {classes}"[:100],
            default=str(existing["Secondary Class"]),
            required=False,
            max_length=100,
        )
        self.cars_input = discord.ui.TextInput(
            label="Car(s) you want to drive",
            placeholder=f"Available: {cars}"[:100],
            default=str(existing["Cars"]),
            style=discord.TextStyle.paragraph,
            max_length=500,
        )

        self.add_item(self.primary_class)
        self.add_item(self.secondary_class)
        self.add_item(self.cars_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            await _run_sync(
                sheets.update_signup,
                self.event_name,
                str(interaction.user.id),
                self.primary_class.value.strip(),
                self.secondary_class.value.strip() if self.secondary_class.value else "None",
                self.cars_input.value.strip(),
                self.available_timeslots,
                self.preferred_timeslot,
            )
        except Exception as e:
            await interaction.followup.send(
                f"Error updating signup: {e}", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Signup Updated!",
            description=f"**{interaction.user.display_name}**'s signup for **{self.event_name}** has been updated.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Primary Class", value=self.primary_class.value, inline=True)
        if self.secondary_class.value:
            embed.add_field(name="Secondary Class", value=self.secondary_class.value, inline=True)
        embed.add_field(name="Car(s)", value=self.cars_input.value, inline=False)
        embed.add_field(name="Available Slots", value=self.available_timeslots, inline=False)
        embed.add_field(name="Preferred Slot", value=self.preferred_timeslot, inline=True)

        await interaction.followup.send(embed=embed)


# ── Cancel confirmation ──


class ConfirmCancelView(discord.ui.View):
    def __init__(self, event_name: str, user_id: int):
        super().__init__(timeout=60)
        self.event_name = event_name
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    @discord.ui.button(label="Yes, cancel my signup", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        success = await _run_sync(sheets.cancel_signup, self.event_name, str(interaction.user.id))
        if success:
            await _remove_event_role(interaction, self.event_name)
            await interaction.edit_original_response(
                content=f"Your signup for **{self.event_name}** has been cancelled.",
                view=None,
            )
        else:
            await interaction.edit_original_response(
                content="Could not find your signup to cancel.",
                view=None,
            )

    @discord.ui.button(label="No, keep it", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Signup cancellation aborted.", view=None,
        )


# ── Cog with slash commands ──


class SignupsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="signup", description="Sign up for a race event")
    @in_signup_channel()
    async def signup(self, interaction: discord.Interaction):
        # Defer immediately — Sheets calls are slow
        await interaction.response.defer(ephemeral=True)

        events = await _run_sync(sheets.get_open_events)
        if not events:
            await interaction.followup.send(
                "There are no open events to sign up for right now.",
                ephemeral=True,
            )
            return

        view = EventSelectView(events, interaction.user.id, mode="signup")
        await interaction.followup.send(
            "Select the event you want to sign up for:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="edit-signup", description="Edit your existing signup")
    @in_signup_channel()
    async def edit_signup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_signups = await _run_sync(sheets.get_user_signups, str(interaction.user.id))
        if not user_signups:
            await interaction.followup.send(
                "You don't have any active signups.", ephemeral=True,
            )
            return

        open_events = await _run_sync(sheets.get_open_events)
        open_event_names = {e["Event Name"] for e in open_events}
        signed_up_events = [
            {"Event Name": s["Event Name"]}
            for s in user_signups
            if s["Event Name"] in open_event_names
        ]

        if not signed_up_events:
            await interaction.followup.send(
                "You have no editable signups (events may be closed).",
                ephemeral=True,
            )
            return

        view = EventSelectView(signed_up_events, interaction.user.id, mode="edit")
        await interaction.followup.send(
            "Select the event signup you want to edit:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="cancel-signup", description="Cancel your signup for an event")
    @in_signup_channel()
    async def cancel_signup(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        user_signups = await _run_sync(sheets.get_user_signups, str(interaction.user.id))
        if not user_signups:
            await interaction.followup.send(
                "You don't have any active signups.", ephemeral=True,
            )
            return

        events = [{"Event Name": s["Event Name"]} for s in user_signups]
        view = EventSelectView(events, interaction.user.id, mode="cancel")
        await interaction.followup.send(
            "Select the event signup you want to cancel:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="my-signups", description="View your current signups")
    @in_signup_channel()
    async def my_signups(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        signups = await _run_sync(sheets.get_user_signups, str(interaction.user.id))
        if not signups:
            await interaction.followup.send(
                "You don't have any signups.", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"{interaction.user.display_name}'s Signups",
            color=discord.Color.purple(),
        )
        for s in signups:
            secondary = f"\nSecondary: {s['Secondary Class']}" if s["Secondary Class"] != "None" else ""
            embed.add_field(
                name=s["Event Name"],
                value=(
                    f"Primary: {s['Primary Class']}{secondary}\n"
                    f"Cars: {s['Cars']}\n"
                    f"Available: {s['Available Timeslots']}\n"
                    f"Preferred: {s['Preferred Timeslot']}"
                ),
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name="view-signups", description="View all signups for an event")
    @app_commands.describe(event_name="Name of the event")
    @in_signup_channel()
    async def view_signups(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer()

        signups = await _run_sync(sheets.get_signups_for_event, event_name)
        if not signups:
            await interaction.followup.send(
                f"No signups found for **{event_name}**.", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title=f"Signups for {event_name}",
            description=f"**{len(signups)}** driver(s) signed up",
            color=discord.Color.gold(),
        )
        for s in signups:
            secondary = f" / {s['Secondary Class']}" if s["Secondary Class"] != "None" else ""
            embed.add_field(
                name=s["Discord User"],
                value=(
                    f"Class: {s['Primary Class']}{secondary}\n"
                    f"Cars: {s['Cars']}\n"
                    f"Preferred Slot: {s['Preferred Timeslot']}"
                ),
                inline=True,
            )

        await interaction.followup.send(embed=embed)

    @view_signups.autocomplete("event_name")
    async def view_signups_autocomplete(self, interaction: discord.Interaction, current: str):
        events = await _run_sync(sheets.get_all_events)
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]

    @app_commands.command(name="export-signups", description="Export signups to CSV (Admin only)")
    @app_commands.describe(event_name="Name of the event to export")
    @is_admin()
    async def export_signups(self, interaction: discord.Interaction, event_name: str):
        await interaction.response.defer(ephemeral=True)

        signups = await _run_sync(sheets.get_signups_for_event, event_name)
        if not signups:
            await interaction.followup.send(
                f"No signups found for **{event_name}**.", ephemeral=True,
            )
            return

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sheets.SIGNUP_HEADERS)
        writer.writeheader()
        for s in signups:
            writer.writerow(s)

        output.seek(0)
        filename = f"{event_name.replace(' ', '_')}_signups.csv"
        file = discord.File(io.BytesIO(output.getvalue().encode()), filename=filename)

        await interaction.followup.send(
            f"Signups for **{event_name}** ({len(signups)} drivers):",
            file=file,
        )

    @export_signups.autocomplete("event_name")
    async def export_signups_autocomplete(self, interaction: discord.Interaction, current: str):
        events = await _run_sync(sheets.get_all_events)
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(SignupsCog(bot))
