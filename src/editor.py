"""Edit clips before publishing: watermark, 9:16 crop, trim, loudnorm.

Verified working form (2026-11-19/20): the logo is pre-scaled to
194px wide and overlaid bottom-right with a 30px margin, with
``-movflags +faststart``. Earlier attempts with scale2ref /
``-c:a copy`` / ``format=yuv420p`` failed (ffmpeg exit 234), so the
filter below is the one to keep.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
LOGO = BASE / "assets" / "watermark-320.png"

POSITIONS = {
    "bottom-right": "W-w-{m}:H-h-{m}",
    "bottom-left": "{m}:H-h-{m}",
    "top-right": "W-w-{m}:{m}",
    "top-left": "{m}:{m}",
}


def overlay_expression(position: str = "bottom-right", margin: int = 30) -> str:
    """ffmpeg overlay x:y expression for a logo position."""
    expr = POSITIONS.get(position, POSITIONS["bottom-right"])
    return expr.format(m=margin)


def build_filter(size_px: int = 194, margin: int = 30,
                 position: str = "bottom-right",
                 crop_to_9x16: bool = False,
                 loudnorm: bool = False) -> str:
    """Build the -filter_complex string for watermarking a video."""
    parts = []
    if crop_to_9x16:
        # crop centre to 9:16, then scale to 1080x1920 (standard reel size)
        parts.append("[0]crop=ih*9/16:ih,scale=1080:1920[v]")
        base = "[v]"
    else:
        base = "[0]"
    parts.append(
        f"[1]scale={size_px}:-1[vlogo];"
        f"{base}[vlogo]overlay={overlay_expression(position, margin)}"
    )
    filt = ",".join(parts) if crop_to_9x16 else parts[-1]
    if loudnorm:
        filt += ",loudnorm=I=-16:TP=-1.5:LRA=11"
    return filt


def build_ffmpeg_command(inp: Path | str, out: Path | str,
                         size_px: int = 194, margin: int = 30,
                         position: str = "bottom-right",
                         crop_to_9x16: bool = False,
                         max_duration_seconds: int = 0,
                         loudnorm: bool = False) -> list[str]:
    """Build (but do not run) the ffmpeg command for a watermarked video."""
    cmd = ["ffmpeg", "-y", "-i", str(inp), "-i", str(LOGO),
           "-filter_complex",
           build_filter(size_px, margin, position, crop_to_9x16, loudnorm)]
    if max_duration_seconds and max_duration_seconds > 0:
        cmd += ["-t", str(max_duration_seconds)]
    cmd += ["-movflags", "+faststart", str(out)]
    return cmd


def watermark_video(inp: Path | str, out: Path | str, size_px: int = 194,
                    margin: int = 30, position: str = "bottom-right",
                    crop_to_9x16: bool = False,
                    max_duration_seconds: int = 0,
                    loudnorm: bool = False) -> Path:
    """Watermark a video with the NEWS OUSSAMA logo. Returns output path."""
    cmd = build_ffmpeg_command(inp, out, size_px, margin, position,
                               crop_to_9x16, max_duration_seconds, loudnorm)
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"video: {inp} -> {out}")
    return Path(out)


def watermark_photo(inp: Path | str, out: Path | str, size: int = 320,
                    margin: int = 30) -> Path:
    """Watermark a photo with PIL. Logo scales to ~18% of image width."""
    logo = Image.open(LOGO).convert("RGBA")
    if size != 320:
        logo = logo.resize((size, size), Image.LANCZOS)
    im = Image.open(inp).convert("RGBA")
    w, h = im.size
    s = max(120, min(360, int(w * 0.18)))
    if s != logo.size[0]:
        logo = logo.resize((s, s), Image.LANCZOS)
    im.alpha_composite(logo, (w - s - margin, h - s - margin))
    im.convert("RGB").save(out, quality=92)
    print(f"photo: {inp} -> {out} ({w}x{h}, logo {s}px bottom-right)")
    return Path(out)


def cover_frame(video: Path | str, out: Path | str,
                seconds: float = 3.0) -> Path:
    """Extract a still frame (for a thumbnail / cover) from a video."""
    cmd = ["ffmpeg", "-y", "-ss", str(seconds), "-i", str(video),
           "-frames:v", "1", str(out)]
    print("running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    return Path(out)
