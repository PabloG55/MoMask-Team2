"""Show mode tests (director, camera, stage, voices, sets). No MoMask needed."""

import json
import os

import numpy as np
import pytest

from story import beats, director, show
from story.director import (
    CHARACTERS,
    LIGHTS,
    SETS,
    SHOTS,
    StoryError,
    clean_show,
    plan_show,
)
from story.motion import FPS

CLIENT = os.path.join("client", "story")


def test_names_are_matched_loosely_and_the_cast_is_capped():
    plan = {
        "cast": ["dino kid", "TEDDY", "polybot", "Hugo", "nobody"],
        "steps": [{"actor": "Hugo", "action": "a person waves", "lines": []}],
    }
    show_ = clean_show(plan)
    assert show_["cast"] == [
        "DinoKid",
        "Teddy",
        "Polybot",
    ]
    # Hugo is not in the cast, so the first one acts.
    assert show_["steps"][0]["actor"] == "DinoKid"
    assert show_["dropped_actors"] == 1


def test_lines_are_checked():
    plan = {
        "cast": ["Teddy"],
        "steps": [
            {
                "actor": "Teddy",
                "action": "jumps",
                "lines": [
                    {"who": "Narrator", "text": "  Can   you jump? ", "when": "before"},
                    {
                        "who": "Kyle",
                        "text": "I am not in this show",
                        "when": "after",
                    },
                    {"who": "Teddy", "text": " ".join(["la"] * 40), "when": "sometime"},
                    {
                        "who": "Teddy",
                        "text": "   ",
                        "when": "after",
                    },
                    "a plain string is a narrator line",
                ],
            }
        ],
    }
    lines = clean_show(plan)["steps"][0]["lines"]
    assert lines[0] == {"who": "narrator", "text": "Can you jump?", "when": "before"}
    assert lines[1]["who"] == "narrator"
    assert (
        len(lines[2]["text"].split()) == director.MAX_CHARACTER_WORDS
        and lines[2]["when"] == "before"
    )
    assert len(lines) == 3  # four kept at most, and the empty one is gone


def test_defaults_for_what_the_plan_leaves_out():
    show_ = clean_show(
        {
            "steps": [
                {
                    "actor": "Astronaut",
                    "action": "a person bows",
                    "seconds": "abc",
                    "shot": "dolly zoom",
                }
            ]
        }
    )
    assert show_["set"] == "space" and show_["light"] == "night"
    step = show_["steps"][0]
    assert step["seconds"] == director.DEFAULT_SECONDS and step["shot"] == "medium"
    assert (
        clean_show({"steps": [{"action": "waves", "seconds": 99}]})["steps"][0][
            "seconds"
        ]
        == director.MAX_SECONDS
    )
    assert (
        clean_show({"steps": [{"action": "waves", "narration": "Hola, ¿cómo estás?"}]})[
            "language"
        ]
        == "es"
    )


def test_bad_shows_are_refused():
    for bad in ({}, {"steps": []}, "text", {"steps": ["not an object"]}):
        with pytest.raises(StoryError):
            clean_show(bad)


def test_json_skips_the_llm_and_free_text_needs_a_key(monkeypatch):
    examples = json.load(open(os.path.join(CLIENT, "examples.json")))
    for example in examples:
        planned, info = plan_show(json.dumps(example["show"]))
        assert info["planner"] == "json"
        assert (
            planned["cast"] == example["show"]["cast"]
            and planned["set"] == example["show"]["set"]
        )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StoryError, match="OPENAI_API_KEY"):
        plan_show("Dino jumps and Teddy claps.")


def test_the_llm_answer_goes_through_the_same_cleaning():
    class Response:
        output_text = json.dumps(
            {
                "title": "T",
                "language": "en",
                "set": "beach",
                "light": "sunset",
                "cast": ["Jimmy"],
                "steps": [
                    {
                        "actor": "Jimmy",
                        "action": "Jimmy dances",
                        "seconds": 3,
                        "shot": "orbit",
                        "lines": [],
                    }
                ],
            }
        )
        usage = None

    class Client:
        class responses:
            calls = []

            @staticmethod
            def create(**kwargs):
                Client.responses.calls.append(kwargs)
                return Response()

    planned, info = plan_show("Jimmy dances on the beach", Client)
    assert planned["set"] == "beach" and planned["steps"][0]["action"].startswith(
        "a person"
    )
    sent = Client.responses.calls[0]
    assert (
        sent["text"]["format"]["strict"] is True
        and sent["text"]["format"]["schema"] is director.SCHEMA
    )
    assert info["planner"] == director.MODEL


def test_slots_are_centred_and_do_not_overlap():
    for cast in (["Teddy"], ["DinoKid", "Teddy"], ["Froggy", "LilBro", "Hugo"]):
        xs = show.slots(cast)
        assert abs(xs[0] + xs[-1]) < 1e-6
        for (a, xa), (b, xb) in zip(zip(cast, xs), zip(cast[1:], xs[1:])):
            assert xb - xa >= (show.WIDTH[a] + show.WIDTH[b]) / 2


