# # # # """
# # # # 使用claude code sdk构建一个agent，作为小龙虾的核心
# # # # 1. bot最开始只能回答设定好的内容（按规则走），现在需要学会思考和生成
# # # # 2. ai回复需要拆分然后安全的返回给qq bot
# # # # 3. 需要把api key与环境配置从代码中剥离

# # # # claude code 是agent智能体，会主动调用工具
# # # # 用户：今天天气怎么样
# # # # Claude （assistant message）：我来查询一下北京天气
# # # # claude 调用工具（天气api）
# # # # 系统返回 toolresultblock：{"temperature": "23.0", "weather": "晴", "city": "北京"}
# # # # claude (assistant message): 北京今天天气是晴，温度是23度

# # # # """ 
# # # # from claude_agent_sdk import (
# # # #     AssistantMessage,
# # # #     ClaudeAgentOptions,
# # # #     ResultMessage,
# # # #     TextBlock,
# # # #     create_sdk_mcp_server,
# # # #     query,
# # # #     tool,
# # # # )
# # # # import os
# # # # from dotenv import load_dotenv
# # # # load_dotenv()
# # # # ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# # # # ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")
# # # # async def ask_claude(prompt: str)-> str:
# # # #     """调用claude code sdk，返回结果"""
# # # #     env = {
# # # #         "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
# # # #         "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL
# # # #     }
# # # #     options = ClaudeAgentOptions(
# # # #         model = "GLM-4.5-air",
# # # #         system_prompt="你是小龙虾助手",
# # # #         permission_mode="acceptEdits",
# # # #         env=env,
# # # #         max_turns=10,
# # # #         cwd = ".",
# # # #         )
# # # #     response_part: list[str] = []
# # # #     async for message in query(prompt=prompt, options=options):
# # # #         if isinstance(message, AssistantMessage):
# # # #             for block in message.content:
# # # #                 if isinstance(block, TextBlock):
# # # #                     response_part.append(block.text)
# # # #         elif isinstance(message, ResultMessage):
# # # #             if message.result:
# # # #                 print("最终回答:", message.result)
# # # #                 response_part.append(message.result)
# # # #     return "\n".join(response_part) or "没有结果"

# # # # if __name__ == "__main__":
# # # #     import asyncio
# # # #     result = asyncio.run(ask_claude("你好，请介绍一下你自己"))
# # # #     print(result)
# # # """
# # # QQ 机器人入口 — 对应原版 Telegram bot 的消息接口层
# # # """
# # # import asyncio
# # # import logging
# # # import os

# # # from botpy import Client
# # # from botpy.flags import Intents
# # # from botpy.message import C2CMessage
# # # from dotenv import load_dotenv
# # # from claude_agent_sdk import (
# # #     AssistantMessage,
# # #     ClaudeAgentOptions,
# # #     ResultMessage,
# # #     TextBlock,
# # #     query,
# # # )
# # # from tools.server import mcp_server
# # # import db

# # # logger = logging.getLogger(__name__)

# # # # 加载环境变量
# # # load_dotenv()
# # # APPID = os.getenv("QQ_APP_ID")
# # # TOKEN = os.getenv("QQ_BOT_TOKEN")
# # # ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "OpenClaw")

# # # ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# # # ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")

# # # QQ_MAX_LENGTH = 2000  # QQ 单条消息字数上限


# # # async def ask_claude(prompt: str) -> str:
# # #     """调用 claude agent sdk，返回结果"""
# # #     env = {
# # #         "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
# # #         "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
# # #     }
# # #     options = ClaudeAgentOptions(
# # #         model="GLM-4.5-air",
# # #         system_prompt="你是小龙虾助手，使用中文回答问题",
# # #         permission_mode="bypassPermissions",
# # #         env=env,
# # #         max_turns=10,
# # #         cwd=".",
# # #         mcp_servers={"nanoclaw-tools": mcp_server},
# # #         allowed_tools=["get_current_time"],
# # #     )
# # #     final_result = ""
# # #     mess = query(prompt=prompt, options=options)
# # #     logger.info("SDK 原始消息内容=======是一个迭代器: %s", mess)
# # #     async for message in mess:
# # #         logger.info("SDK 原始消息类型----------: %s", type(message).__name__)
# # #         logger.info("SDK 原始消息内容: %s", message)
# # #         if isinstance(message, AssistantMessage):
# # #             for block in message.content:
# # #                 logger.info("  block 类型: %s, 内容: %s", type(block).__name__, block)
# # #         elif isinstance(message, ResultMessage):
# # #             if message.result:
# # #                 logger.info("  ResultMessage.result: %s", message.result)
# # #                 final_result = message.result
# # #     return final_result or "没有结果"


