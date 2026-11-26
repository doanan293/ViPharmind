import importlib.util
from itertools import pairwise
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "demo_video", Path(__file__).with_name("demo-video.py")
)
assert spec is not None and spec.loader is not None
demo_video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo_video)


def test_waits_are_sped_up_inside_their_margins() -> None:
    pieces = demo_video.segments([(10.0, 30.0)], 60.0)
    assert pieces == [(0.0, 10.8, 1.0), (10.8, 29.2, 20.0), (29.2, 60.0, 1.0)]


def test_short_waits_stay_at_normal_speed() -> None:
    assert demo_video.segments([(10.0, 11.2)], 20.0) == [(0.0, 20.0, 1.0)]


def test_pieces_cover_the_video_without_gaps() -> None:
    pieces = demo_video.segments([(40.0, 70.0), (5.0, 20.0)], 100.0)
    assert pieces[0][0] == 0.0 and pieces[-1][1] == 100.0
    assert all(a[1] == b[0] for a, b in pairwise(pieces))
