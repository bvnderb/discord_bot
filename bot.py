import discord
from discord.ext import commands
import json
import datetime
import asyncio
import os
from apscheduler.schedulers.asyncio import AsyncIOScheduler

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
RANK_UP_THRESHOLDS = config['rank_up_thresholds']
STREAK_MULTIPLIER = config.get('streak_multiplier', 0.1)

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
                f.write(f"User ID: {user_id}, Points: {data['points']}, Last Claimed: {data['last_claimed']}, Streak: {data['streak']}\n")
            f.write("\n")

# Daily claim streaks + daily reset
async def tick():
    try:
        guild = bot.get_guild(GUILD_ID)
        guild_id = str(guild.id)
        
        sorted_cp_data = sorted(points.get(str(guild_id), {}).items(), key=lambda x: x[1]["points"], reverse=True)
        for idx, (user_id, data) in enumerate(sorted_cp_data, start=1):
            last_claimed = data['last_claimed']
            if not last_claimed:
                continue  # Skip if last_claimed is empty
            yesterday = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=2)
            last_claimed_date = datetime.datetime.strptime(last_claimed, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            
            if last_claimed_date < yesterday:
                print(f"Reset streak of {user_id}")
                data['streak'] = 0
                data['last_claimed'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d')
                save_points()
    except Exception as e:
        print(f"Error in tick function: {e}")

def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)

async def main():
    print('Starting main function...')
    scheduler = AsyncIOScheduler()
    scheduler.add_job(tick, 'interval', seconds=86400)  # Run daily
    scheduler.start()
    print('Scheduler started.')
    
    # Use an asyncio event to keep the program running
    event = asyncio.Event()
    await event.wait()

# Command to claim daily CP
@bot.tree.command(name="claim", description="Claim your daily CP with this command.")
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
        user_data = points[guild_id].setdefault(user_id, {"points": 0, "last_claimed": "", "streak": 0})

        if user_data['last_claimed']:
            last_claimed_date = datetime.datetime.strptime(user_data['last_claimed'], '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
            if last_claimed_date.date() >= now.date():
                next_claim_time = last_claimed_date + datetime.timedelta(days=1)
                next_claim_time_str = next_claim_time.strftime('%Y-%m-%d %H:%M:%S %Z')
                await response.send_message(f'You have already claimed your daily CP for today, try again at {next_claim_time_str}', ephemeral=True)
                return

        if 'streak' in user_data:
            claim_points = int(10 * (1 + (clamp(user_data['streak'], 0, 10) * STREAK_MULTIPLIER)))
            user_data['points'] += claim_points
            user_data['last_claimed'] = today
            user_data['streak'] += 1
            save_points()
            await response.send_message(f"{ctx.user.mention} You claimed {claim_points} CP successfully! Total CP: {user_data['points']}, you have a streak of {user_data['streak']}", ephemeral=True)
        else:
            claim_points = int(10 * (1 + (clamp(0, 0, 10) * STREAK_MULTIPLIER)))
            user_data['points'] += claim_points
            user_data['last_claimed'] = today
            user_data['streak'] = 1
            save_points()
            await response.send_message(f"{ctx.user.mention} You claimed {claim_points} CP successfully! Total CP: {user_data['points']}, you have a streak of {user_data['streak']}", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

# Command to display CP leaderboard
@bot.tree.command(name="leaderboard", description="Shows the leaderboard.")
async def leaderboard(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(ctx.user.id)
    guild_id = str(guild.id)

    if discord.utils.get(guild_member.roles, name='Member') or discord.utils.get(guild_member.roles, name="Trial"):
        sorted_cp_data = sorted(points.get(str(guild_id), {}).items(), key=lambda x: x[1]["points"], reverse=True)
        leaderboard_msg = "Of The Gods Clan Points Leaderboard:\n"
        for idx, (user_id, data) in enumerate(sorted_cp_data, start=1):
            user = guild.get_member(int(user_id))
            if user:
                leaderboard_msg += f"{idx}. {user.display_name}: {data['points']} CP\n"
            else:
                points[guild_id].pop(user_id)
                save_points()

        await response.send_message(leaderboard_msg, ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

# Command to check user's CP
@bot.tree.command(name="cp", description="Shows your CP count.")
async def cp(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_member = guild.get_member(ctx.user.id)
    guild_id = str(guild.id)
    user_id = str(guild_member.id)

    if discord.utils.get(guild_member.roles, name='Member') or discord.utils.get(guild_member.roles, name="Trial"):

        user_data = points.get(guild_id, {}).get(user_id)
        if user_data:
            await response.send_message(f"{guild_member.mention} You have {user_data['points']} CP.", ephemeral=True)
        else:
            await response.send_message(f"{guild_member.mention} You have no CP.", ephemeral=True)
    else:
        await response.send_message("You do not have permission to use this command.", ephemeral=True)

# Command to give CP manually
@bot.tree.command(name="give", description="Give another user CP.")
@commands.has_role('Ranked')
async def give(ctx, user: discord.Member, amount: int, *, reason: str = None):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)
    user_id = str(user.id)

    points.setdefault(guild_id, {})
    user_data = points[guild_id].setdefault(user_id, {"points": 0, "last_claimed": ""})
    user_data["points"] += amount
    save_points()

    if reason:
        await response.send_message(f"{amount} CP added to {user.mention} for reason: {reason}.", ephemeral=True)
        try:
            await user.send(f"You have been given {amount} CP by {ctx.user.display_name} as part of the distribution to members with the role. Reason: {reason}.")
        except discord.Forbidden:
            pass  # If the bot can't DM the user
    else:
        await response.send_message(f"{amount} CP added to {user.mention}.", ephemeral=True)
        try:
            await user.send(f"You have been given {amount} CP by {ctx.user.display_name} as part of the distribution to members with the role.")
        except discord.Forbidden:
            pass  # If the bot can't DM the user

# Command to reset CP for all members
@bot.tree.command(name="reset_cp", description="Reset all CP.")
@commands.has_role('Admin')
async def reset_cp(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    # Backup the current points data
    backup_points()

    points[guild_id] = {}
    save_points()
    await response.send_message("CP count has been reset for all members. A backup has been saved.", ephemeral=True)

# Command to reset daily claims for all users
@bot.tree.command(name="reset_daily_claims", description="Reset daily claims for all users.")
@commands.has_role('Admin')
async def reset_daily_claims(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    if guild_id in points:
        for user_id, data in points[guild_id].items():
            data['last_claimed'] = ""
            data['streak'] = 0
        save_points()
        await response.send_message("Daily claims have been reset for all users.", ephemeral=True)
    else:
        await response.send_message("No points data found to reset.", ephemeral=True)

# Command to give CP to everyone with a specific role
@bot.tree.command(name="give_role_cp", description="Give CP to all users with a specific role.")
@commands.has_role('Admin')
async def give_role_cp(ctx, role: discord.Role, amount: int, *, reason: str = None):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    if role.name in ['Member', 'Trial', 'Ranked']:
        for member in role.members:
            user_id = str(member.id)
            points.setdefault(guild_id, {})
            user_data = points[guild_id].setdefault(user_id, {"points": 0, "last_claimed": ""})
            user_data["points"] += amount

        save_points()
        message = f"Everyone with the role {role.name} has been given {amount} CP as part of the distribution."
        if reason:
            message += f" Reason: {reason}."
        
        await response.send_message(message, ephemeral=True)
        for member in role.members:
            try:
                await member.send(f"You have been given {amount} CP as part of the distribution to members with the role {role.name}. Reason: {reason if reason else 'None'}.")
            except discord.Forbidden:
                pass  # If the bot can't DM the user
    else:
        await response.send_message("Role is not eligible for CP distribution.", ephemeral=True)

# Command to check users eligible for rank-up
@bot.tree.command(name="check_rank_ups", description="Check users eligible for rank-up.")
@commands.has_role('Ranked')
async def check_rank_ups(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    eligible_users = []

    for user_id, data in points.get(guild_id, {}).items():
        points_earned = data.get('points', 0)
        for threshold, rank in RANK_UP_THRESHOLDS.items():
            if int(threshold) <= points_earned:
                member = guild.get_member(int(user_id))
                if member and not any(role.name in ['Ranked', 'Guest', 'Special Guest'] for role in member.roles):
                    eligible_users.append((member, rank))
                break  # Stop checking after the highest rank achieved

    if eligible_users:
        message = "Users eligible for rank-up:\n"
        for member, rank in eligible_users:
            message += f"{member.display_name} - Eligible for rank: {rank}\n"
        await response.send_message(message, ephemeral=True)
    else:
        await response.send_message("No users are eligible for rank-up at this moment.", ephemeral=True)

# Command to track user activity
@bot.tree.command(name="track_activity", description="Track user activity.")
@commands.has_role('Ranked')
async def track_activity(ctx):
    response: discord.InteractionResponse = ctx.response

    guild = bot.get_guild(GUILD_ID)
    guild_id = str(guild.id)

    activity_data = {}  # Example placeholder for tracking data

    for member in guild.members:
        if member.bot:
            continue
        message_count = len([msg async for msg in member.history(limit=100)])  # Adjust limit as needed
        activity_data[member.display_name] = message_count

    activity_report = "User Activity Report:\n"
    for name, count in activity_data.items():
        activity_report += f"{name}: {count} messages\n"

    await response.send_message(activity_report, ephemeral=True)

# Event to check for rank-ups
@bot.event
async def on_member_update(before, after):
    if before.guild.id == GUILD_ID:
        # Check if user role has changed to 'Ranked'
        if any(role.name == 'Ranked' for role in after.roles) and not any(role.name == 'Ranked' for role in before.roles):
            user_id = str(after.id)
            guild_id = str(after.guild.id)
            user_data = points.get(guild_id, {}).get(user_id, {})
            points_earned = user_data.get('points', 0)
            eligible_rank = None

            for threshold, rank in RANK_UP_THRESHOLDS.items():
                if int(threshold) <= points_earned:
                    eligible_rank = rank
                    break

            if eligible_rank:
                try:
                    await after.send(f"Congratulations {after.display_name}! You are now eligible for the rank of {eligible_rank}. Please check your rank and ensure it matches the rank assigned to you.")
                except discord.Forbidden:
                    pass  # If the bot can't DM the user

@bot.event
async def on_ready():
    try:
        print('Bot is ready')
        await bot.tree.sync()
        print('Commands synced.')
        await main()
    except Exception as e:
        print(f"Error in on_ready or main function: {e}")

# Run the bot
bot.run(TOKEN)