# # # async def _handle_c2c_message(message: C2CMessage) -> None:
# # #     """处理私聊文本消息，调用 Claude 生成回复"""
# # #     user_text = message.content
# # #     result = await ask_claude(user_text)
# # #     # QQ 单条消息有长度限制，超长需要截断
# # #     if len(result) > QQ_MAX_LENGTH:
# # #         result = result[:QQ_MAX_LENGTH]
# # #     await message.reply(content=result)


# # # class MyClient(Client):
# # #     """QQ 机器人客户端"""

# # #     async def on_ready(self):
# # #         logger.info("%s 机器人启动成功", ASSISTANT_NAME)

# # #     async def on_c2c_message_create(self, message: C2CMessage):
# # #         """处理私聊（C2C）消息"""
# # #         content = message.content or ""

# # #         if content == "/start":
# # #             await message.reply(
# # #                 content=f"Hi! I'm {ASSISTANT_NAME}, your personal AI assistant. Send me a message to get started.\n\n"
# # #                 "Commands:\n"
# # #                 "/clear - Reset conversation session"
# # #             )
# # #             return

# # #         if content == "/clear":
# # #             await message.reply(content="Session cleared. Starting fresh!")
# # #             return

# # #         if content.startswith("/"):
# # #             return

# # #         await _handle_c2c_message(message)


# # # # 启动
# # # if __name__ == "__main__":
# # #     logging.basicConfig(level=logging.INFO)
# # #     _log = logging.getLogger(__name__)
# # #     _log.setLevel(logging.INFO)
# # #     _log.propagate = False  # 防止向 root logger 传播导致重复输出
# # #     _fmt = logging.Formatter("[%(levelname)s] (%(filename)s:%(lineno)d)%(funcName)-20s %(message)s")
# # #     # 终端输出
# # #     _stream = logging.StreamHandler()
# # #     _stream.setFormatter(_fmt)
# # #     _log.addHandler(_stream)
# # #     # 文件保存
# # #     _file = logging.FileHandler("bot.log", encoding="utf-8")
# # #     _file.setFormatter(logging.Formatter("[%(asctime)s] " + _fmt._fmt))
# # #     _log.addHandler(_file)
# # #     intents = Intents(public_messages=True, public_guild_messages=True)
# # #     client = MyClient(intents=intents)
# # #     client.run(appid=APPID, secret=TOKEN)
# # """
# # QQ 机器人入口 — 对应原版 Telegram bot 的消息接口层
# # """
# # import asyncio
# # import logging
# # import os

# # from botpy import Client
# # from botpy.flags import Intents
# # from botpy.message import C2CMessage
# # from dotenv import load_dotenv
# # from claude_agent_sdk import (
# #     AssistantMessage,
# #     ClaudeAgentOptions,
# #     ResultMessage,
# #     TextBlock,
# #     query,
# # )
# # from tools.server import mcp_server
# # import db

# # logger = logging.getLogger(__name__)

# # # 加载环境变量
# # load_dotenv()
# # APPID = os.getenv("QQ_APP_ID")
# # TOKEN = os.getenv("QQ_BOT_TOKEN")
# # ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "OpenClaw")

# # ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# # ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")

# # QQ_MAX_LENGTH = 2000  # QQ 单条消息字数上限


# # def _build_context_prompt(history: list[dict], user_message: str) -> str:
# #     """将历史对话拼接为带上下文的 prompt"""
# #     if not history:
# #         return user_message
# #     context_lines = []
# #     for msg in history:
# #         role_label = "用户" if msg["role"] == "user" else "小龙虾"
# #         context_lines.append(f"[{role_label}]: {msg['content']}")
# #     context_text = "\n".join(context_lines)
# #     return (
# #         f"以下是你和用户的近期对话记录：\n{context_text}\n\n"
# #         f"用户最新消息：{user_message}\n\n"
# #         f"请根据上下文继续对话。"
# #     )


