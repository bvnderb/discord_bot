import discord
from discord.ext import commands
import json
import datetime
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from discord.ui import View, Button
from math import ceil
import asyncio


############# CORE FUNCTIONS - directory paths, create paths and files, bot intents, backup, etc... #############
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

# Define file paths for tracking GC
gc_file_path = os.path.join(DATA_DIR, 'gc.json')
lttgc_file_path = os.path.join(DATA_DIR, 'lttgc.json')

# Initialize GC data files if they don't exist
if not os.path.exists(gc_file_path):
    with open(gc_file_path, 'w') as f:
        json.dump({}, f, indent=4)

if not os.path.exists(lttgc_file_path):
    with open(lttgc_file_path, 'w') as f:
        json.dump({}, f, indent=4)

# Load points data from JSON files
with open(gc_file_path, 'r') as f:
    gc_data = json.load(f)

with open(lttgc_file_path, 'r') as f:
    lttgc_data = json.load(f)

# Save points data to files
def save_gc():
    with open(gc_file_path, 'w') as f:
        json.dump(gc_data, f, indent=4)

def save_lttgc():
    with open(lttgc_file_path, 'w') as f:
        json.dump(lttgc_data, f, indent=4)

# Backup points data
def backup_points():
    backup_file_path = os.path.join(DATA_DIR, 'points_backup.txt')
    with open(backup_file_path, 'w') as f:
        for guild_id, users in gc_data.items():
            f.write(f"Guild ID: {guild_id}\n")
            for user_id, data in users.items():
                f.write(f"User ID: {user_id}, Balance GC: {data['gc']}, Lifetime GC: {lttgc_data[guild_id].get(user_id, 0)}\n")
            f.write("\n")

