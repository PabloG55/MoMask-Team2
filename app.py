"""MoMask as a service (ITCS 6166, Team 2): /generate, /story and /show, and the TinyStage
page at /tinystage/.

momask/ is the authors' code, app/ is ours.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(ROOT, "app"), os.path.join(ROOT, "momask")]

import spaces  # noqa: E402,F401  before anything touches CUDA (ZeroGPU)
from dotenv import load_dotenv  # noqa: E402
from starlette.routing import Mount  # noqa: E402
from starlette.staticfiles import StaticFiles  # noqa: E402

from server import api, ui  # noqa: E402

load_dotenv()  # OpenAI key: .env locally, a secret on the Space
api.start()
demo = ui.build()

# The TinyStage page, served by the same app so it calls the API on its own origin.
# It goes through launch() so ZeroGPU still sees the Space start the usual way.
PAGE = os.path.join(ROOT, "app", "client", "story")
ROUTES = [Mount("/tinystage", app=StaticFiles(directory=PAGE, html=True))] if os.path.isdir(PAGE) else []

if __name__ == "__main__":
    demo.launch(app_kwargs={"routes": ROUTES})
