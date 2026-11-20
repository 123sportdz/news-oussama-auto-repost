#!/usr/bin/env python3
"""Thin wrapper — the real editor lives in src/editor.py.

Usage:
  python3 watermark.py photo input.jpg output.jpg [--size 194]
  python3 watermark.py video input.mp4 output.mp4 [--size 194]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.editor import watermark_photo, watermark_video  # noqa: E402

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=["photo", "video"])
    p.add_argument("inp")
    p.add_argument("out")
    p.add_argument("--size", type=int, default=194)
    a = p.parse_args()
    if a.kind == "photo":
        watermark_photo(a.inp, a.out, a.size)
    else:
        watermark_video(a.inp, a.out, a.size)
