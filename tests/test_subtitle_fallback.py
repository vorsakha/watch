import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import watch_session


class SubtitleFallbackTests(unittest.TestCase):
    def test_falls_back_to_subtitlecat_after_script_source_failures(self):
        target = watch_session.WatchTarget(query="Some Show S01E01", title="Some Show")
        subtitle_source = watch_session.SourceCandidate(
            provider="subtitlecat",
            url="https://www.subtitlecat.com/subs/some-show-en.srt",
            confidence=0.45,
            script_text=("HELLO\n" * 80).strip(),
        )

        with patch.object(watch_session, "_fetch_imsdb", side_effect=watch_session.SourceError("SOURCE_NOT_FOUND", "x")), patch.object(
            watch_session, "_fetch_transcribed_anime", side_effect=watch_session.SourceError("SOURCE_NOT_FOUND", "x")
        ), patch.object(watch_session, "_fetch_generic", side_effect=watch_session.SourceError("SOURCE_URL_REQUIRED", "x")), patch.object(
            watch_session,
            "_fetch_subtitlecat",
            return_value=(
                subtitle_source,
                ["source:subtitlecat:search:success", "source:subtitlecat:download:success"],
            ),
        ):
            source, trace, warnings = watch_session.fetch_script_text(target, timeout_sec=5)

        self.assertEqual(source.provider, "subtitlecat")
        self.assertEqual(warnings, [])
        self.assertEqual(
            trace,
            [
                "source:imsdb:failed:SOURCE_NOT_FOUND",
                "source:transcribed_anime:failed:SOURCE_NOT_FOUND",
                "source:generic_transcript:failed:SOURCE_URL_REQUIRED",
                "source:subtitlecat:search:success",
                "source:subtitlecat:download:success",
                "source:subtitlecat:success",
            ],
        )

    def test_does_not_call_subtitlecat_when_imsdb_succeeds(self):
        target = watch_session.WatchTarget(query="Some Movie", title="Some Movie", content_type="movie")
        imsdb_source = watch_session.SourceCandidate(provider="imsdb", url="https://imsdb.com/x", confidence=0.9, script_text=("A\n" * 200))

        with patch.object(watch_session, "_fetch_imsdb", return_value=imsdb_source), patch.object(
            watch_session, "_fetch_subtitlecat"
        ) as subtitle_mock:
            source, trace, _warnings = watch_session.fetch_script_text(target, timeout_sec=5)

        self.assertEqual(source.provider, "imsdb")
        self.assertEqual(trace, ["source:imsdb:success"])
        subtitle_mock.assert_not_called()

    def test_extract_text_from_subtitle_payload_strips_srt_vtt_metadata(self):
        payload = """WEBVTT

1
00:00:01.000 --> 00:00:03.500
<i>Hello there.</i>

NOTE this is metadata
2
00:00:04,000 --> 00:00:06,000
[MUSIC]
General Kenobi!
"""
        text = watch_session._extract_text_from_subtitle_payload(payload)
        self.assertIn("Hello there.", text)
        self.assertIn("General Kenobi!", text)
        self.assertNotIn("WEBVTT", text)
        self.assertNotIn("00:00:", text)
        self.assertNotIn("[MUSIC]", text)


if __name__ == "__main__":
    unittest.main()
