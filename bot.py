import discord
from discord.ext import commands
import json
import datetime
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ui import View, Button
from math import ceil

# Define the directory paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')

# Create the data directory if it doesn't exist
os.makedirs(DATA_DIR, exist_ok=True)

# Load configuration from config.json in the data folder
config_file_path = os.path.join(DATA_DIR, 'config.json')
with open(config_file_path, 'r') as f:
    config = json.load(f)

# Define bot intents
intents = discord.Intents.all()

# Define bot token and prefix
TOKEN = config['token']
PREFIX = config['prefix']
GUILD_ID = config['guild_id']
ALLOWED_CHANNEL_IDS = config['allowed_channel_ids']

# Define bot
bot = commands.Bot(intents=intents, command_prefix=PREFIX)

# Load points data from points.json in the data folder
points_file_path = os.path.join(DATA_DIR, 'points.json')
if os.path.exists(points_file_path):
    with open(points_file_path, 'r') as f:
        points = json.load(f)
else:
    points = {}

# Save points data
def save_points():
    with open(points_file_path, 'w') as f:
        json.dump(points, f, indent=4)

# Backup points data
def backup_points():
    backup_file_path = os.path.join(DATA_DIR, 'points_backup.txt')
    with open(backup_file_path, 'w') as f:
        for guild_id, users in points.items():
            f.write(f"Guild ID: {guild_id}\n")
            for user_id, data in users.items():
                f.write(f"User ID: {user_id}, God Coins: {data['gc']}, Last Claimed: {data['last_claimed']}\n")
            f.write("\n")

