"""Story -> steps: one action for MoMask plus the line the narrator says over it.

GPT-6 Luna plans free text; a JSON list written by hand skips it.
"""

import json
import os
import re
import time

MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
MAX_STEPS = 6
MIN_SECONDS, MAX_SECONDS, DEFAULT_SECONDS = 2.4, 9.8, 4.0
MAX_ACTION_WORDS = 20  # CLIP reads at most 77 tokens; HumanML3D captions are short
MAX_NARRATION_WORDS = 30
LANGUAGES = ("en", "es")


class StoryError(ValueError):
    """A problem with the story itself, shown to the user as it is."""


INSTRUCTIONS = """\
You turn a short story into steps for a 3D character. Each step is one body movement that a
text-to-motion model (MoMask, trained on HumanML3D) will animate, plus one line a narrator
reads while it plays.

action:
- One physical movement of the whole body, written like a HumanML3D caption: present tense,
  starting with "a person". Examples: "a person walks forward slowly", "a person jumps up and
  down twice", "a person waves with the right hand", "a person sits down", "a person kicks
  with the left leg", "a person turns around and walks back", "a person stretches both arms
  above the head", "a person dances happily".
- Only what the body does. No objects to hold, no other people, no facial expressions, no
  places, no camera. Turn feelings into movement ("sad" -> "a person walks slowly with the
  head down").
- In English, whatever language the story is in.

narration:
- One sentence that tells the story over that movement, in the story's language, at most 18
  words. Tell the story; don't describe the movement word for word.

seconds: how long the movement takes, between 2.5 and 9.5. A narration line takes about
one second per 2.5 words, so leave room for it.

Use 2 to 6 steps, in story order. title: a short title for the story, in its language.
language: "en" or "es", the language of the story.
"""

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "language", "steps"],
    "properties": {
        "title": {"type": "string"},
        "language": {"type": "string", "enum": list(LANGUAGES)},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["action", "narration", "seconds"],
                "properties": {
                    "action": {"type": "string"},
                    "narration": {"type": "string"},
                    "seconds": {"type": "number"},
                },
            },
        },
    },
}


def _words(text, limit):
    words = text.split()
    return " ".join(words[:limit])


def clean_action(text):
    """Make an action look like a HumanML3D caption: 'a person ...', lower case."""
    text = re.sub(r"\s+", " ", str(text)).strip().rstrip(".!")
    if not text:
        raise StoryError("A step has no action.")
    text = text[0].lower() + text[1:]
    if not re.match(r"^(a|the) person\b", text):
        text = re.sub(
            r"^(he|she|they|someone|the man|the woman|a man|a woman)\b\s*", "", text
        )
        text = f"a person {text}"
    return _words(text, MAX_ACTION_WORDS)


def clean_seconds(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = DEFAULT_SECONDS
    if seconds != seconds:  # NaN
        seconds = DEFAULT_SECONDS
    return min(MAX_SECONDS, max(MIN_SECONDS, seconds))


def guess_language(text):
    spanish = len(
        re.findall(r"[ñáéíóú¿¡]|\b(el|la|los|las|una|y|que|se|con|del)\b", text.lower())
    )
    return "es" if spanish >= 2 else "en"


def clean_plan(plan, story_text=""):
    """Check the steps from the LLM or from a JSON list and fix what can be fixed."""
    steps = plan.get("steps") if isinstance(plan, dict) else plan
    if not isinstance(steps, list) or not steps:
        raise StoryError("The story has no steps.")

    cleaned = []
    for i, step in enumerate(steps[:MAX_STEPS]):
        if isinstance(step, str):
            step = {"action": step}
        if not isinstance(step, dict):
            raise StoryError(f"Step {i + 1} should be an object with an 'action'.")
        cleaned.append(
            {
                "action": clean_action(step.get("action", "")),
                "narration": _words(
                    re.sub(r"\s+", " ", str(step.get("narration") or "")).strip(),
                    MAX_NARRATION_WORDS,
                ),
                "seconds": clean_seconds(step.get("seconds", DEFAULT_SECONDS)),
            }
        )

    title = plan.get("title", "") if isinstance(plan, dict) else ""
    language = plan.get("language") if isinstance(plan, dict) else None
    if language not in LANGUAGES:
        language = guess_language(
            " ".join(s["narration"] for s in cleaned) or story_text
        )
    return {
        "title": str(title).strip()[:80] or "Story",
        "language": language,
        "steps": cleaned,
        "dropped_steps": max(0, len(steps) - MAX_STEPS),
    }


def parse_json_story(text):
    """A story written as JSON (a list of steps or {"title", "steps"}), else None."""
    stripped = text.strip()
    if not stripped.startswith(("[", "{")):
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError as error:
        raise StoryError(
            f"The story looks like JSON but isn't valid JSON: {error.msg} "
            f"(line {error.lineno}, column {error.colno})."
        ) from None


def ask_llm(story, client=None):
    """Free text -> plan, with GPT-6 Luna. Returns (plan, info about the call)."""
    if client is None:
        if not os.environ.get("OPENAI_API_KEY"):
            raise StoryError(
                "The server has no OPENAI_API_KEY, so it can only take a story "
                "written as a JSON list of steps."
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
                    "name": "story_plan",
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
    info = {
        "planner": MODEL,
        "seconds": round(time.time() - start, 2),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }
    return plan, info


def plan_story(story, client=None):
    """Story text (prose or JSON) -> (clean plan, info about how it was planned)."""
    story = (story or "").strip()
    if not story:
        raise StoryError("Write a story first.")

    hand_written = parse_json_story(story)
    if hand_written is not None:
        return clean_plan(hand_written, story), {"planner": "json", "seconds": 0.0}

    plan, info = ask_llm(story, client)
    return clean_plan(plan, story), info