# # async def ask_claude(prompt: str, session_id: str) -> str:
# #     """调用 claude agent sdk，返回结果。支持多轮对话上下文。"""
# #     # 读取历史对话
# #     history = await db.get_recent_messages(session_id, limit=20)
# #     context_prompt = _build_context_prompt(history, prompt)

# #     env = {
# #         "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
# #         "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
# #     }
# #     options = ClaudeAgentOptions(
# #         model="GLM-4.5-air",
# #         system_prompt="你是小龙虾助手，使用中文回答问题",
# #         permission_mode="bypassPermissions",
# #         env=env,
# #         max_turns=10,
# #         cwd=".",
# #         mcp_servers={"nanoclaw-tools": mcp_server},
# #         allowed_tools=["get_current_time", "calculate"],
# #     )
# #     # 带重试的调用
# #     final_result = ""
# #     max_retries = 2
# #     for attempt in range(max_retries + 1):
# #         try:
# #             mess = query(prompt=context_prompt, options=options)
# #             async for message in mess:
# #                 if isinstance(message, AssistantMessage):
# #                     pass  # 跳过中间过程
# #                 elif isinstance(message, ResultMessage):
# #                     if message.result:
# #                         final_result = message.result
# #             break
# #         except asyncio.TimeoutError:
# #             if attempt < max_retries:
# #                 logger.warning("ask_claude 超时，第 %d 次重试", attempt + 1)
# #                 await asyncio.sleep(1)
# #                 continue
# #             return "思考太久了，请再试一次"
# #         except (ConnectionError, OSError) as e:
# #             if attempt < max_retries:
# #                 logger.warning("ask_claude 网络错误: %s，第 %d 次重试", e, attempt + 1)
# #                 await asyncio.sleep(1)
# #                 continue
# #             logger.error("ask_claude 网络错误，重试耗尽: %s", e)
# #             return "网络出了点问题，请稍后再试"
# #         except Exception as e:
# #             logger.error("ask_claude 异常: %s", e, exc_info=True)
# #             return "出了点问题，请稍后再试"

# #     # 保存用户消息和助手回复到数据库
# #     await db.save_message(session_id, "user", prompt)
# #     await db.save_message(session_id, "assistant", final_result)

# #     return final_result or "没有结果"


# # async def _handle_c2c_message(message: C2CMessage) -> None:
# #     """处理私聊文本消息，调用 Claude 生成回复"""
# #     session_id = message.author.user_openid
# #     user_text = message.content
# #     try:
# #         result = await ask_claude(user_text, session_id)
# #     except Exception as e:
# #         logger.error("消息处理异常: %s", e, exc_info=True)
# #         result = "出了点问题，请稍后再试"
# #     # QQ 单条消息有长度限制，超长需要截断
# #     if len(result) > QQ_MAX_LENGTH:
# #         result = result[:QQ_MAX_LENGTH]
# #     await message.reply(content=result)


# # class MyClient(Client):
# #     """QQ 机器人客户端"""

# #     async def on_ready(self):
# #         await db.init_db()
# #         logger.info("%s 机器人启动成功", ASSISTANT_NAME)

# #     async def on_c2c_message_create(self, message: C2CMessage):
# #         """处理私聊（C2C）消息"""
# #         content = message.content or ""

# #         if content == "/start":
# #             await message.reply(
# #                 content=f"Hi! I'm {ASSISTANT_NAME}, your personal AI assistant. Send me a message to get started.\n\n"
# #                 "Commands:\n"
# #                 "/clear - Reset conversation session"
# #             )
# #             return

# #         if content == "/clear":
# #             session_id = message.author.user_openid
# #             await db.clear_session(session_id)
# #             await message.reply(content="Session cleared. Starting fresh!")
# #             return

# #         if content.startswith("/"):
# #             return

# #         await _handle_c2c_message(message)


# # # 启动
# # if __name__ == "__main__":
# #     logging.basicConfig(level=logging.INFO)
# #     _log = logging.getLogger(__name__)
# #     _log.setLevel(logging.INFO)
# #     _log.propagate = False  # 防止向 root logger 传播导致重复输出
# #     _fmt = logging.Formatter("[%(levelname)s] (%(filename)s:%(lineno)d)%(funcName)-20s %(message)s")
# #     # 终端输出
# #     _stream = logging.StreamHandler()
# #     _stream.setFormatter(_fmt)
# #     _log.addHandler(_stream)
# #     # 文件保存
# #     _file = logging.FileHandler("bot.log", encoding="utf-8")
# #     _file.setFormatter(logging.Formatter("[%(asctime)s] " + _fmt._fmt))
# #     _log.addHandler(_file)
# #     intents = Intents(public_messages=True, public_guild_messages=True)
# #     client = MyClient(intents=intents)
# #     client.run(appid=APPID, secret=TOKEN)
# """
# QQ 机器人入口 — 对应原版 Telegram bot 的消息接口层
# """
# import asyncio
# import logging
# import os

