from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    app_id: str | None
    bot_token: str | None
    assistant_name: str
    anthropic_api_key: str | None
    anthropic_base_url: str | None
    model: str
    max_turns: int
    qq_max_length: int
    viz_host: str
    viz_port: int
    rag_server_command: str
    rag_server_cwd: str
    guardian_enabled: bool
    guardian_llm_enabled: bool
    guardian_fail_mode: str
    guardian_block_message: str
    consolidation_hour: int
    consolidation_minute: int
    hitl_enabled: bool
    hitl_guarded_tools: str
    hitl_timeout_seconds: int


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        app_id=os.getenv("QQ_APP_ID"),
        bot_token=os.getenv("QQ_BOT_TOKEN"),
        assistant_name=os.getenv("ASSISTANT_NAME", "OpenClaw"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL"),
        model=os.getenv("OPENCLAW_MODEL", "GLM-4.5-air"),
        max_turns=int(os.getenv("OPENCLAW_MAX_TURNS", "10")),
        qq_max_length=int(os.getenv("QQ_MAX_LENGTH", "2000")),
        viz_host=os.getenv("OPENCLAW_VIZ_HOST", "localhost"),
        viz_port=int(os.getenv("OPENCLAW_VIZ_PORT", "8080")),
        rag_server_command=os.getenv("RAG_SERVER_COMMAND", "python"),
        rag_server_cwd=os.getenv("RAG_SERVER_CWD", ""),
        guardian_enabled=os.getenv("GUARDIAN_ENABLED", "true").lower() == "true",
        guardian_llm_enabled=os.getenv("GUARDIAN_LLM_ENABLED", "false").lower() == "true",
        guardian_fail_mode=os.getenv("GUARDIAN_FAIL_MODE", "open"),
        guardian_block_message=os.getenv("GUARDIAN_BLOCK_MESSAGE", "你的消息触发了安全过滤，请正常交流。"),
        consolidation_hour=int(os.getenv("CONSOLIDATION_HOUR", "2")),
        consolidation_minute=int(os.getenv("CONSOLIDATION_MINUTE", "0")),
        hitl_enabled=os.getenv("HITL_ENABLED", "false").lower() == "true",
        hitl_guarded_tools=os.getenv("HITL_GUARDED_TOOLS", ""),
        hitl_timeout_seconds=int(os.getenv("HITL_TIMEOUT_SECONDS", "60")),
    )
