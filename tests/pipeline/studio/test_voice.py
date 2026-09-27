from __future__ import annotations

import copy
import json
import sys
import types

import pytest

from pipeline.studio import voice
from pipeline.studio.episode import EpisodeWorkspace
from pipeline.studio.errors import StudioError
from tests.pipeline.studio import script_fixtures as sf


def test_chunks_pack_sentences_under_the_limit():
    sentence = "The block was cut in the quarry. "
    text = sentence * 60
    chunks = voice.chunk_text(text)
    assert all(len(c) <= voice.MAX_CHUNK_CHARS for c in chunks)
    assert " ".join(chunks) == text.strip()
    assert len(chunks) == 2


def test_a_single_overlong_sentence_is_refused():
    with pytest.raises(StudioError, match="exceeds 1000: split it"):
        voice.chunk_text("word " * 300 + ".")


def test_quota_floor():
    voice.check_quota(10, 35)
    with pytest.raises(StudioError, match="5-hour window at 9%"):
        voice.check_quota(9, 35)


class Fakes:
    def __init__(self, interval=99):
        self.interval = interval
        self.synth_calls = []
        self.transcribe_calls = []
        self.quota_calls = 0

    def quota(self):
        self.quota_calls += 1
        return self.interval, 40

    def synth(self, text, out, voice_id, speed):
        self.synth_calls.append((out.stem, voice_id, speed))
        out.write_bytes(b"mp3")
        return 0.4 * len(text.split())

    def transcribe(self, audio):
        self.transcribe_calls.append(audio.stem)
        beat = next(b for b in sf.script()["beats"] if b["id"] == audio.stem)
        heard = beat["spoken"].split()
        return [(w, i * 0.4, i * 0.4 + 0.3) for i, w in enumerate(heard)]


def _ws(tmp_path):
    return EpisodeWorkspace(tmp_path / "ep", "baalbek-c5")


def test_voice_writes_words_in_display_spelling(tmp_path):
    ws, fakes = _ws(tmp_path), Fakes()
    words = voice.voice_episode(
        ws, sf.script(), quota=fakes.quota, synth=fakes.synth, transcribe=fakes.transcribe
    )
    assert fakes.quota_calls == 1
    assert [c[0] for c in fakes.synth_calls] == [b["id"] for b in sf.script()["beats"]]
    b01 = words["b01"]
    assert [w["w"] for w in b01["words"]][:6] == [
        "This",
        "stone",
        "weighs",
        "about",
        "1,000",
        "tonnes.",
    ]
    assert b01["duration_s"] == pytest.approx(0.4 * 12)
    assert json.loads(ws.words.read_text(encoding="utf-8")) == words


def test_unchanged_beats_are_not_narrated_again(tmp_path):
    ws, fakes = _ws(tmp_path), Fakes()
    data = sf.script()
    voice.voice_episode(ws, data, quota=fakes.quota, synth=fakes.synth, transcribe=fakes.transcribe)
    again = Fakes(interval=0)
    voice.voice_episode(ws, data, quota=again.quota, synth=again.synth, transcribe=again.transcribe)
    assert again.synth_calls == [] and again.quota_calls == 0 and again.transcribe_calls == []
    changed = copy.deepcopy(data)
    changed["beats"][6]["spoken"] = changed["beats"][6]["display"] = (
        "So the balance tips toward Roman engineers today."
    )
    third = Fakes()
    third.transcribe = lambda audio: [
        (w, i * 0.3, i * 0.3 + 0.2) for i, w in enumerate(changed["beats"][6]["spoken"].split())
    ]
    voice.voice_episode(
        ws, changed, quota=third.quota, synth=third.synth, transcribe=third.transcribe
    )
    assert [c[0] for c in third.synth_calls] == ["b07"]


def test_low_quota_refuses_before_any_narration(tmp_path):
    ws, fakes = _ws(tmp_path), Fakes(interval=5)
    with pytest.raises(StudioError, match="below 10%"):
        voice.voice_episode(
            ws, sf.script(), quota=fakes.quota, synth=fakes.synth, transcribe=fakes.transcribe
        )
    assert fakes.synth_calls == []


def test_the_studio_transcribes_on_the_nvidia(monkeypatch, tmp_path):
    seen = {}

    class FakeModel:
        def __init__(self, name, **kwargs):
            seen.update(kwargs)

        def transcribe(self, path, **kwargs):
            return [], None

    monkeypatch.setitem(
        sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel)
    )
    assert voice.whisper_words(tmp_path / "b01.mp3") == []
    assert seen == {"device": "cuda", "device_index": 0, "compute_type": "float16"}


def test_stale_beats_name_every_mp3_the_script_moved_past(tmp_path):
    ws, fakes = _ws(tmp_path), Fakes()
    data = sf.script()
    assert voice.stale_beats(ws, data) == [
        "voice/manifest.json does not exist: run `episode voice`"
    ]
    voice.voice_episode(ws, data, quota=fakes.quota, synth=fakes.synth, transcribe=fakes.transcribe)
    assert voice.stale_beats(ws, data) == []
    changed = copy.deepcopy(data)
    changed["beats"][0]["spoken"] = "Another sentence entirely."
    assert voice.stale_beats(ws, changed) == ["b01: voice/b01.mp3 is stale; run `episode voice`"]
    faster = sf.mutated_script(lambda d: d["voice"].update(speed=1.06))
    assert len(voice.stale_beats(ws, faster)) == len(data["beats"])