# from botpy import Client
# from botpy.flags import Intents
# from botpy.message import C2CMessage
# from dotenv import load_dotenv
# from claude_agent_sdk import (
#     AssistantMessage,
#     ClaudeAgentOptions,
#     ResultMessage,
#     TextBlock,
#     query,
# )
# from tools.server import mcp_server
# import db

# logger = logging.getLogger(__name__)

# # 加载环境变量
# load_dotenv()
# APPID = os.getenv("QQ_APP_ID")
# TOKEN = os.getenv("QQ_BOT_TOKEN")
# ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "OpenClaw")

# ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
# ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")

# QQ_MAX_LENGTH = 2000  # QQ 单条消息字数上限


# def _build_context_prompt(history: list[dict], user_message: str, user_id: str, memories: list[dict]) -> str:
#     """将历史对话、用户记忆拼接为带上下文的 prompt"""
#     parts = []

#     # 注入长期记忆
#     if memories:
#         memory_lines = []
#         for m in memories:
#             memory_lines.append(f"- [{m['category']}] {m['content']}")
#         parts.append("你记住的关于用户的信息：\n" + "\n".join(memory_lines))

#     # 注入近期对话
#     if history:
#         context_lines = []
#         for msg in history:
#             role_label = "用户" if msg["role"] == "user" else "小龙虾"
#             context_lines.append(f"[{role_label}]: {msg['content']}")
#         parts.append("近期对话记录：\n" + "\n".join(context_lines))

#     # 用户最新消息
#     parts.append(f"用户最新消息：{user_message}")

#     # 提示 agent 注意 user_id
#     parts.append(f"当前用户的 user_id 是 {user_id}，调用记忆工具时请传入此 user_id。")

#     parts.append("请根据上下文和记忆继续对话。")

#     return "\n\n".join(parts)


# async def ask_claude(prompt: str, session_id: str) -> str:
#     """调用 claude agent sdk，返回结果。支持多轮对话上下文和长期记忆。"""
#     # 读取历史对话和长期记忆
#     history = await db.get_recent_messages(session_id, limit=20)
#     memories = await db.get_memories(session_id, limit=50)
#     context_prompt = _build_context_prompt(history, prompt, session_id, memories)

#     env = {
#         "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
#         "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
#     }
#     options = ClaudeAgentOptions(
#         model="GLM-4.5-air",
#         system_prompt="你是小龙虾助手，使用中文回答问题。当用户告诉你重要信息（偏好、习惯、事实、提醒）时，请主动使用 save_memory 工具保存。",
#         permission_mode="bypassPermissions",
#         env=env,
#         max_turns=10,
#         cwd=".",
#         mcp_servers={"nanoclaw-tools": mcp_server},
#         allowed_tools=["get_current_time", "calculate", "save_memory", "recall_memories"],
#     )
#     # 带重试的调用
#     final_result = ""
#     max_retries = 2
#     for attempt in range(max_retries + 1):
#         try:
#             mess = query(prompt=context_prompt, options=options)
#             async for message in mess:
#                 if isinstance(message, AssistantMessage):
#                     pass  # 跳过中间过程
#                 elif isinstance(message, ResultMessage):
#                     if message.result:
#                         final_result = message.result
#             break
#         except asyncio.TimeoutError:
#             if attempt < max_retries:
#                 logger.warning("ask_claude 超时，第 %d 次重试", attempt + 1)
#                 await asyncio.sleep(1)
#                 continue
#             return "思考太久了，请再试一次"
#         except (ConnectionError, OSError) as e:
#             if attempt < max_retries:
#                 logger.warning("ask_claude 网络错误: %s，第 %d 次重试", e, attempt + 1)
#                 await asyncio.sleep(1)
#                 continue
#             logger.error("ask_claude 网络错误，重试耗尽: %s", e)
#             return "网络出了点问题，请稍后再试"
#         except Exception as e:
#             logger.error("ask_claude 异常: %s", e, exc_info=True)
#             return "出了点问题，请稍后再试"

