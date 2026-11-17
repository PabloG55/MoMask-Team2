"""Story -> a show: who is in it, where, with what light, and what each one does and
says.

GPT-6 Luna directs; a show written as JSON skips it. Either way it is checked here
first.
"""

import json
import os
import re
import time

from story.orchestrator import (
    StoryError,
    clean_action,
    guess_language,
    parse_json_story,
)

MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
MAX_CAST = 3
MAX_STEPS = 6
MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 2.4, 6.0, 3.0
MAX_LINES_PER_STEP = 4
MAX_CHARACTER_WORDS = 12
MAX_NARRATOR_WORDS = 22
LANGUAGES = ("en", "es")

# The ten 100Avatars characters (Polygonal Mind, CC0), as the director sees them.
CHARACTERS = {
    "Astronaut": "a small astronaut kid in an orange space suit and a big round helmet",
    "CoolAlien": "a tall, thin grey-green alien with big black eyes",
    "DinoKid": "a little kid in a green dinosaur costume",
    "Froggy": "a tall green frog with long legs",
    "Hugo": "a big, friendly purple monster",
    "Jimmy": "a cheerful guy in swim shorts, ready for the beach",
    "Kyle": "a tall young man in a t-shirt and jeans",
    "LilBro": "a tiny green bottle with stick arms and legs",
    "Polybot": "a small boxy green robot",
    "Teddy": "a big brown teddy bear",
}

# Kept in step with client/story/sets/index.json (a test checks it).
SETS = {
    "stage": "An empty white stage, like Pocoyo: nothing but the characters.",
    "park": "A sunny park with trees, bushes and flowers.",
    "room": "A cosy kid's room with a sofa, a rug, shelves and toys.",
    "beach": "A sandy beach with palm trees, a treasure chest and a pirate ship at sea.",
    "space": "The surface of the moon, with rocks, a rocket and stars.",
}
LIGHTS = {
    "studio": "soft, even, shadowless white (the Pocoyo look)",
    "day": "bright midday sun",
    "sunset": "warm orange evening light",
    "night": "dark blue night with a moon light",
}
SHOTS = {
    "wide": "everyone in frame",
    "medium": "the actor, whole body",
    "close": "the actor's face and shoulders, for small gestures and feelings",
    "low": "from low down looking up, makes a jump or a kick look big",
    "high": "from above looking down, makes the actor look small",
    "orbit": "circles slowly around the actor, for dancing or spinning",
    "follow": "keeps the actor in the middle while it walks or runs",
}
WHEN = ("before", "during", "after")


def _bullets(table):
    return "\n".join(f"- {k}: {v}" for k, v in table.items())


