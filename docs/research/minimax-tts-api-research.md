# MiniMax Text-to-Speech (TTS) API Research

**Date:** 2026-04-04
**Status:** Complete
**Relevance:** Project uses MiniMax Token Plan with `api.minimax.io` base URL and Bearer auth (env: `LYRA_MINIMAX_API_KEY`)

---

## 1. API Endpoints

### Synchronous TTS (up to 10,000 characters)

```
POST https://api.minimax.io/v1/t2a_v2
```

Alternative low-latency endpoint (Western US):
```
POST https://api-uw.minimax.io/v1/t2a_v2
```

### Async Long-Text TTS (up to 1,000,000 characters)

```
POST https://api.minimax.io/v1/t2a_async_v2          # Create task
GET  https://api.minimax.io/v1/query/t2a_async_query_v2?task_id={task_id}  # Poll status
GET  https://api.minimax.io/v1/files/retrieve_content?file_id={file_id}    # Download audio (URL valid 9 hours)
```

### Voice Management

```
POST https://api.minimax.io/v1/get_voice              # List available voices
```

### Voice Cloning

```
POST https://api.minimax.io/v1/voice_clone             # Clone from audio file (10s-5min MP3/M4A/WAV)
```

---

## 2. Authentication

Same as project's existing MiniMax integration:
```
Authorization: Bearer {LYRA_MINIMAX_API_KEY}
Content-Type: application/json
```

No `group_id` query parameter is needed for the Token Plan. The older `api.minimaxi.chat` endpoint required `?GroupId=...`, but `api.minimax.io` with Token Plan keys does not.

---

## 3. Available Models

| Model | Quality | Latency | Languages | Notes |
|-------|---------|---------|-----------|-------|
| `speech-2.8-hd` | Highest | Higher | 40+ | Latest HD, best quality |
| `speech-2.8-turbo` | High | Low | 40+ | Latest turbo, real-time |
| `speech-2.6-hd` | Very High | Higher | 40+ | Previous gen HD |
| `speech-2.6-turbo` | High | Low | 40+ | Previous gen turbo |
| `speech-02-hd` | High | Higher | 24 | Legacy HD |
| `speech-02-turbo` | Good | Low | 24 | Legacy turbo |
| `speech-01-hd` | Good | Higher | Fewer | Oldest HD |
| `speech-01-turbo` | Basic | Lowest | Fewer | Oldest turbo |

**Recommendation:** Use `speech-2.8-hd` for quality (articles, narration) or `speech-2.8-turbo` for real-time/interactive use.

---

## 4. Complete Request Body Schema

```json
{
  "model": "speech-2.8-hd",
  "text": "The text to synthesize. Max 10,000 characters. Supports pause markers <#2.5#> for 2.5s pause, and interjections like (sighs), (laughs), (coughs).",
  "stream": false,
  "output_format": "url",
  "language_boost": "English",

  "voice_setting": {
    "voice_id": "English_expressive_narrator",
    "speed": 1.0,
    "vol": 1.0,
    "pitch": 0,
    "emotion": "happy",
    "text_normalization": false,
    "latex_read": false
  },

  "audio_setting": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1,
    "force_cbr": false
  },

  "voice_modify": {
    "pitch": 0,
    "intensity": 0,
    "timbre": 0,
    "sound_effects": ""
  },

  "pronunciation_dict": {
    "tone": ["Gobekli Tepe/goh-BEHK-lee TEH-peh", "Nabta Playa/NOB-tah PLY-ah"]
  },

  "subtitle_enable": false,

  "timbre_weights": [
    { "voice_id": "English_expressive_narrator", "weight": 70 },
    { "voice_id": "English_WiseScholar", "weight": 30 }
  ]
}
```

### Parameter Details

#### Core (Required)
| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | Model name (see table above) |
| `text` | string | Input text, max 10,000 chars |

#### Voice Setting
| Parameter | Type | Range/Options | Default |
|-----------|------|---------------|---------|
| `voice_id` | string | See voice list below | Required |
| `speed` | float | 0.5 - 2.0 | 1.0 |
| `vol` | float | 0.01 - 10.0 | 1.0 |
| `pitch` | int | -12 to +12 (semitones) | 0 |
| `emotion` | string | `happy`, `sad`, `angry`, `fearful`, `disgusted`, `surprised`, `calm`, `fluent`, `whisper` | (none) |
| `text_normalization` | bool | Normalize numbers/abbreviations | false |
| `latex_read` | bool | Read LaTeX expressions aloud | false |

