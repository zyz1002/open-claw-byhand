import botpy
from botpy.types.message import Message
from dotenv import load_dotenv
import os
logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()
APPID = os.getenv("QQ_APPID")
TOKEN = os.getenv("QQ_TOKEN")
class MyClient(botpy.Client):
    async def on_at_message_create(self, message: Message):
        await self.api.post_message(channel_id=message.channel_id, content="content")

intents = botpy.Intents(public_guild_messages=True) 
client = MyClient(intents=intents)
client.run(appid={APPID}, token={TOKEN})
