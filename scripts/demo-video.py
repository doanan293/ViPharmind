"""Turn the recorded walkthrough into the final demo video.

The walkthrough (`npm --prefix frontend run demo:video`) writes `video.webm` and `waits.json`
(milliseconds since the recording started while the app was answering). This script keeps
everything else at normal speed, plays the waits SPEEDUP times faster, and writes an H.264 MP4.

    uv run python scripts/demo-video.py frontend/demo-videos/walkthrough.demo.ts-walkthrough out.mp4
"""

import argparse
import json
import subprocess
from pathlib import Path

SPEEDUP = 20.0
# Seconds kept at normal speed at each end of a wait, so the cut is visible.
MARGIN = 0.8


def segments(
    waits: list[tuple[float, float]], duration: float
) -> list[tuple[float, float, float]]:
    """(start, end, speed) pieces covering [0, duration]; waits shorter than two margins stay."""
    pieces: list[tuple[float, float, float]] = []
    cursor = 0.0
    for start, end in sorted(waits):
        fast_start, fast_end = start + MARGIN, end - MARGIN
        if fast_end - fast_start <= 0 or fast_start < cursor or fast_end > duration:
            continue
        pieces.append((cursor, fast_start, 1.0))
        pieces.append((fast_start, fast_end, SPEEDUP))
        cursor = fast_end
    pieces.append((cursor, duration, 1.0))
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