#     # 保存用户消息和助手回复到数据库
#     await db.save_message(session_id, "user", prompt)
#     await db.save_message(session_id, "assistant", final_result)

#     return final_result or "没有结果"


# async def _handle_c2c_message(message: C2CMessage) -> None:
#     """处理私聊文本消息，调用 Claude 生成回复"""
#     session_id = message.author.user_openid
#     user_text = message.content
#     try:
#         result = await ask_claude(user_text, session_id)
#     except Exception as e:
#         logger.error("消息处理异常: %s", e, exc_info=True)
#         result = "出了点问题，请稍后再试"
#     # QQ 单条消息有长度限制，超长需要截断
#     if len(result) > QQ_MAX_LENGTH:
#         result = result[:QQ_MAX_LENGTH]
#     await message.reply(content=result)


# class MyClient(Client):
#     """QQ 机器人客户端"""

#     async def on_ready(self):
#         await db.init_db()
#         await db.cleanup_old_data(days=7)
#         logger.info("%s 机器人启动成功", ASSISTANT_NAME)

#     async def on_c2c_message_create(self, message: C2CMessage):
#         """处理私聊（C2C）消息"""
#         content = message.content or ""

#         if content == "/start":
#             await message.reply(
#                 content=f"Hi! I'm {ASSISTANT_NAME}, your personal AI assistant. Send me a message to get started.\n\n"
#                 "Commands:\n"
#                 "/clear - Reset conversation session"
#             )
#             return

#         if content == "/clear":
#             session_id = message.author.user_openid
#             await db.clear_session(session_id)
#             await message.reply(content="Session cleared. Starting fresh!")
#             return

#         if content.startswith("/"):
#             return

#         await _handle_c2c_message(message)


# # 启动
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     _log = logging.getLogger(__name__)
#     _log.setLevel(logging.INFO)
#     _log.propagate = False  # 防止向 root logger 传播导致重复输出
#     _fmt = logging.Formatter("[%(levelname)s] (%(filename)s:%(lineno)d)%(funcName)-20s %(message)s")
#     # 终端输出
#     _stream = logging.StreamHandler()
#     _stream.setFormatter(_fmt)
#     _log.addHandler(_stream)
#     # 文件保存
#     _file = logging.FileHandler("bot.log", encoding="utf-8")
#     _file.setFormatter(logging.Formatter("[%(asctime)s] " + _fmt._fmt))
#     _log.addHandler(_file)
#     intents = Intents(public_messages=True, public_guild_messages=True)
#     client = MyClient(intents=intents)
#     client.run(appid=APPID, secret=TOKEN)
"""
QQ 机器人入口 — 对应原版 Telegram bot 的消息接口层
"""
import asyncio
import logging
import os

from botpy import Client
from botpy.flags import Intents
from botpy.message import C2CMessage
from dotenv import load_dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    query,
)
from tools.server import mcp_server
import db

logger = logging.getLogger(__name__)

# 加载环境变量
load_dotenv()
APPID = os.getenv("QQ_APP_ID")
TOKEN = os.getenv("QQ_BOT_TOKEN")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "OpenClaw")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")

QQ_MAX_LENGTH = 2000  # QQ 单条消息字数上限


def _build_context_prompt(history: list[dict], user_message: str, user_id: str, memories: list[dict]) -> str:
    """将历史对话、用户记忆拼接为带上下文的 prompt"""
    parts = []

    # 注入长期记忆
    if memories:
        memory_lines = []
        for m in memories:
            memory_lines.append(f"- [{m['category']}] {m['content']}")
        parts.append("你记住的关于用户的信息：\n" + "\n".join(memory_lines))

    # 注入近期对话
    if history:
        context_lines = []
        for msg in history:
            role_label = "用户" if msg["role"] == "user" else "小龙虾"
            context_lines.append(f"[{role_label}]: {msg['content']}")
        parts.append("近期对话记录：\n" + "\n".join(context_lines))

    # 用户最新消息
    parts.append(f"用户最新消息：{user_message}")

    # 提示 agent 注意 user_id
    parts.append(f"当前用户的 user_id 是 {user_id}，调用记忆工具时请传入此 user_id。")

    parts.append("请根据上下文和记忆继续对话。")

    return "\n\n".join(parts)


