"""The web page. Its buttons are also the API: /story, /show and /generate."""

import json
import os

import gradio as gr

from server import APP_DIR, api

SHOW_EXAMPLES = os.path.join(APP_DIR, "client", "story", "examples.json")

EXAMPLE_STORY = (
    "Max wakes up late, stretches, and runs to catch the bus. "
    "He misses it, kicks the ground in frustration, then laughs and dances in the rain."
)


def story_page(story, seed, smooth):
    motion, voice, timeline, preview = api.tell_story(story, seed, smooth, preview=True)
    return preview or motion, voice, timeline, motion


def build():
    with open(SHOW_EXAMPLES) as f:
        first_show = json.load(f)[0]["show"]

    with gr.Blocks(title="MoMask Team 2") as demo:
        gr.Markdown("# MoMask: text → 3D motion (ITCS 6166, Team 2)")

        with gr.Tab("Story"):
            gr.Markdown(
                "Write a short story. GPT-6 Luna splits it into actions, MoMask animates each one "
                "and the transitions between them, and Kokoro narrates it. A JSON list of "
                '`{"action", "narration", "seconds"}` steps skips the LLM.'
            )
            story_input = gr.Textbox(label="Story", value=EXAMPLE_STORY, lines=4)
            with gr.Row():
                story_seed = gr.Number(label="Seed", value=42, precision=0)
                story_smooth = gr.Checkbox(label="Smooth transitions", value=True)
            story_button = gr.Button("Tell the story", variant="primary")

            with gr.Row():
                preview_output = gr.Model3D(
                    label="Xbot", clear_color=[0.96, 0.95, 0.92, 1.0], height=480
                )
                with gr.Column():
                    narration_output = gr.Audio(label="Narration", type="filepath")
                    motion_output = gr.File(
                        label="Animation for the client (.glb, no mesh)"
                    )
            timeline_output = gr.JSON(label="Timeline and network measurements")

            story_button.click(
                story_page,
                inputs=[story_input, story_seed, story_smooth],
                outputs=[
                    preview_output,
                    narration_output,
                    timeline_output,
                    motion_output,
                ],
                api_visibility="private",
            )

            # The /story API, hidden so it returns only the three files the client
            # needs.
            with gr.Row(visible=False):
                api_motion = gr.File()
                api_narration = gr.File()
                api_timeline = gr.JSON()
                api_button = gr.Button()
            api_button.click(
                api.story_api,
                inputs=[story_input, story_seed, story_smooth],
                outputs=[api_motion, api_narration, api_timeline],
                api_name="story",
            )

        with gr.Tab("Show"):
            gr.Markdown(
                "Pocoyo-style show: up to three characters take turns while a narrator talks to them. "
                "GPT-6 Luna directs (cast, set, light, camera, lines); MoMask moves every character; "
                "Kokoro gives each one a voice. A show written as JSON skips the LLM. "
                "Watch it in the player in `client/story/`."
            )
            show_input = gr.Textbox(
                label="Story or show JSON",
                lines=10,
                value=json.dumps(first_show, indent=1),
            )
            show_seed = gr.Number(label="Seed", value=42, precision=0)
            show_button = gr.Button("Make the show", variant="primary")
            with gr.Row():
                show_motions = gr.File(
                    label="One animation per character (.glb, no mesh)",
                    file_count="multiple",
                )
                show_voices = gr.Audio(label="Voices", type="filepath")
            show_timeline = gr.JSON(label="Timeline and network measurements")
            show_button.click(
                api.show_api,
                inputs=[show_input, show_seed],
                outputs=[show_motions, show_voices, show_timeline],
                api_name="show",
            )

        with gr.Tab("One action"):
            text_input = gr.Textbox(label="Action", value="a person walks forward")
            with gr.Row():
                length_input = gr.Number(label="Frames (0 = automatic)", value=100)
                seed_input = gr.Number(label="Seed", value=42)
            generate_button = gr.Button("Generate", variant="primary")

            bvh_output = gr.File(label="BVH (motion)")
            video_output = gr.Video(label="Preview")
            stats_output = gr.JSON(label="Network measurements")

            generate_button.click(
                api.generate,
                inputs=[text_input, length_input, seed_input],
                outputs=[bvh_output, video_output, stats_output],
                api_name="generate",
            )

    return demo
