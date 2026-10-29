import io
import os
import re
import zipfile

import streamlit as st
from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs
from pydub import AudioSegment
from pypdf import PdfReader


st.set_page_config(
    page_title="YouTube Voiceover Studio",
    page_icon="🎙️",
    layout="centered",
)

CHANNELS = {
    "Football Explained": {
        "voice_id": "2mltbVQP21Fq8XgIfRQJ",
        "model_id": "eleven_multilingual_v2",
        "stability": 0.50,
        "similarity": 0.50,
        "style": 0.00,
        "speed": 1.00,
        "speaker_boost": True,
    },
    "Harry Potter": {
        "voice_id": "2mltbVQP21Fq8XgIfRQJ",
        "model_id": "eleven_multilingual_v2",
        "stability": 0.50,
        "similarity": 0.50,
        "style": 0.00,
        "speed": 1.00,
        "speaker_boost": True,
    },
    "Extreme Earth": {
        "voice_id": "2mltbVQP21Fq8XgIfRQJ",
        "model_id": "eleven_multilingual_v2",
        "stability": 0.50,
        "similarity": 0.50,
        "style": 0.00,
        "speed": 1.00,
        "speaker_boost": True,
    },
    "The Chelsea Brief": {
        "voice_id": "3WqHLnw80rOZqJzW9YRB",
        "model_id": "eleven_multilingual_v2",
        "stability": 0.50,
        "similarity": 0.50,
        "style": 0.00,
        "speed": 1.00,
        "speaker_boost": True,
    },
}

TARGET_CHARACTERS = 650
MAX_CHARACTERS = 700
MIN_CHARACTERS = 500


def get_secret(name, default=""):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return os.getenv(name, default)


def password_gate():
    expected = get_secret("APP_PASSWORD", "")
    if not expected:
        return

    if st.session_state.get("authenticated"):
        return

    st.title("🎙️ YouTube Voiceover Studio")
    st.caption("Private voiceover generator")
    password = st.text_input("Password", type="password")

    if st.button("Open studio", type="primary", use_container_width=True):
        if password == expected:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    st.stop()


