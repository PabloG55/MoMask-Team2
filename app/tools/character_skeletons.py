"""Save each character's skeleton and body shapes as story/characters/<Name>.json, so
the server doesn't need the VRMs.

.venv/bin/python app/tools/character_skeletons.py
"""

import glob
import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from story.retarget import TargetSkeleton, read_glb  # noqa: E402
from tools.body_shapes import body_shapes  # noqa: E402

OUT = os.path.join(APP_DIR, "story", "characters")

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for vrm in sorted(
        glob.glob(os.path.join(APP_DIR, "client", "story", "characters", "*.vrm"))
    ):
        name = os.path.splitext(os.path.basename(vrm))[0]
        skeleton = TargetSkeleton.from_vrm(vrm)
        skeleton.body = body_shapes(*read_glb(vrm), skeleton)
        skeleton.save(
            os.path.join(OUT, f"{name}.json"),
            source=f"app/client/story/characters/{name}.vrm (100Avatars by Polygonal Mind, CC0)",
        )
        print(
            name, len(skeleton.names), "bones", "body" if skeleton.body else "NO BODY"
        )
