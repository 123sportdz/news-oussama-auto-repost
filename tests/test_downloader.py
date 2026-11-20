"""Tests for the downloader fallback: yt-dlp metadata when post read fails."""
import json
import subprocess
import unittest
from unittest import mock

from src import downloader


class VideoInfoTest(unittest.TestCase):
    def test_video_info_from_ytdlp_json(self):
        fake = {
            "id": "2187826579280394",
            "title": "3.9K views · 247 reactions | أهازيج جمهور | Goal algeria",
            "description": "أهازيج جمهور شبيبة القبائل",
            "uploader": "Goal algeria ",
            "upload_date": "20261120",
        }
        completed = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0,
            stdout=json.dumps(fake), stderr="")
        with mock.patch.object(downloader.subprocess, "run",
                               return_value=completed):
            info = downloader.video_info(
                "https://www.facebook.com/reel/2187826579280394")
        self.assertEqual(info["post_id"], "2187826579280394")
        self.assertEqual(info["caption"], "أهازيج جمهور شبيبة القبائل")
        self.assertEqual(info["owner"], "Goal algeria")
        self.assertEqual(info["media_type"], "video")

    def test_video_info_falls_back_to_title(self):
        fake = {
            "id": "123",
            "title": "1.2K views · 10 reactions | عنوان المقطع | صفحة",
            "description": "",
            "uploader": "صفحة",
            "upload_date": "20261120",
        }
        completed = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0,
            stdout=json.dumps(fake), stderr="")
        with mock.patch.object(downloader.subprocess, "run",
                               return_value=completed):
            info = downloader.video_info(
                "https://www.facebook.com/reel/123456789")
        self.assertEqual(info["caption"], "عنوان المقطع")

    def test_post_info_falls_back_when_cli_cannot_see_post(self):
        cli_fail = subprocess.CompletedProcess(
            args=["facebook-cli"], returncode=1, stdout="", stderr="")
        ytdlp_ok = subprocess.CompletedProcess(
            args=["yt-dlp"], returncode=0,
            stdout=json.dumps({
                "id": "2187826579280394",
                "title": "t", "description": "نص",
                "uploader": "Goal algeria", "upload_date": "20261120",
            }), stderr="")
        calls = {"n": 0}

        def fake_run(cmd, **kwargs):
            calls["n"] += 1
            return cli_fail if "facebook-cli" in cmd[0] else ytdlp_ok

        with mock.patch.object(downloader.subprocess, "run",
                               side_effect=fake_run):
            info = downloader.post_info(
                "https://www.facebook.com/reel/2187826579280394")
        self.assertEqual(calls["n"], 2)
        self.assertEqual(info["caption"], "نص")
        self.assertEqual(info["owner"], "Goal algeria")


if __name__ == "__main__":
    unittest.main()