#### Audio Setting
| Parameter | Type | Options | Default |
|-----------|------|---------|---------|
| `format` | string | `mp3`, `pcm`, `flac`, `wav` | `mp3` |
| `sample_rate` | int | 8000, 16000, 22050, 24000, 32000, 44100 | (model default) |
| `bitrate` | int | 32000, 64000, 128000, 256000 (MP3 only) | 128000 |
| `channel` | int | 1 (mono), 2 (stereo) | 1 |
| `force_cbr` | bool | Force constant bitrate | false |

#### Voice Modify (post-processing effects)
| Parameter | Type | Range | Description |
|-----------|------|-------|-------------|
| `pitch` | int | -100 to +100 | Deepen/brighten |
| `intensity` | int | -100 to +100 | Stronger/softer |
| `timbre` | int | -100 to +100 | Nasal/crisp |
| `sound_effects` | string | `spacious_echo`, `auditorium_echo`, `lofi_telephone`, `robotic` | Effect overlay |

#### Other Options
| Parameter | Type | Description |
|-----------|------|-------------|
| `stream` | bool | Enable SSE streaming (default: false) |
| `output_format` | string | `"url"` (returns download URL, valid 24h) or `"hex"` (returns hex-encoded audio in response). Non-streaming only. Default: `"hex"` |
| `language_boost` | string | Bias pronunciation: `auto`, `English`, `Chinese`, `Japanese`, `French`, `German`, `Spanish`, `Arabic`, `Russian`, `Korean`, `Portuguese`, `Turkish`, `Dutch`, `Hindi`, `Italian`, `Thai`, `Polish`, `Vietnamese`, `Indonesian`, `Filipino`, `Tamil`, `Persian`, and more (40+ total) |
| `pronunciation_dict.tone` | array of strings | Custom pronunciations: `"word/pronunciation"` format |
| `subtitle_enable` | bool | Generate subtitle/timestamp file |
| `timbre_weights` | array | Mix up to 4 voices with weights (1-100) |

---

## 5. Response Format

### Non-Streaming with `output_format: "hex"` (default)

```json
{
  "data": {
    "audio": "4944330400000000002354...",
    "subtitle_file": "",
    "status": 2
  },
  "extra_info": {
    "audio_length": 3450,
    "audio_sample_rate": 32000,
    "audio_size": 55200,
    "bitrate": 128000,
    "word_count": 42,
    "invisible_character_ratio": 0.0,
    "usage_characters": 42,
    "audio_format": "mp3",
    "audio_channel": 1
  },
  "trace_id": "abc123...",
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

The `data.audio` field contains **hex-encoded** audio bytes. To save as file:
```python
audio_bytes = bytes.fromhex(response["data"]["audio"])
with open("output.mp3", "wb") as f:
    f.write(audio_bytes)