def safe_filename(value):
    value = re.sub(r'[<>:"/\\|?*]', "", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value or "Voiceover"


def read_upload(file):
    ext = file.name.lower().rsplit(".", 1)[-1]
    raw = file.getvalue()

    if ext == "txt":
        for encoding in ("utf-8", "utf-8-sig", "cp1252"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                pass
        return raw.decode("utf-8", errors="replace")

    if ext == "pdf":
        reader = PdfReader(io.BytesIO(raw))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        return "\n".join(pages)

    raise ValueError("Please upload a TXT or PDF script.")


def split_long_piece(text, max_chars):
    words = text.split()
    chunks = []
    current = ""

    for word in words:
        proposed = f"{current} {word}".strip()
        if len(proposed) <= max_chars:
            current = proposed
        else:
            if current:
                chunks.append(current)
            current = word

    if current:
        chunks.append(current)

    return chunks


def split_script(text):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    sentences = re.split(r'(?<=[.!?])\s+', text)
    expanded = []

    for sentence in sentences:
        if len(sentence) > MAX_CHARACTERS:
            expanded.extend(split_long_piece(sentence, MAX_CHARACTERS))
        else:
            expanded.append(sentence)

    chunks = []
    current = ""

    for sentence in expanded:
        proposed = f"{current} {sentence}".strip() if current else sentence

        if len(proposed) <= TARGET_CHARACTERS:
            current = proposed
            continue

        if len(proposed) <= MAX_CHARACTERS and len(current) < MIN_CHARACTERS:
            current = proposed
            continue

        if current:
            chunks.append(current.strip())
        current = sentence

    if current:
        chunks.append(current.strip())

    if len(chunks) >= 2 and len(chunks[-1]) < MIN_CHARACTERS:
        combined = f"{chunks[-2]} {chunks[-1]}".strip()
        if len(combined) <= MAX_CHARACTERS:
            chunks[-2] = combined
            chunks.pop()

    safe = []
    for chunk in chunks:
        if len(chunk) <= MAX_CHARACTERS:
            safe.append(chunk)
        else:
            safe.extend(split_long_piece(chunk, MAX_CHARACTERS))

    return safe


def generate_clip(client, text, preset):
    audio = client.text_to_speech.convert(
        voice_id=preset["voice_id"],
        text=text,
        model_id=preset["model_id"],
        output_format="mp3_44100_128",
        voice_settings=VoiceSettings(
            stability=preset["stability"],
            similarity_boost=preset["similarity"],
            style=preset["style"],
            use_speaker_boost=preset["speaker_boost"],
            speed=preset["speed"],
        ),
    )
    return b"".join(part for part in audio if part)


def combine_mp3s(clips):
    combined = AudioSegment.empty()

    for clip in clips:
        combined += AudioSegment.from_file(io.BytesIO(clip), format="mp3")

    out = io.BytesIO()
    combined.export(out, format="mp3", bitrate="192k")
    return out.getvalue()


def make_clips_zip(clips, chunks):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for idx, (clip, text) in enumerate(zip(clips, chunks), start=1):
            archive.writestr(f"{idx:02d}.mp3", clip)
            archive.writestr(f"{idx:02d}.txt", text)
    return out.getvalue()


password_gate()

st.title("🎙️ YouTube Voiceover Studio")
st.caption("Paste a script → generate with ElevenLabs → download one finished MP3")

api_key = get_secret("ELEVENLABS_API_KEY", "")

if not api_key:
    st.warning("ELEVENLABS_API_KEY has not been added to the website secrets.")

channel = st.selectbox("Channel", list(CHANNELS))
preset = CHANNELS[channel]

title = st.text_input(
    "Video title",
    placeholder="e.g. Every Football Tactical Term Explained"
)

tab1, tab2 = st.tabs(["Paste script", "Upload TXT / PDF"])

with tab1:
    pasted = st.text_area(
        "Script",
        height=350,
        placeholder="Paste the complete narration script here..."
    )

with tab2:
    uploaded = st.file_uploader("Upload script", type=["txt", "pdf"])

script = pasted

if uploaded is not None:
    try:
        script = read_upload(uploaded)
        st.success(f"Loaded: {uploaded.name}")
    except Exception as exc:
        st.error(str(exc))
        script = ""

chunks = split_script(script) if script.strip() else []

if chunks:
    st.info(
        f"**{len(script.split()):,} words** · "
        f"**{len(script):,} characters** · "
        f"**{len(chunks)} ElevenLabs generations**"
    )

    with st.expander("Check chunk sizes"):
        for idx, chunk in enumerate(chunks, start=1):
            st.write(f"Part {idx:02d}: {len(chunk)} characters")

with st.expander("Current voice preset"):
    st.code(
        f"""Channel: {channel}
Voice ID: {preset['voice_id']}
Model: {preset['model_id']}
Stability: {preset['stability']}
Similarity: {preset['similarity']}
Speed: {preset['speed']}
Speaker boost: {preset['speaker_boost']}
Target characters: {TARGET_CHARACTERS}
Maximum characters: {MAX_CHARACTERS}"""
    )

if st.button("Generate full voiceover", type="primary", use_container_width=True):
    if not api_key:
        st.error("The ElevenLabs API key is missing from the website secrets.")
        st.stop()

    if not title.strip():
        st.error("Enter a video title.")
        st.stop()

    if not script.strip():
        st.error("Paste or upload a script.")
        st.stop()

    if not chunks:
        st.error("No voiceover chunks could be created.")
        st.stop()

    client = ElevenLabs(api_key=api_key)

    progress = st.progress(0)
    status = st.empty()
    clips = []

    try:
        for idx, chunk in enumerate(chunks, start=1):
            status.write(
                f"Generating part {idx}/{len(chunks)} "
                f"({len(chunk)} characters)…"
            )
            clips.append(generate_clip(client, chunk, preset))
            progress.progress(idx / len(chunks))

        status.write("Combining the generated clips locally on the server…")
        full_audio = combine_mp3s(clips)

    except Exception as exc:
        st.error(f"Voiceover generation failed: {exc}")
        st.stop()

    progress.progress(1.0)
    status.empty()

    filename = f"{safe_filename(title)} - FULL.mp3"

    st.success("Voiceover complete.")
    st.audio(full_audio, format="audio/mp3")

    st.download_button(
        "⬇️ Download full voiceover",
        data=full_audio,
        file_name=filename,
        mime="audio/mpeg",
        type="primary",
        use_container_width=True,
    )

    with st.expander("Individual clips"):
        st.download_button(
            "Download all clips + chunk text",
            data=make_clips_zip(clips, chunks),
            file_name=f"{safe_filename(title)} - Clips.zip",
            mime="application/zip",
            use_container_width=True,
        )

        for idx, clip in enumerate(clips, start=1):
            st.write(f"Part {idx:02d}")
            st.audio(clip, format="audio/mp3")
