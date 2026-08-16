import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
AZURE_OPENAI_API_KEY = os.environ.get("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_URL = os.environ.get("AZURE_OPENAI_API_URL")
AZURE_OPENAI_DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
OPENAI_TIMEOUT_SECONDS = int(os.environ.get("OPENAI_TIMEOUT_SECONDS", "180"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "/opt/homebrew/bin/ffmpeg")
WHISPER_CLI_PATH = os.environ.get("WHISPER_CLI_PATH", "/opt/homebrew/bin/whisper-cli")
WHISPER_MODEL_PATH = os.environ.get(
    "WHISPER_MODEL_PATH",
    "/Users/debi.pradhan/Library/Application Support/LocalWorkCompanion/models/ggml-small.en.bin",
)
search_cache = {}


def masked(value):
    if not value:
        return "MISSING"
    return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "***"


def truncate_text(value: str, max_chars: int):
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + "..."


class VideoPayload(BaseModel):
    title: str
    script: str


class YouTubeUrlPayload(BaseModel):
    url: str


def extract_youtube_video_id(url: str):
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"youtu.be", "www.youtu.be"} and path_parts:
        return path_parts[0]

    if "youtube.com" in host:
        if path_parts and path_parts[0] == "shorts" and len(path_parts) > 1:
            return path_parts[1]
        query = parse_qs(parsed.query)
        if query.get("v"):
            return query["v"][0]

    raise ValueError("Could not find a YouTube video ID in the URL")


def fetch_youtube_video_metadata(video_id: str):
    url = "https://www.googleapis.com/youtube/v3/videos"
    params = {
        "part": "snippet,statistics",
        "id": video_id,
        "key": YOUTUBE_API_KEY,
    }
    safe_params = {**params, "key": masked(YOUTUBE_API_KEY)}
    print(f"[YouTube Video API] GET {url}")
    print(f"[YouTube Video API] params={json.dumps(safe_params)}")
    res = requests.get(url, params=params, timeout=10)
    print(f"[YouTube Video API] status={res.status_code}")
    print(f"[YouTube Video API] response_preview={res.text[:500]}")
    res.raise_for_status()
    data = res.json()
    items = data.get("items", [])
    if not items:
        raise ValueError("YouTube video not found")

    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    return {
        "video_id": video_id,
        "title": snippet.get("title", "YouTube Short"),
        "description": snippet.get("description", ""),
        "channel": snippet.get("channelTitle", ""),
        "published_at": snippet.get("publishedAt", ""),
        "tags": snippet.get("tags", []),
        "statistics": statistics,
    }


def fetch_trending_keywords(title: str):
    current_time = time.time()
    search_query = " ".join(title.split()) if title.split() else "shorts"

    if search_query in search_cache:
        cached_data, timestamp = search_cache[search_query]
        if current_time - timestamp < 1800:
            return cached_data

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "videoDuration": "short",
        "maxResults": 10,
        "key": YOUTUBE_API_KEY,
    }

    try:
        safe_params = {**params, "key": masked(YOUTUBE_API_KEY)}
        print(f"[Google API] GET {url}")
        print(f"[Google API] params={json.dumps(safe_params)}")
        res = requests.get(url, params=params, timeout=10)
        print(f"[Google API] status={res.status_code}")
        print(f"[Google API] response_preview={res.text[:500]}")
        res.raise_for_status()
        data = res.json()
        titles = [item["snippet"]["title"] for item in data.get("items", [])]
        search_cache[search_query] = (titles, current_time)
        return titles
    except Exception:
        return ["Trending Short Example", "Viral Short Sample"]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/predict")
