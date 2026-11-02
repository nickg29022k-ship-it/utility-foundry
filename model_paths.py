"""Shared local-model locations.

Set LOCAL_MODELS_DIR to one folder used by every repo, e.g.:

    export LOCAL_MODELS_DIR=/home/you/models

Phi-3 files then live at $LOCAL_MODELS_DIR/phi3-mini.
If unset, this repo uses the shared ../models directory at the code-workspace root.
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PHI3_DIR_NAME = "phi3-mini"
PHI3_HUB_ID = "microsoft/Phi-3-mini-4k-instruct"


def models_root() -> Path:
    override = os.environ.get("LOCAL_MODELS_DIR") or os.environ.get("MODELS_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT.parent / "models"


def phi3_mini_dir() -> Path:
    return models_root() / PHI3_DIR_NAME