# Daily reset
async def tick():
    try:
        guild = bot.get_guild(GUILD_ID)
        guild_id = str(guild.id)
        
        sorted_gc_data = sorted(points.get(str(guild_id), {}).items(), key=lambda x: x[1]['gc'], reverse=True)
        for idx, (user_id, data) in enumerate(sorted_gc_data, start=1):
            last_claimed = data['last_claimed']
            if not last_claimed:
                continue  # Skip if last_claimed is empty
            yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
            last_claimed_date = datetime.datetime.strptime(last_claimed, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            
            if last_claimed_date < yesterday:
                # print(f"Reset streak of {user_id}")
                # data['streak'] = 0
                data['last_claimed'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
                save_points()
    except Exception as e:
        print(f"Error in tick function: {e}")

# used for the streaks
# def clamp(n, minn, maxn):
#     return max(min(maxn, n), minn)

# used for the daily reset and streak
async def main():
    print('Starting main function...')
    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick, 'interval', seconds=86400)  # Run daily
    scheduler.start()
    print('Scheduler started.')
    
    # Use an asyncio event to keep the program running
    event = asyncio.Event()
    await event.wait()

# Command to claim daily GC
@bot.tree.command(name="claim", description="Claim your daily God Coins with this command.")
async def claim(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(ctx.user.id)

    if discord.utils.get(guild_member.roles, name='Member') or discord.utils.get(guild_member.roles, name='Trial'):
        guild_id = str(guild.id)
        user_id = str(guild_member.id)
        today = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
        now = datetime.datetime.now(datetime.timezone.utc)

        points.setdefault(guild_id, {})
        user_data = points[guild_id].setdefault(user_id, {"gc": 0, "last_claimed": ""})
        user_data.setdefault('gc', 0)

        if user_data['last_claimed']:
            last_claimed_date = datetime.datetime.strptime(user_data['last_claimed'], '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if last_claimed_date.date() >= now.date():
                next_claim_time = last_claimed_date + datetime.timedelta(days=1)
                next_claim_time_str = next_claim_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                await response.send_message(f'You have already claimed your daily God Coins for today, try again at {next_claim_time_str}', ephemeral=True)
                return

        # Commented out streak logic
        claim_gc = 10
        user_data['gc'] += claim_gc
        user_data['last_claimed'] = today
        save_points()
        await response.send_message(f"{ctx.user.mention} You claimed {claim_gc} God Coins successfully! Total God Coins: {user_data['gc']}", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)


############# CHECK PERSONAL GC + LEADERBOARD #############

# Command to display GC leaderboard
@bot.tree.command(name="leaderboard", description="Shows the leaderboard.")
async def leaderboard(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    if not guild:
        await response.send_message("Guild not found.", ephemeral=True)
        return

    sorted_gc_data = sorted(
    [(user_id, {**data, "gc": data.get("gc", 0)}) for user_id, data in points.get(str(guild_id), {}).items()],
    key=lambda x: x[1]["gc"],
    reverse=True
)
    leaderboard_entries = [
        f"{idx + 1}. {guild.get_member(int(user_id)).display_name if guild.get_member(int(user_id)) else 'Unknown User'}: {data['gc']} GC"
        for idx, (user_id, data) in enumerate(sorted_gc_data)
    ]

    # Pagination settings
    entries_per_page = 25
    total_pages = max(ceil(len(leaderboard_entries) / entries_per_page), 1)

    def get_page_content(page: int):
        start_idx = page * entries_per_page
        end_idx = start_idx + entries_per_page
        entries = leaderboard_entries[start_idx:end_idx]
        leaderboard_msg = f"**Of The Gods Clan GC Leaderboard** (Page {page + 1}/{total_pages})\n\n" + "\n".join(entries)
        return leaderboard_msg

    # Initial page setup
    current_page = 0
    message_content = get_page_content(current_page)

    # Create navigation buttons
    class LeaderboardView(View):
        def __init__(self):
            super().__init__()
            self.update_buttons()

        @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary, disabled=True)
        async def previous_button(self, interaction: discord.Interaction, button: Button):
            nonlocal current_page
            current_page -= 1
            message_content = get_page_content(current_page)
            self.update_buttons()
            await interaction.response.edit_message(content=message_content, view=self)

        @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
        async def next_button(self, interaction: discord.Interaction, button: Button):
            nonlocal current_page
            current_page += 1
            message_content = get_page_content(current_page)
            self.update_buttons()
            await interaction.response.edit_message(content=message_content, view=self)

        def update_buttons(self):
            self.children[0].disabled = current_page == 0
            self.children[1].disabled = current_page == total_pages - 1

    view = LeaderboardView()
    await response.send_message(message_content, view=view, ephemeral=True)

# Command to check user's GC
@bot.tree.command(name="gc", description="Shows your GC count.")
async def gc(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(ctx.user.id)
    guild_id = str(guild.id)
    user_id = str(guild_member.id)

    if discord.utils.get(guild_member.roles, name='Member') or discord.utils.get(guild_member.roles, name="Trial"):

        user_data = points.get(guild_id, {}).get(user_id)
        if user_data:
            await response.send_message(f"{guild_member.mention} You have {user_data['points']} God Coins.", ephemeral=True)
        else:
            await response.send_message(f"{guild_member.mention} You have no God Coins.", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

############# GOD COIN MANAGEMENT #############

# Command to give GC to others
@bot.tree.command(name="give", description='Give GC to a specific user.')
async def give(ctx, user: discord.User, amount: int, reason: str = None):
    response: discord.InteractionResponse = ctx.response
    # Check if the user has the Admin role
    if discord.utils.get(ctx.user.roles, name="Admin"):
        guild = bot.get_guild(GUILD_ID)

        # Check if the guild is found
        if not guild:
            await response.send_message("Guild not found.", ephemeral=True)
            return
        
        user_id = str(user.id)
        guild_id = str(guild.id)
        points.setdefault(guild_id, {})
        user_data = points[guild_id].setdefault(user_id, {'gc': 0, 'last_claimed': ''})
        user_data['gc'] += amount  # Add the GC to the user

        # Send a DM to the user
        try:
            dm_channel = await user.create_dm()
            dm_message = f"Hello {user.display_name},\n\nYou have received {amount} God Coins. "
            dm_message += f"Reason: {reason if reason else 'No reason provided.'}\n\nKeep being awesome!"
            await dm_channel.send(dm_message)
        except discord.Forbidden:
            # Handle the case where the bot cannot DM the user
            print(f"Could not send DM to {user.display_name} (ID: {user.id})")

        # Save the points after giving the GC
        save_points()

        # Notify the user who triggered the command
        await response.send_message(f"{amount} GC has been given to {user.display_name}.", ephemeral=True)
    else:
        # Notify if the user doesn't have the required permissions
        await response.send_message("You do not have the required permissions to use this command.", ephemeral=True)

# Command to give GC to all members with a specific role
@bot.tree.command(name="give_role_gc", description='Give GC to all members with a specific role.')
async def give_role_gc(ctx, role_name: str, amount: int, reason: str = None):
    response: discord.InteractionResponse = ctx.response
    # Check if the user has the Admin role
    if discord.utils.get(ctx.user.roles, name="Admin"):
        guild = bot.get_guild(GUILD_ID)
        
        # Check if the guild is found
        if not guild:
            await response.send_message("Guild not found.", ephemeral=True)
            return
        
        # Find the role by name
        role = discord.utils.get(guild.roles, name=role_name)
        
        # If role doesn't exist, notify the user
        if not role:
            await response.send_message(f"Role '{role_name}' not found in the server.", ephemeral=True)
            return
        
        members_with_role = [member for member in guild.members if role in member.roles]

        # If no members with the role, notify the user
        if not members_with_role:
            await response.send_message(f"No members found with the '{role_name}' role.", ephemeral=True)
            return
        
        # Defer the response to avoid timeout error if the operation is taking time
        await response.defer(ephemeral=True)

        # Add the specified amount of GC to each member with the role
        for member in members_with_role:
            user_id = str(member.id)
            guild_id = str(guild.id)
            points.setdefault(guild_id, {})
            user_data = points[guild_id].setdefault(user_id, {'gc': 0, 'last_claimed': ''})
            user_data['gc'] += amount  # Add the GC to the user

            # Send a DM to the user
            try:
                dm_channel = await member.create_dm()
                dm_message = f"Hello {member.display_name},\n\nYou have received {amount} God Coins from the server. "
                dm_message += f"Reason: {reason if reason else 'No reason provided.'}\n\nKeep being awesome!"
                await dm_channel.send(dm_message)
            except discord.Forbidden:
                # Handle the case where the bot cannot DM the user
                print(f"Could not send DM to {member.display_name} (ID: {member.id})")

        # Save changes after processing all members
        save_points()

        # Notify the user about the successful operation
        await response.send_message(f"{amount} GC has been given to all members with the '{role_name}' role.", ephemeral=True)
    else:
        # Notify if the user doesn't have the required permissions
        await response.send_message("You do not have the required permissions to use this command.", ephemeral=True)


############# RESETS #############

# Command to reset all God Coins
@bot.tree.command(name="reset_gc", description="Reset all GC points in the clan.")
async def reset_gc(ctx):
    response: discord.InteractionResponse = ctx.response
    if discord.utils.get(ctx.user.roles, name="Admin"):
        points.clear()
        save_points()
        await response.send_message("All God Coins have been reset.", ephemeral=True)

# Command to reset daily claims for all users
@bot.tree.command(name="reset_daily_claims", description="Reset daily claims.")
async def reset_daily_claims(ctx):

############# TO START UP THE BOT #############


    @bot.event
    async def on_ready():
        try:
            print('Bot is ready')
            await bot.tree.sync()
            print('Commands synced.')
            await main()  # Start the scheduler and other functions after the bot is ready
        except Exception as e:
         print(f"Error in on_ready or main function: {e}")

# Start the bot
bot.run(TOKEN)  # This should be outside the on_ready function