```

### Non-Streaming with `output_format: "url"`

```json
{
  "data": {
    "audio": "https://cdn.minimax.io/audio/...",
    "status": 2
  },
  "extra_info": { ... },
  "base_resp": { "status_code": 0, "status_msg": "success" }
}
```

The `data.audio` field contains a **download URL valid for 24 hours**.

### Streaming (SSE)

Server-Sent Events, one JSON per line:
```json
{"data":{"audio":"4944330400...","status":1},"trace_id":"...","base_resp":{"status_code":0,"status_msg":""}}
{"data":{"audio":"ff03c800...","status":1},"trace_id":"...","base_resp":{"status_code":0,"status_msg":""}}
{"data":{"audio":"","status":2},"trace_id":"...","extra_info":{...},"base_resp":{"status_code":0,"status_msg":"success"}}
```

- `status: 1` = synthesizing (contains hex audio chunk)
- `status: 2` = completed (contains aggregated metadata in `extra_info`)

Each chunk's `data.audio` is hex-encoded. Concatenate `bytes.fromhex(chunk)` to build the full audio.

---

## 6. English Voice IDs (Complete List: 45 Voices)

| voice_id | Description |
|----------|-------------|
| `English_expressive_narrator` | Expressive Narrator |
| `English_radiant_girl` | Radiant Girl |
| `English_magnetic_voiced_man` | Magnetic-voiced Male |
| `English_compelling_lady1` | Compelling Lady |
| `English_Aussie_Bloke` | Aussie Bloke |
| `English_captivating_female1` | Captivating Female |
| `English_Upbeat_Woman` | Upbeat Woman |
| `English_Trustworth_Man` | Trustworthy Man |
| `English_CalmWoman` | Calm Woman |
| `English_UpsetGirl` | Upset Girl |
| `English_Gentle-voiced_man` | Gentle-voiced Man |
| `English_Whispering_girl` | Whispering Girl |
| `English_Diligent_Man` | Diligent Man |
| `English_Graceful_Lady` | Graceful Lady |
| `English_ReservedYoungMan` | Reserved Young Man |
| `English_PlayfulGirl` | Playful Girl |
| `English_ManWithDeepVoice` | Man With Deep Voice |
| `English_MaturePartner` | Mature Partner |
| `English_FriendlyPerson` | Friendly Guy |
| `English_MatureBoss` | Bossy Lady |
| `English_Debator` | Male Debater |
| `English_LovelyGirl` | Lovely Girl |
| `English_Steadymentor` | Reliable Man |
| `English_Deep-VoicedGentleman` | Deep-voiced Gentleman |
| `English_Wiselady` | Wise Lady |
| `English_CaptivatingStoryteller` | Captivating Storyteller |
| `English_DecentYoungMan` | Decent Young Man |
| `English_SentimentalLady` | Sentimental Lady |
| `English_ImposingManner` | Imposing Queen |
| `English_SadTeen` | Teen Boy |
| `English_PassionateWarrior` | Passionate Warrior |
| `English_WiseScholar` | Wise Scholar |
| `English_Soft-spokenGirl` | Soft-Spoken Girl |
| `English_SereneWoman` | Serene Woman |
| `English_ConfidentWoman` | Confident Woman |
| `English_PatientMan` | Patient Man |
| `English_Comedian` | Comedian |
| `English_BossyLeader` | Bossy Leader |
| `English_Strong-WilledBoy` | Strong-Willed Boy |
| `English_StressedLady` | Stressed Lady |
| `English_AssertiveQueen` | Assertive Queen |
| `English_AnimeCharacter` | Female Narrator |
| `English_Jovialman` | Jovial Man |
| `English_WhimsicalGirl` | Whimsical Girl |
| `English_Kind-heartedGirl` | Kind-Hearted Girl |

**Good defaults for this project (archaeology/history narration):**
- `English_expressive_narrator` -- versatile, expressive narration
- `English_WiseScholar` -- authoritative, scholarly tone
- `English_CaptivatingStoryteller` -- engaging storytelling
- `English_Insightful_Speaker` -- (referenced in docs, may need verification via Get Voice API)

To get the full live catalog (including non-English and cloned voices):
```bash
curl -X POST https://api.minimax.io/v1/get_voice \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{"voice_type": "all"}'
```

---

## 7. Error Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1000 | Unknown error |
| 1001 | Timeout |
| 1002 | Rate limit exceeded |
| 1004 | Authentication failed |
| 1039 | TPM (tokens per minute) rate limit |
| 1042 | Invalid characters exceed 10% of input |
| 2013 | Invalid input parameters |

---

## 8. Pricing (Pay-as-you-go reference)

| Model | Cost per 1K characters |
|-------|----------------------|
| speech-2.6-hd / speech-2.8-hd | ~$0.13 |
| speech-2.6-turbo / speech-2.8-turbo | ~$0.078 |

On the Token Plan, TTS usage draws from the token budget. One MiniMax token is approximately one character.

---

## 9. Test curl Commands

### Minimal test (non-streaming, URL output -- easiest to verify)

```bash
curl -X POST https://api.minimax.io/v1/t2a_v2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{
    "model": "speech-2.8-hd",
    "text": "The ancient city of Gobekli Tepe, built around 9500 BCE, challenges everything we thought we knew about early human civilization.",
    "stream": false,
    "output_format": "url",
    "language_boost": "English",
    "voice_setting": {
      "voice_id": "English_expressive_narrator",
      "speed": 1.0,
      "vol": 1.0,
      "pitch": 0
    },
    "audio_setting": {
      "sample_rate": 32000,
      "bitrate": 128000,
      "format": "mp3",
      "channel": 1
    }
  }'
```

This returns a JSON with `data.audio` containing a download URL (valid 24 hours). Easiest way to listen to the result.

### Minimal test (non-streaming, hex output -- for programmatic use)

```bash
curl -X POST https://api.minimax.io/v1/t2a_v2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{
    "model": "speech-2.8-turbo",
    "text": "Hello world, this is a test of MiniMax text to speech.",
    "stream": false,
    "output_format": "hex",
    "voice_setting": {
      "voice_id": "English_WiseScholar",
      "speed": 1.0
    },
    "audio_setting": {
      "format": "mp3"
    }
  }' | python -c "import sys,json; open('test.mp3','wb').write(bytes.fromhex(json.load(sys.stdin)['data']['audio']))"
