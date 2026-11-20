"""Tests for the video editor command builder (no ffmpeg run needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.editor import build_ffmpeg_command, build_filter, overlay_expression


class TestEditor(unittest.TestCase):
    def test_default_watermark_bottom_right(self):
        filt = build_filter()
        self.assertIn("scale=194:-1", filt)
        self.assertIn("overlay=W-w-30:H-h-30", filt)

    def test_positions(self):
        self.assertEqual(overlay_expression("bottom-left", 30), "30:H-h-30")
        self.assertEqual(overlay_expression("top-right", 10), "W-w-10:10")

    def test_command_shape(self):
        cmd = build_ffmpeg_command("in.mp4", "out.mp4")
        self.assertEqual(cmd[0], "ffmpeg")
        self.assertIn("-movflags", cmd)
        self.assertIn("+faststart", cmd)
        self.assertEqual(cmd[-1], "out.mp4")

    def test_crop_9x16(self):
        filt = build_filter(crop_to_9x16=True)
        self.assertIn("crop=ih*9/16:ih", filt)
        self.assertIn("scale=1080:1920", filt)

    def test_trim(self):
        cmd = build_ffmpeg_command("in.mp4", "out.mp4",
                                   max_duration_seconds=60)
        self.assertIn("-t", cmd)
        self.assertIn("60", cmd)

    def test_no_trim_by_default(self):
        cmd = build_ffmpeg_command("in.mp4", "out.mp4")
        self.assertNotIn("-t", cmd)

    def test_loudnorm(self):
        # loudnorm is an audio filter: it must go through -af, never
        # into the video filter chain.
        cmd = build_ffmpeg_command("in.mp4", "out.mp4", loudnorm=True)
        self.assertIn("-af", cmd)
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", cmd)
        filt = build_filter()
        self.assertNotIn("loudnorm", filt)

    def test_no_loudnorm_by_default(self):
        cmd = build_ffmpeg_command("in.mp4", "out.mp4")
        self.assertNotIn("-af", cmd)


if __name__ == "__main__":
    unittest.main()
