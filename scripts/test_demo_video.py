import importlib.util
from itertools import pairwise
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "demo_video", Path(__file__).with_name("demo-video.py")
)
assert spec is not None and spec.loader is not None
demo_video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_video)


def test_wait_fast_answer_reveal_at_normal_speed_rest_brisk() -> None:
    pieces = demo_video.segments([(10.0, 30.0)], 60.0)
    assert pieces == [
        (0.0, 10.8, demo_video.BASE_SPEED),
        (10.8, 30.0, demo_video.WAIT_SPEED),
        (30.0, 30.0 + demo_video.REVEAL_S, 1.0),
        (30.0 + demo_video.REVEAL_S, 60.0, demo_video.BASE_SPEED),
    ]


def test_short_waits_still_get_the_reveal() -> None:
    pieces = demo_video.segments([(10.0, 10.5)], 20.0)
    assert (10.5, 10.5 + demo_video.REVEAL_S, 1.0) in pieces


def test_output_length_is_about_two_minutes() -> None:
    waits = [
        (26.6, 70.3),
        (76.7, 144.0),
        (145.6, 154.0),
        (200.0, 225.1),
        (260.0, 278.0),
        (290.0, 355.7),
    ]
    pieces = demo_video.segments(waits, 361.0)
    out = sum((e - s) / v for s, e, v in pieces)
    assert 100 <= out <= 130


def test_pieces_cover_the_video_without_gaps() -> None:
    pieces = demo_video.segments([(40.0, 70.0), (5.0, 20.0)], 100.0)
    assert pieces[0][0] == 0.0 and pieces[-1][1] == 100.0
    assert all(a[1] == b[0] for a, b in pairwise(pieces))
