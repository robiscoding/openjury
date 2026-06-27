import os
import re


class ConfigurationError(Exception):
    pass


def expand_env_vars(value: str) -> str:
    """Expand ${VAR_NAME} placeholders in a string using os.environ."""

    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        var_name = match.group(1)
        resolved = os.environ.get(var_name)
        if resolved is None:
            raise ConfigurationError(
                f"Environment variable '{var_name}' referenced in config is not set."
            )
        return resolved

    return re.sub(r"\$\{([^}]+)\}", _replace, value)
