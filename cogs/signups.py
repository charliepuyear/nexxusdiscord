"""Signup commands — users sign up, edit, cancel, and view race signups."""
from __future__ import annotations

import io
import csv
import discord
from discord import app_commands
from discord.ext import commands
from config import ADMIN_ROLE
import sheets


def in_signup_channel():
    """Check that commands are used in a designated signup channel."""
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed = sheets.get_signup_channels()
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
        event = sheets.get_event(event_name)
        if not event:
            await interaction.response.send_message("Event not found.", ephemeral=True)
            return

        if self.mode == "signup":
            # Check if already signed up
            existing = sheets.get_user_signup_for_event(event_name, str(interaction.user.id))
            if existing:
                await interaction.response.send_message(
                    f"You're already signed up for **{event_name}**. "
                    f"Use `/edit-signup` to change your signup.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_modal(SignupModal(event))

        elif self.mode == "edit":
            existing = sheets.get_user_signup_for_event(event_name, str(interaction.user.id))
            if not existing:
                await interaction.response.send_message(
                    f"You don't have a signup for **{event_name}**.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_modal(EditSignupModal(event, existing))

        elif self.mode == "cancel":
            existing = sheets.get_user_signup_for_event(event_name, str(interaction.user.id))
            if not existing:
                await interaction.response.send_message(
                    f"You don't have a signup for **{event_name}**.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                f"Are you sure you want to cancel your signup for **{event_name}**?",
                view=ConfirmCancelView(event_name, interaction.user.id),
                ephemeral=True,
            )


# ── Step 2: Signup modal ──


class SignupModal(discord.ui.Modal, title="Race Signup"):
    def __init__(self, event: dict):
        super().__init__()
        self.event_name = event["Event Name"]
        classes = event["Classes"]
        cars = event["Cars"]
        timeslots = event["Timeslots"]

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
        self.available_slots = discord.ui.TextInput(
            label="Available timeslots",
            placeholder=f"Slots: {timeslots}"[:100],
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.preferred_slot = discord.ui.TextInput(
            label="Preferred timeslot",
            placeholder=f"Your top pick from: {timeslots}"[:100],
            max_length=200,
        )

        self.add_item(self.primary_class)
        self.add_item(self.secondary_class)
        self.add_item(self.cars_input)
        self.add_item(self.available_slots)
        self.add_item(self.preferred_slot)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            success = sheets.add_signup(
                event_name=self.event_name,
                discord_user=interaction.user.display_name,
                discord_id=str(interaction.user.id),
                primary_class=self.primary_class.value.strip(),
                secondary_class=self.secondary_class.value.strip() if self.secondary_class.value else "None",
                cars=self.cars_input.value.strip(),
                available_timeslots=self.available_slots.value.strip(),
                preferred_timeslot=self.preferred_slot.value.strip(),
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error saving signup: {e}", ephemeral=True,
            )
            return

        if not success:
            await interaction.response.send_message(
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
        embed.add_field(name="Available Slots", value=self.available_slots.value, inline=False)
        embed.add_field(name="Preferred Slot", value=self.preferred_slot.value, inline=True)

        await interaction.response.send_message(embed=embed)


# ── Edit signup modal ──


class EditSignupModal(discord.ui.Modal, title="Edit Your Signup"):
    def __init__(self, event: dict, existing: dict):
        super().__init__()
        self.event_name = event["Event Name"]
        classes = event["Classes"]
        cars = event["Cars"]
        timeslots = event["Timeslots"]

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
        self.available_slots = discord.ui.TextInput(
            label="Available timeslots",
            placeholder=f"Slots: {timeslots}"[:100],
            default=str(existing["Available Timeslots"]),
            style=discord.TextStyle.paragraph,
            max_length=500,
        )
        self.preferred_slot = discord.ui.TextInput(
            label="Preferred timeslot",
            default=str(existing["Preferred Timeslot"]),
            max_length=200,
        )

        self.add_item(self.primary_class)
        self.add_item(self.secondary_class)
        self.add_item(self.cars_input)
        self.add_item(self.available_slots)
        self.add_item(self.preferred_slot)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            sheets.update_signup(
                event_name=self.event_name,
                discord_id=str(interaction.user.id),
                primary_class=self.primary_class.value.strip(),
                secondary_class=self.secondary_class.value.strip() if self.secondary_class.value else "None",
                cars=self.cars_input.value.strip(),
                available_timeslots=self.available_slots.value.strip(),
                preferred_timeslot=self.preferred_slot.value.strip(),
            )
        except Exception as e:
            await interaction.response.send_message(
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
        embed.add_field(name="Available Slots", value=self.available_slots.value, inline=False)
        embed.add_field(name="Preferred Slot", value=self.preferred_slot.value, inline=True)

        await interaction.response.send_message(embed=embed)


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
        success = sheets.cancel_signup(self.event_name, str(interaction.user.id))
        if success:
            await _remove_event_role(interaction, self.event_name)
            await interaction.response.edit_message(
                content=f"Your signup for **{self.event_name}** has been cancelled.",
                view=None,
            )
        else:
            await interaction.response.edit_message(
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
        events = sheets.get_open_events()
        if not events:
            await interaction.response.send_message(
                "There are no open events to sign up for right now.",
                ephemeral=True,
            )
            return

        view = EventSelectView(events, interaction.user.id, mode="signup")
        await interaction.response.send_message(
            "Select the event you want to sign up for:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="edit-signup", description="Edit your existing signup")
    @in_signup_channel()
    async def edit_signup(self, interaction: discord.Interaction):
        # Show only events the user has signed up for
        user_signups = sheets.get_user_signups(str(interaction.user.id))
        if not user_signups:
            await interaction.response.send_message(
                "You don't have any active signups.", ephemeral=True,
            )
            return

        # Build event list from user's signups, only open events
        open_events = sheets.get_open_events()
        open_event_names = {e["Event Name"] for e in open_events}
        signed_up_events = [
            {"Event Name": s["Event Name"]}
            for s in user_signups
            if s["Event Name"] in open_event_names
        ]

        if not signed_up_events:
            await interaction.response.send_message(
                "You have no editable signups (events may be closed).",
                ephemeral=True,
            )
            return

        view = EventSelectView(signed_up_events, interaction.user.id, mode="edit")
        await interaction.response.send_message(
            "Select the event signup you want to edit:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="cancel-signup", description="Cancel your signup for an event")
    @in_signup_channel()
    async def cancel_signup(self, interaction: discord.Interaction):
        user_signups = sheets.get_user_signups(str(interaction.user.id))
        if not user_signups:
            await interaction.response.send_message(
                "You don't have any active signups.", ephemeral=True,
            )
            return

        events = [{"Event Name": s["Event Name"]} for s in user_signups]
        view = EventSelectView(events, interaction.user.id, mode="cancel")
        await interaction.response.send_message(
            "Select the event signup you want to cancel:",
            view=view,
            ephemeral=True,
        )

    @app_commands.command(name="my-signups", description="View your current signups")
    @in_signup_channel()
    async def my_signups(self, interaction: discord.Interaction):
        signups = sheets.get_user_signups(str(interaction.user.id))
        if not signups:
            await interaction.response.send_message(
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

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="view-signups", description="View all signups for an event")
    @app_commands.describe(event_name="Name of the event")
    @in_signup_channel()
    async def view_signups(self, interaction: discord.Interaction, event_name: str):
        signups = sheets.get_signups_for_event(event_name)
        if not signups:
            await interaction.response.send_message(
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

        await interaction.response.send_message(embed=embed)

    @view_signups.autocomplete("event_name")
    async def view_signups_autocomplete(self, interaction: discord.Interaction, current: str):
        events = sheets.get_all_events()
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]

    @app_commands.command(name="export-signups", description="Export signups to CSV (Admin only)")
    @app_commands.describe(event_name="Name of the event to export")
    @is_admin()
    async def export_signups(self, interaction: discord.Interaction, event_name: str):
        signups = sheets.get_signups_for_event(event_name)
        if not signups:
            await interaction.response.send_message(
                f"No signups found for **{event_name}**.", ephemeral=True,
            )
            return

        # Build CSV in memory
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=sheets.SIGNUP_HEADERS)
        writer.writeheader()
        for s in signups:
            writer.writerow(s)

        output.seek(0)
        filename = f"{event_name.replace(' ', '_')}_signups.csv"
        file = discord.File(io.BytesIO(output.getvalue().encode()), filename=filename)

        await interaction.response.send_message(
            f"Signups for **{event_name}** ({len(signups)} drivers):",
            file=file,
        )

    @export_signups.autocomplete("event_name")
    async def export_signups_autocomplete(self, interaction: discord.Interaction, current: str):
        events = sheets.get_all_events()
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(SignupsCog(bot))