############# CORE COMMAND - CLAIM #############

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

        # Ensure lttgc_data has the guild_id and user_id initialized
        lttgc_data.setdefault(guild_id, {})
        lttgc_data[guild_id].setdefault(user_id, 0)  # Initialize user lifetime GC if not present

        gc_data.setdefault(guild_id, {})
        user_data = gc_data[guild_id].setdefault(user_id, {"gc": 0, "last_claimed": ""})
        user_data.setdefault('gc', 0)

        if user_data['last_claimed']:
            last_claimed_date = datetime.datetime.strptime(user_data['last_claimed'], '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if last_claimed_date.date() >= now.date():
                next_claim_time = last_claimed_date + datetime.timedelta(days=1)
                next_claim_time_str = next_claim_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                await response.send_message(f'You have already claimed your daily God Coins for today, try again at {next_claim_time_str}', ephemeral=True)
                return

        claim_gc = 10
        user_data['gc'] += claim_gc
        lttgc_data[guild_id][user_id] += claim_gc  # Add claim_gc to user's lifetime GC
        user_data['last_claimed'] = today
        save_gc()
        save_lttgc()
        await response.send_message(f"{ctx.user.mention} You claimed {claim_gc} God Coins successfully! Total GC balance: {user_data['gc']}", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

                                    ############# LOGIC FOR THE DAILY RESET #############

# daily reset to check if already been claimed
async def tick():
    try:
        guild = bot.get_guild(GUILD_ID)
        guild_id = str(guild.id)
        
        sorted_gc_data = sorted(gc_data.get(guild_id, {}).items(), key=lambda x: x[1]['gc'], reverse=True)
        for idx, (user_id, data) in enumerate(sorted_gc_data, start=1):
            last_claimed = data['last_claimed']
            if not last_claimed:
                continue  # Skip if last_claimed is empty
            yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
            last_claimed_date = datetime.datetime.strptime(last_claimed, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            
            if last_claimed_date < yesterday:
                data['last_claimed'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
                save_gc()
    except Exception as e:
        print(f"Error in tick function: {e}")

# used for the daily resets
async def main():
    print('Starting main function...')
    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick, 'interval', seconds=86400)  # Run daily
    scheduler.start()
    print('Scheduler started.')
    
    # Use an asyncio event to keep the program running
    event = asyncio.Event()
    await event.wait()


############# GC MANAGEMENT - give, deduct, reset #############

# Command to give GC to others (user)
@bot.tree.command(name="give", description='Give GC to a specific user.')
async def give(ctx, user: discord.User, amount: int, reason: str = None):
    response: discord.InteractionResponse = ctx.response
    if discord.utils.get(ctx.user.roles, name="Admin"):
        guild = bot.get_guild(GUILD_ID)

        if not guild:
            await response.send_message("Guild not found.", ephemeral=True)
            return
        
        if amount < 0:
            await response.send_message("You cannot give a negative amount of God Coins.", ephemeral=True)
            return

        user_id = str(user.id)
        guild_id = str(guild.id)
        gc_data.setdefault(guild_id, {})
        user_data = gc_data[guild_id].setdefault(user_id, {'gc': 0, 'last_claimed': ''})

        user_data['gc'] += amount
        lttgc_data[guild_id][user_id] = lttgc_data[guild_id].get(user_id, 0) + amount

        try:
            dm_channel = await user.create_dm()
            dm_message = f"Hello {user.display_name},\n\n{ctx.user.name} has given you {amount} God Coins."
            if reason:
                dm_message += f"\nReason: {reason}"
            await dm_channel.send(dm_message)
        except discord.Forbidden:
            await response.send_message(f"{user.display_name} has their DMs disabled, but the coins were added successfully.", ephemeral=True)
        
        save_gc()  # Save GC data
        save_lttgc()  # Save LTTGC data
        await response.send_message(f"You have successfully given {amount} God Coins to {user.display_name}.", ephemeral=True)
    else:
        await response.send_message("You do not have permission to give God Coins.", ephemeral=True)

# Command to give GC to roles (role)
@bot.tree.command(name="giverole", description="Give GC to all members of a single role.")
async def give_role(ctx, role: discord.Role, amount: int, reason: str = "No reason provided"):
    response: discord.InteractionResponse = ctx.response
    
    if discord.utils.get(ctx.user.roles, name="Admin"):
        guild = bot.get_guild(GUILD_ID)

        if not guild:
            await response.send_message("Guild not found.", ephemeral=True)
            return

        if amount < 0:
            await response.send_message("You cannot give a negative amount of God Coins.", ephemeral=True)
            return

        members = role.members
        for member in members:
            user_id = str(member.id)
            guild_id = str(guild.id)
            gc_data.setdefault(guild_id, {})
            user_data = gc_data[guild_id].setdefault(user_id, {'gc': 0, 'last_claimed': ''})

            user_data['gc'] += amount
            lttgc_data[guild_id][user_id] = lttgc_data[guild_id].get(user_id, 0) + amount

            try:
                dm_channel = await member.create_dm()
                dm_message = (f"Hello {member.display_name},\n\n{ctx.user.name} has given you {amount} God Coins.\n\n"
                              f"Reason: {reason}")
                await dm_channel.send(dm_message)
            except discord.Forbidden:
                pass

        save_gc()  # Save GC data
        save_lttgc()  # Save LTTGC data
        await response.send_message(f"You have successfully given {amount} God Coins to all members of {role.name}.", ephemeral=True)
    else:
        await response.send_message("You do not have permission to give God Coins.", ephemeral=True)

# Command to deduct GC from a user
@bot.tree.command(name="deduct", description="Deduct GC from a user with a reason.")
async def deduct(interaction: discord.Interaction, member: discord.Member, amount: int, reason: str):
    """Command to deduct GC from a user's balance, accessible only by admins."""
    
    # Check if the user has admin permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    user_id = str(member.id)
    guild_id = str(interaction.guild.id)

    # Call the deduct_gc function to perform the deduction
    if deduct_gc(user_id, guild_id, amount, reason):
        # Notify the user that their GC balance has been deducted
        await member.send(f"Your GC balance has been reduced by {amount} points. Reason: {reason}")
        
        # Inform the admin who triggered the command
        await interaction.response.send_message(f"{amount} GC has been deducted from {member.name}'s balance. Reason: {reason}.", ephemeral=True)
    else:
        # If the deduction failed (e.g., insufficient balance)
        await interaction.response.send_message(f"Failed to deduct GC from {member.name}. They may not have enough GC.", ephemeral=True)

def deduct_gc(user_id, guild_id, amount, reason):
    """Deduct the given amount of GC from a user's balance and record the reason."""
    # Ensure gc_data is properly initialized for the guild and user
    if user_id in gc_data.get(guild_id, {}):
        user_data = gc_data[guild_id][user_id]
        
        # Check if the user has enough GC to deduct
        if user_data['gc'] >= amount:
            user_data['gc'] -= amount
            save_gc()  # Save GC data after deduction
            
            # Optionally log the reason or take other actions (e.g., save the reason to a log)
            print(f"Deducted {amount} GC from {user_id} for reason: {reason}")  # Example log
            return True
    return False

# Reset GC of all users
@bot.tree.command(name="reset_gc", description="Reset the GC balance of all users.")
async def reset_gc(ctx):
    response = ctx.response

    guild_id = str(ctx.guild.id)

# Command to reset GC
@bot.tree.command(name="reset_gc", description="Reset the GC balance of all users.")
async def reset_gc(ctx):
    response = ctx.response

    guild_id = str(ctx.guild.id)

    # Backup the current GC data before resetting
    backup_points()

    # Reset the GC balance for all users in the guild
    if guild_id in gc_data:
        for user_id in list(gc_data[guild_id].keys()):
            gc_data[guild_id][user_id]['gc'] = 0  # Reset only the GC balance, not lttgc

        save_gc()  # Save the updated GC data after reset

        await response.send_message(f"All GC balances have been reset for the clan.")
    else:
        await response.send_message("No GC data found for this clan.", ephemeral=True)

# Command to reset daily claims for all users
@bot.tree.command(name="reset_daily", description="Reset daily claims for all users.")
@commands.has_role('Admin')
async def reset_daily_claims(interaction: discord.Interaction):
    """Resets daily claims for all users in the guild."""
    
    # Get the guild object from the interaction
    guild = interaction.guild
    guild_id = str(guild.id)

    # Check if the points data exists for the guild
    if guild_id in gc_data:  # Assuming gc_data holds the user claim data
        for user_id, data in gc_data[guild_id].items():
            data['last_claimed'] = ""  # Reset the 'last_claimed' field for all users
        save_gc()  # Save the updated GC data
        
        # Send a confirmation message to the user who triggered the command
        await interaction.response.send_message("Daily claims have been reset for all users.", ephemeral=True)
    else:
        # Send an error message if no points data is found for the guild
        await interaction.response.send_message("No GC data found to reset.", ephemeral=True)

############# LEADERBOARD + GC BALANCE #############

# Command to display LTTGC leaderboard (Only Lifetime GC)
@bot.tree.command(name="leaderboard", description="Shows the leaderboard.")
async def leaderboard(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    if not guild:
        await response.send_message("Guild not found.", ephemeral=True)
        return

    try:
        sorted_lttgc_data = sorted(
            [
                (
                    user_id, 
                    {
                        "lttgc": data if isinstance(data, int) else data.get("lttgc", 0)
                    }
                )
                for user_id, data in lttgc_data.get(guild_id, {}).items()
            ],
            key=lambda x: x[1]["lttgc"],
            reverse=True
        )
    except Exception as e:
        print(f"Error while sorting lttgc data for guild {guild_id}: {e}")
        await response.send_message("There was an error while generating the leaderboard.", ephemeral=True)
        return

    leaderboard_entries = [
        f"{idx + 1}. {guild.get_member(int(user_id)).display_name if guild.get_member(int(user_id)) else 'Unknown User'}: {data['lttgc']} Lifetime God Coins"
        for idx, (user_id, data) in enumerate(sorted_lttgc_data)
    ]

    entries_per_page = 25x
    total_pages = max(ceil(len(leaderboard_entries) / entries_per_page), 1)

    def get_page_content(page: int):
        start_idx = page * entries_per_page
        end_idx = start_idx + entries_per_page
        entries = leaderboard_entries[start_idx:end_idx]
        leaderboard_msg = f"**Of The Gods - Lifetime total God Coins - Leaderboard** (Page {page + 1}/{total_pages})\n\n" + "\n".join(entries)
        return leaderboard_msg

    current_page = 0
    message_content = get_page_content(current_page)

    class LeaderboardView(View):
        def __init__(self):
            super().__init__()
            self.update_buttons()

        @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary, disabled=True)
        async def previous_button(self, interaction: discord.Interaction, button: Button):
            nonlocal current_page
            current_page -= 1
            message_content = get_page_content(current_page)  # Update message content on page change
            self.update_buttons()
            await interaction.response.edit_message(content=message_content, view=self)

        @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)
        async def next_button(self, interaction: discord.Interaction, button: Button):
            nonlocal current_page
            current_page += 1
            message_content = get_page_content(current_page)  # Update message content on page change
            self.update_buttons()
            await interaction.response.edit_message(content=message_content, view=self)

        def update_buttons(self):
            self.children[0].disabled = current_page == 0
            self.children[1].disabled = current_page == total_pages - 1

    view = LeaderboardView()
    await response.send_message(message_content, view=view, ephemeral=True)

# Command to check user's GC balance
@bot.tree.command(name="gc", description="Shows your GC balance.")
async def gc(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(ctx.user.id)
    guild_id = str(guild.id)
    user_id = str(guild_member.id)

    if discord.utils.get(guild_member.roles, name='Member') or discord.utils.get(guild_member.roles, name="Trial"):

        user_data = gc_data.get(guild_id, {}).get(user_id)
        if user_data:
            await response.send_message(f"{guild_member.mention} You have {user_data['gc']} God Coins in your balance.", ephemeral=True)
        else:
            await response.send_message(f"{guild_member.mention} You have no God Coins in your balance.", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

############# TO START UP THE BOT #############

@bot.event
async def on_ready():
        try:
            print('Bot is ready')
            await bot.tree.sync()
            print('Commands synced.')
            await main()
        except Exception as e:
         print(f"Error in on_ready or main function: {e}")

# Start the bot
bot.run(TOKEN)