INSTRUCTIONS = f"""\
You are the director of a short children's show in the style of Pocoyo. A friendly narrator
talks to the characters and to the audience; the characters answer with short, playful lines;
they take turns doing one movement at a time. A text-to-motion model (MoMask, trained on
HumanML3D) animates every movement, so movements must be things a body can do alone.

Pick 1 to {MAX_CAST} characters (cast) that fit the story:
{_bullets(CHARACTERS)}

Pick one set:
{_bullets(SETS)}

Pick one light:
{_bullets(LIGHTS)}

Then write 2 to {MAX_STEPS} steps in story order. Each step is ONE character (actor, from the
cast) doing ONE movement:
- action: written like a HumanML3D caption, present tense, starting with "a person", in
  English whatever the story's language. Examples: "a person jumps forward with both feet",
  "a person waves with the right hand", "a person spins around in place", "a person kicks
  with the left leg", "a person dances happily", "a person bows", "a person claps",
  "a person walks forward slowly", "a person sits down on the ground". Only the body: no
  objects, no other people, no faces. Prefer movements that stay in place; the characters
  stand side by side.
- seconds: how long the movement takes, {MIN_SECONDS} to {MAX_SECONDS} (most take about 3).
- shot: the camera for the movement:
{_bullets(SHOTS)}
- lines: 1 to {MAX_LINES_PER_STEP} lines around the movement. who: "narrator" or a cast
  member. when: "before" (set it up: "Can you jump, Dino?" / "Watch me!"), "during" (a very
  short line said while moving: "Wheee!") or "after" (react: "Wow! What a big jump!").
  The narrator speaks to the characters by name and to the audience ("Can you clap too?").
  Characters say at most {MAX_CHARACTER_WORDS} words, the narrator at most {MAX_NARRATOR_WORDS}.
  Lines are in the story's language.

title: a short title in the story's language. language: "en" or "es".
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "language", "set", "light", "cast", "steps"],
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string", "enum": list(LANGUAGES)},
        "set": {"type": "string", "enum": list(SETS)},
        "light": {"type": "string", "enum": list(LIGHTS)},
        "cast": {
            "type": "array",
            "items": {"type": "string", "enum": list(CHARACTERS)},
        },
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["actor", "action", "seconds", "shot", "lines"],
                "properties": {
                    "actor": {"type": "string", "enum": list(CHARACTERS)},
                    "action": {"type": "string"},
                    "seconds": {"type": "number"},
                    "shot": {"type": "string", "enum": list(SHOTS)},
                    "lines": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["who", "text", "when"],
                            "properties": {
                                "who": {
                                    "type": "string",
                                    "enum": ["narrator", *CHARACTERS],
                                },
                                "text": {"type": "string"},
                                "when": {"type": "string", "enum": list(WHEN)},
                            },
                        },
                    },
                },
            },
        },
    },
}

# When a hand-written show names no set.
DEFAULT_SET = {"Astronaut": "space", "Jimmy": "beach"}


def _name(value, table):
    """Match a name in `table` ignoring case and spaces ("dino kid" -> "DinoKid"), or
    None."""
    key = re.sub(r"[\s_-]+", "", str(value or "")).lower()
    for name in table:
        if name.lower() == key:
            return name
    return None


def _text(value, limit):
    words = re.sub(r"\s+", " ", str(value or "")).strip().split()
    return " ".join(words[:limit])


def _seconds(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SECONDS
    if seconds != seconds:  # NaN
        return DEFAULT_SECONDS
    return min(MAX_SECONDS, max(MIN_SECONDS, seconds))


def clean_show(plan, story_text=""):
    """Check a show from the LLM or from JSON and fix what can be fixed."""
    if isinstance(plan, list):
        plan = {"steps": plan}
    if not isinstance(plan, dict):
        raise StoryError("A show should be a JSON object with steps.")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise StoryError("The show has no steps.")

    cast = []
    for value in plan.get("cast") or []:
        name = _name(value, CHARACTERS)
        if name and name not in cast and len(cast) < MAX_CAST:
            cast.append(name)

    cleaned, dropped_actors = [], 0
    for i, step in enumerate(steps[:MAX_STEPS]):
        if not isinstance(step, dict):
            raise StoryError(f"Step {i + 1} should be an object with an 'action'.")
        actor = _name(step.get("actor"), CHARACTERS)
        if actor and actor not in cast:
            if len(cast) < MAX_CAST:
                cast.append(actor)
            else:
                actor, dropped_actors = None, dropped_actors + 1
        if actor is None:
            if not cast:
                cast.append("DinoKid")
            actor = cast[0]

        lines = []
        for line in (step.get("lines") or [])[:MAX_LINES_PER_STEP]:
            if isinstance(line, str):
                line = {"who": "narrator", "text": line}
            if not isinstance(line, dict):
                continue
            who = (
                "narrator"
                if str(line.get("who", "")).lower() == "narrator"
                else _name(line.get("who"), CHARACTERS)
            )
            if who is None or (who != "narrator" and who not in cast):
                who = "narrator"
            text = _text(
                line.get("text"),
                MAX_NARRATOR_WORDS if who == "narrator" else MAX_CHARACTER_WORDS,
            )
            when = line.get("when") if line.get("when") in WHEN else "before"
            if text:
                lines.append({"who": who, "text": text, "when": when})
        # A narration field in the older story format becomes a "before" line.
        if not lines and step.get("narration"):
            lines.append(
                {
                    "who": "narrator",
                    "text": _text(step["narration"], MAX_NARRATOR_WORDS),
                    "when": "before",
                }
            )

        cleaned.append(
            {
                "actor": actor,
                "action": clean_action(step.get("action", "")),
                "seconds": _seconds(step.get("seconds", DEFAULT_SECONDS)),
                "shot": step.get("shot") if step.get("shot") in SHOTS else "medium",
                "lines": lines,
            }
        )

    set_name = _name(plan.get("set"), SETS) or next(
        (DEFAULT_SET[c] for c in cast if c in DEFAULT_SET), "stage"
    )
    light = _name(plan.get("light"), LIGHTS) or {
        "stage": "studio",
        "space": "night",
    }.get(set_name, "day")
    language = plan.get("language") if plan.get("language") in LANGUAGES else None
    if language is None:
        language = guess_language(
            " ".join(l["text"] for s in cleaned for l in s["lines"]) or story_text
        )
    return {
        "title": str(plan.get("title") or "").strip()[:80] or "Story",
        "language": language,
        "set": set_name,
        "light": light,
        "cast": cast,
        "steps": cleaned,
        "dropped_steps": max(0, len(steps) - MAX_STEPS),
        "dropped_actors": dropped_actors,
    }


def ask_director(story, client=None):
    """Free text -> show, with GPT-6 Luna. Returns (plan, info about the call)."""
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise StoryError(
                "The server has no OPENAI_API_KEY, so it can only take a show "
                "written as JSON (see the examples)."
            )
        from openai import OpenAI

        client = OpenAI(timeout=60, max_retries=2)

    start = time.time()
    try:
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input=story,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "show",
                    "schema": SCHEMA,
                    "strict": True,
                }
            },
            reasoning={"effort": "low"},
        )
    # The SDK raises many types; the user only needs the message.
    except Exception as error:
        raise StoryError(f"{MODEL} could not be reached: {error}") from None
    try:
        plan = json.loads(response.output_text)
    except (json.JSONDecodeError, TypeError):
        raise StoryError(f"{MODEL} did not answer with the expected JSON.") from None

    usage = getattr(response, "usage", None)
    return plan, {
        "planner": MODEL,
        "seconds": round(time.time() - start, 2),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def plan_show(story, client=None):
    """Story text (prose or JSON) -> (clean show, info about how it was planned)."""
    story = (story or "").strip()
    if not story:
        raise StoryError("Write a story first.")
    hand_written = parse_json_story(story)
    if hand_written is not None:
        return clean_show(hand_written, story), {"planner": "json", "seconds": 0.0}
    plan, info = ask_director(story, client)
    return clean_show(plan, story), info