STEPS = [
    {
        "actor": "DinoKid",
        "action": "a person waves",
        "seconds": 3.0,
        "shot": "medium",
        "lines": [
            {"who": "narrator", "text": "Hello!", "when": "before"},
            {"who": "DinoKid", "text": "Hi!", "when": "during"},
        ],
    },
    {
        "actor": "Teddy",
        "action": "a person jumps",
        "seconds": 2.6,
        "shot": "low",
        "lines": [
            {"who": "Teddy", "text": "Watch me!", "when": "before"},
            {"who": "narrator", "text": "Wow!", "when": "after"},
        ],
    },
]
SECONDS_OF = {(0, 0): 1.0, (0, 1): 0.6, (1, 0): 1.0, (1, 1): 0.8}


def shots_for(steps=STEPS, cast=("DinoKid", "Teddy")):
    rows = beats.segments(steps)
    frames, starts = beats.schedule(steps, rows, SECONDS_OF)
    return (
        show.plan_shots({"steps": steps, "cast": list(cast)}, rows, frames, starts),
        rows,
        frames,
        starts,
    )


def test_actions_get_the_directors_shot_and_speakers_get_a_close_up():
    shots, rows, frames, starts = shots_for()
    bounds = np.concatenate([[0], np.cumsum(frames)]) / FPS
    at = lambda t: next(s for s in shots if s["start"] <= t < s["end"])  # noqa: E731
    assert shots[0]["type"] == "wide" and shots[0]["start"] == 0
    assert shots[-1]["end"] == pytest.approx(bounds[-1], abs=0.01)
    for a, b in zip(shots, shots[1:]):
        assert a["end"] == b["start"]  # no gaps
        assert b["start"] - a["start"] >= show.MIN_SHOT - 1e-6 or a["start"] == 0
    jump = rows.index(next(r for r in rows if r["kind"] == "action" and r["step"] == 1))
    assert at(bounds[jump] + 0.1) == {
        "start": round(bounds[jump], 2),
        "end": at(bounds[jump] + 0.1)["end"],
        "type": "low",
        "target": "Teddy",
    }
    assert (
        at(starts[(1, 0)] + 0.1)["type"] == "close"
        and at(starts[(1, 0)] + 0.1)["target"] == "Teddy"
    )
    # The narrator praising the jump shows the one who jumped.
    assert at(starts[(1, 1)] + 0.1) == {
        **at(starts[(1, 1)] + 0.1),
        "type": "medium",
        "target": "Teddy",
    }


def test_every_character_has_a_voice_a_width_a_skeleton_and_a_vrm():
    assert set(show.VOICES) == {"narrator", *CHARACTERS}
    assert set(show.WIDTH) == set(CHARACTERS)
    for name in CHARACTERS:
        assert os.path.exists(os.path.join(CLIENT, "characters", f"{name}.vrm")), name
        skeleton = show.load_skeleton(name)
        assert skeleton.body and skeleton.bone("Hips") is not None, name
    for en, _, es, _, effect in show.VOICES.values():
        assert (
            en[0] in show.LANG_CODE
            and es[0] in show.LANG_CODE
            and effect in (None, *show.EFFECTS)
        )


def test_mouth_follows_loudness():
    sr = show.SR
    t = np.arange(sr) / sr
    track = np.zeros(2 * sr, np.float32)
    track[sr:] = 0.3 * np.sin(2 * np.pi * 220 * t)  # silent for a second, then a tone
    m = show.mouth(track)
    assert m["fps"] == show.MOUTH_FPS and len(m["aa"]) == 2 * show.MOUTH_FPS
    shut = max(m[k][i] for k in ("aa", "ee", "oh") for i in range(show.MOUTH_FPS - 1))
    opened = max(m[k][show.MOUTH_FPS + 5] for k in ("aa", "ee", "oh"))
    assert shut == 0 and opened > 30
    assert show.mouth(np.zeros(10, np.float32))["aa"] == []


def test_sets_match_the_director_and_keep_the_action_area_clear():
    index = json.load(open(os.path.join(CLIENT, "sets", "index.json")))
    assert [s["id"] for s in index] == list(SETS)
    for entry in index:
        folder = os.path.join(CLIENT, "sets", entry["id"])
        data = json.load(open(os.path.join(folder, "set.json")))
        assert data["light"] in LIGHTS
        for prop in data["props"]:
            assert os.path.exists(os.path.join(folder, prop["model"])), prop["model"]
            x, _, z = prop["position"]
            flat = "rug" in prop["model"]
            assert flat or abs(x) >= 3.2 or z <= -1.5, (entry["id"], prop)


def test_example_shows_have_saved_outputs():
    examples = json.load(open(os.path.join(CLIENT, "examples.json")))
    for example in examples:
        folder = os.path.join(CLIENT, "demo", example["slug"])
        timeline = json.load(open(os.path.join(folder, "timeline.json")))
        assert timeline["version"] == 2 and timeline["shots"] and timeline["lines"]
        assert set(SHOTS) >= {s["type"] for s in timeline["shots"]}
        for member in timeline["cast"]:
            assert os.path.exists(os.path.join(folder, member["motion"]))
        assert os.path.exists(os.path.join(folder, "voices.mp3"))
