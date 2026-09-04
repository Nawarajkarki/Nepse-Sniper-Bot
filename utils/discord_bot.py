import asyncio
import discord

from config.settings import DISCORD_TOKEN, DISCORD_USER_ID


async def send_private_message(message_text):
    user_id = DISCORD_USER_ID
    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        try:
            # Fetch user by their Discord Snowflake ID
            user = await client.fetch_user(user_id)
            await user.send(message_text)
            print(f"Message sent to {user.name}")
        except Exception as e:
            print(f"Failed to send DM: {e}")
        finally:
            await client.close()
            
            

    await client.start(DISCORD_TOKEN)

if __name__ == "__main__":
    msg = "Message from send_dm.py"    
    asyncio.run(send_private_message(msg))