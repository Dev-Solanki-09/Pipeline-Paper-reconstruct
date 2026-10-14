"""ExamForge language plugins."""

from examforge.lang.plugins.en import EnglishPlugin
from examforge.lang.plugins.hi import HindiPlugin
from examforge.lang.plugins.scaffolded import ScaffoldedScriptPlugin, get_scaffolded_plugins

__all__ = [
    "EnglishPlugin",
    "HindiPlugin",
    "ScaffoldedScriptPlugin",
    "get_scaffolded_plugins",
]