async def ask_claude(prompt: str, session_id: str) -> str:
    """调用 claude agent sdk，返回结果。支持多轮对话上下文和长期记忆。"""
    # 读取历史对话和长期记忆
    history = await db.get_recent_messages(session_id, limit=20)
    memories = await db.get_memories(session_id, limit=50)
    context_prompt = _build_context_prompt(history, prompt, session_id, memories)

    env = {
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "ANTHROPIC_BASE_URL": ANTHROPIC_BASE_URL,
    }
    options = ClaudeAgentOptions(
        model="GLM-4.5-air",
        system_prompt="你是小龙虾助手，使用中文回答问题。当用户告诉你重要信息（偏好、习惯、事实、提醒）时，请主动使用 save_memory 工具保存。",
        permission_mode="bypassPermissions",
        env=env,
        max_turns=10,
        cwd=".",
        mcp_servers={"nanoclaw-tools": mcp_server},
        allowed_tools=["get_current_time", "calculate", "save_memory", "recall_memories", "update_memory_status"],
    )
    # 带重试的调用
    final_result = ""
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            mess = query(prompt=context_prompt, options=options)
            async for message in mess:
                if isinstance(message, AssistantMessage):
                    pass  # 跳过中间过程
                elif isinstance(message, ResultMessage):
                    if message.result:
                        final_result = message.result
            break
        except asyncio.TimeoutError:
            if attempt < max_retries:
                logger.warning("ask_claude 超时，第 %d 次重试", attempt + 1)
                await asyncio.sleep(1)
                continue
            return "思考太久了，请再试一次"
        except (ConnectionError, OSError) as e:
            if attempt < max_retries:
                logger.warning("ask_claude 网络错误: %s，第 %d 次重试", e, attempt + 1)
                await asyncio.sleep(1)
                continue
            logger.error("ask_claude 网络错误，重试耗尽: %s", e)
            return "网络出了点问题，请稍后再试"
        except Exception as e:
            logger.error("ask_claude 异常: %s", e, exc_info=True)
            return "出了点问题，请稍后再试"

    # 保存用户消息和助手回复到数据库
    await db.save_message(session_id, "user", prompt)
    await db.save_message(session_id, "assistant", final_result)

    return final_result or "没有结果"


async def _handle_c2c_message(message: C2CMessage) -> None:
    """处理私聊文本消息，调用 Claude 生成回复"""
    session_id = message.author.user_openid
    user_text = message.content
    try:
        result = await ask_claude(user_text, session_id)
    except Exception as e:
        logger.error("消息处理异常: %s", e, exc_info=True)
        result = "出了点问题，请稍后再试"
    # QQ 单条消息有长度限制，超长需要截断
    if len(result) > QQ_MAX_LENGTH:
        result = result[:QQ_MAX_LENGTH]
    await message.reply(content=result)


class MyClient(Client):
    """QQ 机器人客户端"""

    async def on_ready(self):
        await db.init_db()
        await db.cleanup_old_data(days=7)
        logger.info("%s 机器人启动成功", ASSISTANT_NAME)

    async def on_c2c_message_create(self, message: C2CMessage):
        """处理私聊（C2C）消息"""
        content = message.content or ""

        if content == "/start":
            await message.reply(
                content=f"Hi! I'm {ASSISTANT_NAME}, your personal AI assistant. Send me a message to get started.\n\n"
                "Commands:\n"
                "/clear - Reset conversation session"
            )
            return

        if content == "/clear":
            session_id = message.author.user_openid
            await db.clear_session(session_id)
            await message.reply(content="Session cleared. Starting fresh!")
            return

        if content.startswith("/"):
            return

        await _handle_c2c_message(message)


# 启动
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    _log = logging.getLogger(__name__)
    _log.setLevel(logging.INFO)
    _log.propagate = False  # 防止向 root logger 传播导致重复输出
    _fmt = logging.Formatter("[%(levelname)s] (%(filename)s:%(lineno)d)%(funcName)-20s %(message)s")
    # 终端输出
    _stream = logging.StreamHandler()
    _stream.setFormatter(_fmt)
    _log.addHandler(_stream)
    # 文件保存
    _file = logging.FileHandler("bot.log", encoding="utf-8")
    _file.setFormatter(logging.Formatter("[%(asctime)s] " + _fmt._fmt))
    _log.addHandler(_file)
    intents = Intents(public_messages=True, public_guild_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=APPID, secret=TOKEN)
