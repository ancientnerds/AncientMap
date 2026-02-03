"""
AI Mode Configuration.

Defines available modes, their models, and UI content.
Single source of truth - no hardcoding elsewhere.
"""


AI_MODES = {
    "chat": {
        "model": "mistral:7b",  # Apache 2.0 license - commercial use permitted
        "display_name": "Chat",
        "description": "Quick answers and site lookups",
        "icon": "chat",
        "max_tokens": 200,
        "examples": [
            "Find Roman temples in Greece",
            "Show me the Gate of the Sun",
            "What's the oldest site in Egypt?",
            "Show me on the map",
        ]
    },
    "research": {
        "model": "llama3.1:8b",
        "display_name": "Research",
        "description": "In-depth analysis and detailed explanations",
        "icon": "research",
        "max_tokens": 500,
        "examples": [
            "Explain the significance of Gobekli Tepe",
            "Compare Bronze Age settlements in Greece vs Italy",
            "What do we know about the builders of Stonehenge?",
            "Analyze the architectural features of Machu Picchu",
        ]
    }
}

DEFAULT_MODE = "chat"


def get_mode_config(mode: str) -> dict:
    """Get config for a mode, with fallback to default."""
    return AI_MODES.get(mode, AI_MODES[DEFAULT_MODE])


def get_all_modes() -> dict:
    """Get all mode configs for frontend."""
    return AI_MODES


def get_default_mode() -> str:
    """Get the default mode name."""
    return DEFAULT_MODE
