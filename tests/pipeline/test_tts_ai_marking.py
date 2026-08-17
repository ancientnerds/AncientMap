# SPDX-License-Identifier: AGPL-3.0-only
"""Art. 50(2) EU AI Act: machine-readable AI marking in generated TTS MP3s."""

from mutagen.id3 import ID3

from pipeline.lyra.tts_generator import tag_mp3_ai_generated


def test_tag_mp3_ai_generated(tmp_path):
    f = tmp_path / "x.mp3"
    # Minimal MPEG frame header + padding — enough for ID3 to attach a tag.
    f.write_bytes(b"\xff\xfb\x90\x00" + b"\x00" * 128)

    tag_mp3_ai_generated(f)

    frames = {fr.desc: str(fr.text[0]) for fr in ID3(f).getall("TXXX")}
    assert frames["AI-Generated"] == "true"
    assert "MiniMax" in frames["AI-System"]
