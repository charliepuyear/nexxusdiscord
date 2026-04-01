"""Admin commands for managing race events."""

import discord
from discord import app_commands
from discord.ext import commands
from config import ADMIN_ROLE, SIGNUP_CHANNEL_ID, DEFAULT_TIMESLOTS
import sheets


def is_admin():
    """Check if user has the admin role."""
    async def predicate(interaction: discord.Interaction) -> bool:
        if isinstance(interaction.user, discord.Member):
            if any(role.name == ADMIN_ROLE for role in interaction.user.roles):
                return True
        await interaction.response.send_message(
            f"You need the **{ADMIN_ROLE}** role to use this command.",
            ephemeral=True,
        )
        return False
    return app_commands.check(predicate)


class CreateEventModal(discord.ui.Modal, title="Create Race Event"):
    event_name = discord.ui.TextInput(
        label="Event Name",
        placeholder="e.g., Sebring 12 Hour",
        max_length=100,
    )
    classes = discord.ui.TextInput(
        label="Classes (comma-separated)",
        placeholder="e.g., LMP2, GTP, GT3",
        max_length=500,
    )
    cars = discord.ui.TextInput(
        label="Cars (comma-separated)",
        placeholder="e.g., Cadillac GTP, Porsche 963, Dallara LMP2",
        style=discord.TextStyle.paragraph,
        max_length=1000,
    )
    timeslots = discord.ui.TextInput(
        label="Timeslots (comma-separated, or leave for defaults)",
        placeholder="e.g., Slot 1 - Fri Eve, Slot 2 - Sat Morn",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000,
    )
    deadline = discord.ui.TextInput(
        label="Signup Deadline (YYYY-MM-DD HH:MM)",
        placeholder="e.g., 2026-04-15 18:00",
        max_length=20,
        required=False,
    )

    async def on_submit(self, interaction: discord.Interaction):
        name = self.event_name.value.strip()
        class_list = [c.strip() for c in self.classes.value.split(",") if c.strip()]
        car_list = [c.strip() for c in self.cars.value.split(",") if c.strip()]

        if self.timeslots.value and self.timeslots.value.strip():
            slot_list = [s.strip() for s in self.timeslots.value.split(",") if s.strip()]
        else:
            slot_list = DEFAULT_TIMESLOTS

        deadline = self.deadline.value.strip() if self.deadline.value else "None"

        try:
            success = sheets.add_event(
                name=name,
                classes=class_list,
                cars=car_list,
                timeslots=slot_list,
                deadline=deadline,
                created_by=str(interaction.user),
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error creating event: {e}", ephemeral=True,
            )
            return

        if not success:
            await interaction.response.send_message(
                f"An event named **{name}** already exists.", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="New Race Event Created!",
            description=f"**{name}**",
            color=discord.Color.green(),
        )
        embed.add_field(name="Classes", value=", ".join(class_list), inline=False)
        embed.add_field(name="Cars", value=", ".join(car_list), inline=False)
        embed.add_field(name="Timeslots", value="\n".join(f"• {s}" for s in slot_list), inline=False)
        if deadline != "None":
            embed.add_field(name="Signup Deadline", value=deadline, inline=False)
        embed.set_footer(text=f"Created by {interaction.user.display_name}")

        await interaction.response.send_message(embed=embed)


