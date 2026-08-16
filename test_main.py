import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class YouTubeUrlTests(unittest.TestCase):
    def test_extract_video_id_from_shorts_url(self):
        video_id = main.extract_youtube_video_id("https://www.youtube.com/shorts/abcDEF12345")

        self.assertEqual(video_id, "abcDEF12345")

    def test_extract_video_id_from_watch_url(self):
        video_id = main.extract_youtube_video_id("https://www.youtube.com/watch?v=abcDEF12345&t=4")

        self.assertEqual(video_id, "abcDEF12345")

    def test_extract_video_id_from_short_youtu_be_url(self):
        video_id = main.extract_youtube_video_id("https://youtu.be/abcDEF12345")

        self.assertEqual(video_id, "abcDEF12345")


class TranscriptionTests(unittest.TestCase):
    def test_transcribe_video_extracts_audio_and_returns_whisper_text(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = Path(temp_dir) / "sample.mp4"
            video_path.write_bytes(b"fake video")

            with patch("main.subprocess.run") as run:
                run.return_value.stdout = "[00:00:00.000 --> 00:00:01.000] hello world\n"

                transcript = main.transcribe_video_file(video_path)

        self.assertEqual(transcript, "hello world")
        self.assertEqual(run.call_count, 2)
        self.assertIn("/opt/homebrew/bin/ffmpeg", run.call_args_list[0].args[0][0])
        self.assertIn("/opt/homebrew/bin/whisper-cli", run.call_args_list[1].args[0][0])


class OpenAIResponseTests(unittest.TestCase):
    def test_incomplete_blocked_response_returns_readable_fallback(self):
        result = main.incomplete_ai_response(
            {
                "status": "incomplete",
                "content_filters": [
                    {"source_type": "completion", "blocked": True}
                ],
            }
        )

        self.assertEqual(result["score"], 50)
        self.assertIn("safety filter blocked", result["suggestions"][0])


if __name__ == "__main__":
    unittest.main()
