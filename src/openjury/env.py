import os
from typing import Tuple

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"


class EnvironmentError(Exception):
    pass


def get_env_vars() -> dict[str, str]:
    provider = os.getenv("LLM_PROVIDER", "openrouter").lower()

    if provider == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY environment variable is required when using OpenAI provider.\n"
                "Set it with: os.environ['OPENAI_API_KEY'] = 'your-key-here'"
            )
        return {"api_key": api_key, "base_url": OPENAI_BASE_URL}

    elif provider == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENROUTER_API_KEY environment variable is required when using OpenRouter provider.\n"
                "Set it with: os.environ['OPENROUTER_API_KEY'] = 'your-key-here'"
            )
        return {"api_key": api_key, "base_url": OPENROUTER_BASE_URL}

    else:
        raise EnvironmentError(
            f"Unsupported LLM_PROVIDER: {provider}. "
            "Supported providers: 'openai', 'openrouter'"
        )