class EditEventModal(discord.ui.Modal, title="Edit Race Event"):
    def __init__(self, event: dict):
        super().__init__()
        self.event_name = event["Event Name"]

        self.classes = discord.ui.TextInput(
            label="Classes (comma-separated)",
            default=event["Classes"],
            max_length=500,
        )
        self.cars = discord.ui.TextInput(
            label="Cars (comma-separated)",
            default=event["Cars"],
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.timeslots = discord.ui.TextInput(
            label="Timeslots (comma-separated)",
            default=event["Timeslots"],
            style=discord.TextStyle.paragraph,
            max_length=1000,
        )
        self.deadline = discord.ui.TextInput(
            label="Signup Deadline (YYYY-MM-DD HH:MM)",
            default=str(event["Deadline"]),
            max_length=20,
            required=False,
        )
        self.add_item(self.classes)
        self.add_item(self.cars)
        self.add_item(self.timeslots)
        self.add_item(self.deadline)

    async def on_submit(self, interaction: discord.Interaction):
        class_list = [c.strip() for c in self.classes.value.split(",") if c.strip()]
        car_list = [c.strip() for c in self.cars.value.split(",") if c.strip()]
        slot_list = [s.strip() for s in self.timeslots.value.split(",") if s.strip()]
        deadline = self.deadline.value.strip() if self.deadline.value else "None"

        try:
            sheets.update_event(
                name=self.event_name,
                classes=class_list,
                cars=car_list,
                timeslots=slot_list,
                deadline=deadline,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error updating event: {e}", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Event Updated",
            description=f"**{self.event_name}** has been updated.",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Classes", value=", ".join(class_list), inline=False)
        embed.add_field(name="Cars", value=", ".join(car_list), inline=False)
        embed.add_field(name="Timeslots", value="\n".join(f"• {s}" for s in slot_list), inline=False)
        embed.add_field(name="Deadline", value=deadline, inline=False)

        await interaction.response.send_message(embed=embed)


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="create-event", description="Create a new race event (Admin only)")
    @is_admin()
    async def create_event(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreateEventModal())

    @app_commands.command(name="edit-event", description="Edit an existing race event (Admin only)")
    @app_commands.describe(event_name="Name of the event to edit")
    @is_admin()
    async def edit_event(self, interaction: discord.Interaction, event_name: str):
        event = sheets.get_event(event_name)
        if not event:
            await interaction.response.send_message(
                f"Event **{event_name}** not found.", ephemeral=True,
            )
            return
        await interaction.response.send_modal(EditEventModal(event))

    @edit_event.autocomplete("event_name")
    async def edit_event_autocomplete(self, interaction: discord.Interaction, current: str):
        events = sheets.get_all_events()
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]

    @app_commands.command(name="close-event", description="Close signups for an event (Admin only)")
    @app_commands.describe(event_name="Name of the event to close")
    @is_admin()
    async def close_event(self, interaction: discord.Interaction, event_name: str):
        success = sheets.close_event(event_name)
        if success:
            embed = discord.Embed(
                title="Event Closed",
                description=f"Signups for **{event_name}** are now closed.",
                color=discord.Color.red(),
            )
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                f"Event **{event_name}** not found.", ephemeral=True,
            )

    @close_event.autocomplete("event_name")
    async def close_event_autocomplete(self, interaction: discord.Interaction, current: str):
        events = sheets.get_open_events()
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]

    @app_commands.command(name="delete-event", description="Delete an event and all signups (Admin only)")
    @app_commands.describe(event_name="Name of the event to delete")
    @is_admin()
    async def delete_event(self, interaction: discord.Interaction, event_name: str):
        success = sheets.delete_event(event_name)
        if success:
            await interaction.response.send_message(
                f"Event **{event_name}** and all associated signups have been deleted.",
            )
        else:
            await interaction.response.send_message(
                f"Event **{event_name}** not found.", ephemeral=True,
            )

    @delete_event.autocomplete("event_name")
    async def delete_event_autocomplete(self, interaction: discord.Interaction, current: str):
        events = sheets.get_all_events()
        return [
            app_commands.Choice(name=e["Event Name"], value=e["Event Name"])
            for e in events
            if current.lower() in e["Event Name"].lower()
        ][:25]

    @app_commands.command(name="list-events", description="List all race events")
    async def list_events(self, interaction: discord.Interaction):
        events = sheets.get_all_events()
        if not events:
            await interaction.response.send_message("No events found.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Race Events",
            color=discord.Color.gold(),
        )
        for event in events:
            status_emoji = "🟢" if event["Status"] == "Open" else "🔴"
            deadline_text = f"\nDeadline: {event['Deadline']}" if event["Deadline"] != "None" else ""
            embed.add_field(
                name=f"{status_emoji} {event['Event Name']}",
                value=f"Classes: {event['Classes']}\nCars: {event['Cars']}{deadline_text}",
                inline=False,
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="setup-sheets", description="Initialize Google Sheets worksheets (Admin only)")
    @is_admin()
    async def setup_sheets(self, interaction: discord.Interaction):
        try:
            sheets.ensure_worksheets()
            await interaction.response.send_message(
                "Google Sheets worksheets have been set up successfully!",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"Error setting up sheets: {e}", ephemeral=True,
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