def predict_shorts_virality(payload: VideoPayload):
    trending_context = fetch_trending_keywords(payload.title)

    prompt = f"""
    You are a YouTube Shorts content optimization assistant.
    Give safety-neutral, family-friendly advice for improving a draft video.
    Do not sexualize, stereotype, or exploit minors. If the title mentions a child,
    treat it as educational/family-safe content and suggest privacy-safe improvements.

    Evaluate this upcoming Short:
    Proposed Title: {payload.title}
    Script Text: {truncate_text(payload.script, 1200)}
    Current Trends In This Category: {trending_context[:5]}

    Return strict raw JSON formatting matching this exact structure.
    Keep suggestions concise, practical, and easy to scan.
    Each suggestion should be one action item, max 24 words.
    Group advice in this order: niche, title, hook, sound, pacing, captions, hashtags, description, cover, CTA, posting, testing.
    {{
      "score": 75,
      "suggestions": [
        "Pick one clear niche so the algorithm understands the audience.",
        "Rewrite the title with one keyword and one curiosity hook."
      ]
    }}
    """

    try:
        openai_payload = {
            "model": AZURE_OPENAI_DEPLOYMENT_NAME,
            "input": prompt,
            "stream": False,
        }
        print(f"[OpenAI API] POST {AZURE_OPENAI_API_URL}")
        print(f"[OpenAI API] api_key={masked(AZURE_OPENAI_API_KEY)}")
        print(f"[OpenAI API] payload={json.dumps(openai_payload)}")
        response = requests.post(
            AZURE_OPENAI_API_URL,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache",
                "api-key": AZURE_OPENAI_API_KEY,
            },
            json=openai_payload,
            timeout=OPENAI_TIMEOUT_SECONDS,
        )
        print(f"[OpenAI API] status={response.status_code}")
        print(f"[OpenAI API] response_preview={response.text[:1000]}")
        response.raise_for_status()
        data = response.json()
        if data.get("status") != "completed":
            return incomplete_ai_response(data)
        content = extract_response_text(data)
        if not content.strip():
            return incomplete_ai_response(data)
        return json.loads(content)
    except Exception as e:
        error_message = str(e)
        print(f"Azure OpenAI error: {type(e).__name__}: {error_message}")
        return {
            "score": 50,
            "suggestions": [
                "Error processing Azure AI response. Using fallback parameters.",
                f"Debug: {type(e).__name__}: {error_message}",
            ],
        }


@app.post("/analyze-youtube-url")
def analyze_youtube_url(payload: YouTubeUrlPayload):
    metadata = fetch_youtube_video_metadata(extract_youtube_video_id(payload.url))
    script_context = "\n".join(
        [
            f"YouTube URL analysis. Spoken transcript was not fetched.",
            f"Description: {truncate_text(metadata['description'], 800)}",
            f"Channel: {metadata['channel']}",
            f"Published At: {metadata['published_at']}",
            f"Tags: {', '.join(metadata['tags'][:12])}",
            f"Statistics: {json.dumps(metadata['statistics'])}",
        ]
    )
    return predict_shorts_virality(
        VideoPayload(title=metadata["title"], script=script_context)
    )


def incomplete_ai_response(data):
    reason = data.get("incomplete_details", {}).get("reason") or data.get("status")
    blocked = response_has_blocked_completion(data)
    suggestion = "AI response was incomplete before it returned JSON."
    if blocked:
        suggestion = (
            "AI safety filter blocked the completion. Try a neutral title such as "
            "'Kid learns tic tac toe with AI' and avoid sensitive wording."
        )
    return {
        "score": 50,
        "suggestions": [
            suggestion,
            f"Debug: response status={data.get('status')} reason={reason}",
        ],
    }


def response_has_blocked_completion(data):
    for item in data.get("content_filters", []):
        if item.get("source_type") == "completion" and item.get("blocked"):
            return True
    return False


@app.post("/analyze-video")
async def analyze_video(request: Request, title: str = ""):
    video_bytes = await request.body()
    clean_title = title.strip() or "Local Short"

    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / "upload.mp4"
        video_path.write_bytes(video_bytes)
        transcript = transcribe_video_file(video_path)

    print(f"[Whisper] transcript={transcript}")
    return predict_shorts_virality(
        VideoPayload(
            title=clean_title,
            script=transcript or "No speech detected in this video file.",
        )
    )


def transcribe_video_file(video_path: Path):
    with tempfile.TemporaryDirectory() as temp_dir:
        audio_path = Path(temp_dir) / "audio.wav"
        subprocess.run(
            [
                FFMPEG_PATH,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(audio_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        whisper_result = subprocess.run(
            [
                WHISPER_CLI_PATH,
                "-m",
                WHISPER_MODEL_PATH,
                "-f",
                str(audio_path),
                "-nt",
                "-l",
                "en",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

    return clean_whisper_output(whisper_result.stdout)


def clean_whisper_output(output):
    lines = []
    for line in output.splitlines():
        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def extract_response_text(data):
    if "output_text" in data:
        return data["output_text"]

    result = ""
    for item in data.get("output", []):
        for content in item.get("content", []):
            if isinstance(content, dict) and "text" in content:
                result += content["text"]

    if result:
        return result

    raise ValueError("AI response did not contain output text")
