#!/usr/bin/env python3
"""Download local models into LOCAL_MODELS_DIR (or the workspace's shared ../models).

Usage:
    python download_models.py              # Phi-3 mini only
    python download_models.py --all        # same for now; add more models here later

On Linux, point every repo at one tree:

    export LOCAL_MODELS_DIR=/home/you/models
    python download_models.py
"""
import argparse
from huggingface_hub import snapshot_download

from model_paths import PHI3_HUB_ID, models_root, phi3_mini_dir


def download_phi3():
    dest = phi3_mini_dir()
    dest.mkdir(parents=True, exist_ok=True)
    print(f"Models root: {models_root()}")
    print(f"Downloading {PHI3_HUB_ID} → {dest}")
    snapshot_download(
        repo_id=PHI3_HUB_ID,
        local_dir=str(dest),
        local_dir_use_symlinks=False,
    )
    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Download models into LOCAL_MODELS_DIR")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download every model this repo knows about (currently only Phi-3 mini)",
    )
    args = parser.parse_args()
    download_phi3()
    if args.all:
        pass


if __name__ == "__main__":
    main()
