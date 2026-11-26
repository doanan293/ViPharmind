"""Turn the recorded walkthrough into the final demo video.

The walkthrough (`npm --prefix frontend run demo:video`) writes `video.webm` and `waits.json`
(milliseconds since the recording started while the app was answering). This script keeps
plays ordinary steps BASE_SPEED times faster, the waits WAIT_SPEED times faster, and the
REVEAL_S seconds after each answer arrives at normal speed; writes an H.264 MP4.

    uv run python scripts/demo-video.py frontend/demo-videos/walkthrough.demo.ts-walkthrough out.mp4
"""

import argparse
import json
import subprocess
from pathlib import Path

# Owner (2026-11-26): about two minutes; ordinary steps brisk, waits for the model skipped,
# the moment an answer appears at normal speed so viewers can read it.
BASE_SPEED = 1.4
WAIT_SPEED = 30.0
# Seconds before a wait kept at base speed (the question being sent) and after it at normal
# speed (the answer and its citations appearing).
MARGIN = 0.8
REVEAL_S = 5.0


def segments(
    waits: list[tuple[float, float]], duration: float
) -> list[tuple[float, float, float]]:
    """(start, end, speed) pieces covering [0, duration]."""
    pieces: list[tuple[float, float, float]] = []
    cursor = 0.0
    for start, end in sorted(waits):
        if end <= cursor or end > duration:
            continue
        fast_start = max(cursor, start + MARGIN)
        if fast_start < end:
            pieces.append((cursor, fast_start, BASE_SPEED))
            pieces.append((fast_start, end, WAIT_SPEED))
        else:
            pieces.append((cursor, end, BASE_SPEED))
        reveal_end = min(duration, end + REVEAL_S)
        pieces.append((end, reveal_end, 1.0))
        cursor = reveal_end
    pieces.append((cursor, duration, BASE_SPEED))
    return [piece for piece in pieces if piece[1] - piece[0] > 0.05]


def filter_graph(pieces: list[tuple[float, float, float]]) -> str:
    parts = [
        f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=(PTS-STARTPTS)/{speed}[v{i}]"
        for i, (start, end, speed) in enumerate(pieces)
    ]
    inputs = "".join(f"[v{i}]" for i in range(len(pieces)))
    parts.append(f"{inputs}concat=n={len(pieces)}:v=1:a=0[out]")
    return ";".join(parts)


def duration_of(video: Path) -> float:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(video),
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return float(out.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "recording", type=Path, help="folder with video.webm and waits.json"
    )
    parser.add_argument("output", type=Path, help="the MP4 to write")
    args = parser.parse_args()
    video = args.recording / "video.webm"
    waits_ms = json.loads((args.recording / "waits.json").read_text())["waits"]
    waits = [(start / 1000, end / 1000) for start, end in waits_ms]
    pieces = segments(waits, duration_of(video))
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(video),
            "-filter_complex",
            filter_graph(pieces),
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(args.output),
        ],
        check=True,
    )
    print(
        f"wrote {args.output} ({duration_of(args.output):.0f} s from {duration_of(video):.0f} s)"
    )


if __name__ == "__main__":
    main()