```

### With emotion and pronunciation dictionary

```bash
curl -X POST https://api.minimax.io/v1/t2a_v2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{
    "model": "speech-2.8-hd",
    "text": "Incredible! The excavation at Gobekli Tepe has revealed structures that predate Stonehenge by over six thousand years. (sighs) And yet, so much remains buried beneath the surface.",
    "stream": false,
    "output_format": "url",
    "language_boost": "English",
    "voice_setting": {
      "voice_id": "English_CaptivatingStoryteller",
      "speed": 0.9,
      "vol": 1.0,
      "pitch": 0,
      "emotion": "happy"
    },
    "audio_setting": {
      "sample_rate": 44100,
      "bitrate": 128000,
      "format": "mp3",
      "channel": 1
    },
    "pronunciation_dict": {
      "tone": [
        "Gobekli Tepe/goh-BEHK-lee TEH-peh"
      ]
    }
  }'
```

### List all available voices

```bash
curl -X POST https://api.minimax.io/v1/get_voice \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{"voice_type": "system"}'
```

### Streaming test

```bash
curl -X POST https://api.minimax.io/v1/t2a_v2 \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $LYRA_MINIMAX_API_KEY" \
  -d '{
    "model": "speech-2.8-turbo",
    "text": "This is a streaming test for real-time audio synthesis.",
    "stream": true,
    "voice_setting": {
      "voice_id": "English_expressive_narrator",
      "speed": 1.0
    },
    "audio_setting": {
      "format": "mp3"
    }
  }'
```

---

## 10. Integration Notes for This Project

### Existing Pattern
The project already has `pipeline/lyra/minimax_shared.py` with `create_minimax_client()` that creates an `httpx.Client` with base URL `https://api.minimax.io` and Bearer auth. A TTS function can follow the same pattern:

```python
MINIMAX_TTS_PATH = "/v1/t2a_v2"

def minimax_tts(client: httpx.Client, text: str, voice_id: str = "English_expressive_narrator") -> bytes:
    """Generate speech audio from text via MiniMax TTS API."""
    resp = client.post(
        MINIMAX_TTS_PATH,
        json={
            "model": "speech-2.8-hd",
            "text": text,
            "stream": False,
            "output_format": "hex",
            "language_boost": "English",
            "voice_setting": {
                "voice_id": voice_id,
                "speed": 1.0,
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data["base_resp"]["status_code"] != 0:
        raise RuntimeError(f"TTS failed: {data['base_resp']['status_msg']}")
    return bytes.fromhex(data["data"]["audio"])
```

### Text Length Consideration
- Sync endpoint: max 10,000 characters per request
- Async endpoint: max 1,000,000 characters (needs polling)
- For article narration, typical articles are 2,000-5,000 chars -- sync is fine

### Special Text Features
- Insert pauses: `<#2.5#>` inserts a 2.5-second pause (range: 0.01 to 99.99)
- Interjections: `(sighs)`, `(laughs)`, `(coughs)` are rendered as sound effects
- Pronunciation override: `pronunciation_dict.tone` array with `"word/pronunciation"` entries

---

## Sources

- [MiniMax T2A API Introduction](https://platform.minimax.io/docs/api-reference/speech-t2a-intro)
- [MiniMax T2A HTTP API Reference](https://platform.minimax.io/docs/api-reference/speech-t2a-http)
- [MiniMax System Voice ID List](https://platform.minimax.io/docs/faq/system-voice-id)
- [MiniMax API Overview](https://platform.minimax.io/docs/api-reference/api-overview)
- [MiniMax Get Voice API](https://platform.minimax.io/docs/api-reference/voice-management-get)
- [MiniMax Token Plan Quick Start](https://platform.minimax.io/docs/token-plan/quickstart)
- [MiniMax Async Long TTS Guide](https://platform.minimax.io/docs/guides/speech-t2a-async)
- [MiniMax TTS Pricing](https://platform.minimax.io/docs/guides/pricing)
- [Pipecat MiniMax Integration](https://docs.pipecat.ai/server/services/tts/minimax)
- [Handling Minimax TTS API (Blog)](https://blog.williamchong.cloud/code/2025/06/21/handling-minimax-tts-api-basic-and-streaming.html)
- [MiniMax Audio Documentation](https://minimaxaudio.org/api-docs)
