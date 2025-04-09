# bot.py
import discord
from discord import app_commands # Required for slash commands
import os
import requests
import logging
from dotenv import load_dotenv

# --- Basic Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv() # Load .env file for local development
DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
N8N_WEBHOOK_BASE_URL = os.getenv('N8N_WEBHOOK_BASE_URL')

if not DISCORD_BOT_TOKEN:
    logger.error("FATAL: DISCORD_BOT_TOKEN environment variable not set.")
    exit()
if not N8N_WEBHOOK_BASE_URL:
    logger.error("FATAL: N8N_WEBHOOK_BASE_URL environment variable not set.")
    exit()

# --- Discord Bot Setup ---
# Define intents - default is usually fine for slash commands
intents = discord.Intents.default()
# intents.message_content = True # Only needed if using prefix commands or reading message text

# Use Client for simpler setup, or Bot for more features (like cogs)
# Using Client here as it's sufficient
client = discord.Client(intents=intents)
# Command Tree stores the slash command definitions
tree = app_commands.CommandTree(client)

# --- Bot Events ---
@client.event
async def on_ready():
    """Event handler for when the bot connects to Discord."""
    logger.info(f'Logged in as {client.user.name} (ID: {client.user.id})')
    logger.info('Syncing command tree...')
    try:
        # Sync commands globally. Can take up to an hour to propagate.
        # For testing, sync to a specific guild: await tree.sync(guild=discord.Object(id=YOUR_GUILD_ID))
        synced = await tree.sync()
        logger.info(f"Synced {len(synced)} command(s).")
    except Exception as e:
        logger.error(f"Failed to sync command tree: {e}")
    logger.info('Bot is ready and listening!')

# --- Bot Commands ---
@tree.command(name="attribute-speakers", description="Send metadata back to a waiting n8n workflow.")
@app_commands.describe(
    execution_id="The n8n execution ID provided in the initial message.",
    metadata="The metadata value you need to provide.",
    transcription_id="The transcription ID to associate with this metadata."
)
async def attribute_speakers(interaction: discord.Interaction, execution_id: str, metadata: str, transcription_id: str):
    """Slash command handler to send data to n8n."""
    logger.info(f"Received /attribute-speakers from {interaction.user} for execution ID: {execution_id}")

    # Parse the metadata string into a dictionary
    speaker_map = {}
    try:
        pairs = metadata.split(',')
        for pair in pairs:
            speaker_id, speaker_name = pair.strip().split(':')
            speaker_map[speaker_id] = speaker_name
    except ValueError as e:
        logger.error(f"Error parsing metadata string: {e}")
        await interaction.response.send_message("❌ Invalid metadata format. Please use format 'speaker_00:name,speaker_01:name'", ephemeral=True)
        return

    webhook_url = f"{N8N_WEBHOOK_BASE_URL.rstrip('/')}/webhook-waiting/{execution_id}"
    logger.info(f"Target n8n webhook URL: {webhook_url}")

    # Updated payload to include parsed speaker map
    payload = {
        "metadata": speaker_map,
        "transcription_id": transcription_id
    }

    # Make the POST request to n8n
    try:
        # Defer the response first, as the request might take time
        await interaction.response.defer(ephemeral=True) # Ephemeral: only visible to the user

        logger.info(f"Sending POST request to n8n with payload: {payload}")
        response = requests.post(webhook_url, json=payload, timeout=10) # 10 second timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        logger.info(f"n8n workflow {execution_id} successfully triggered. Status: {response.status_code}")
        await interaction.followup.send(f"✅ Successfully sent metadata for execution `{execution_id}` to the workflow!", ephemeral=True)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error sending request to n8n for execution {execution_id}: {e}")
        error_message = f"❌ Failed to send metadata to the workflow for execution `{execution_id}`."
        if e.response is not None:
            logger.error(f"n8n response status: {e.response.status_code}")
            logger.error(f"n8n response body: {e.response.text}")
            error_message += f"\n_Details: Received status {e.response.status_code} from n8n._"
            if e.response.status_code == 404:
                 error_message += "\n_(This often means the execution ID is incorrect or the workflow is no longer waiting.)_"
        else:
             error_message += "\n_(Could not connect to the n8n instance.)_"
        await interaction.followup.send(error_message, ephemeral=True)

    except Exception as e:
        logger.exception(f"An unexpected error occurred processing /provide-metadata for {execution_id}: {e}")
        await interaction.followup.send(f"❌ An unexpected error occurred. Please check the bot logs.", ephemeral=True)


# --- Run the Bot ---
if __name__ == "__main__":
    try:
        client.run(DISCORD_BOT_TOKEN, log_handler=None) # Use default logging configured above
    except discord.LoginFailure:
        logger.error("FATAL: Invalid Discord Bot Token. Please check your .env file or environment variables.")
    except Exception as e:
        logger.exception(f"FATAL: Bot failed to run: {e}")