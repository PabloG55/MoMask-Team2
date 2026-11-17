"""Write story/xbot_skeleton.json from the client's Xbot.glb (only if the character
changes).

python app/tools/xbot_skeleton.py app/client/docs/assets/character/Xbot.glb
"""

import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from story.retarget import TargetSkeleton  # noqa: E402

if __name__ == "__main__":
    default = os.path.join(APP_DIR, "client", "docs", "assets", "character", "Xbot.glb")
    glb = sys.argv[1] if len(sys.argv) > 1 else default
    skeleton = TargetSkeleton.from_glb(glb)
    skeleton.save(os.path.join(APP_DIR, "story", "xbot_skeleton.json"))
    print(f"{len(skeleton.names)} bones -> story/xbot_skeleton.json")
