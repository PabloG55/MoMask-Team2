"""MoMask as a service (ITCS 6166, Team 2): /generate, /story and /show.

momask/ is the authors' code, app/ is ours.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(ROOT, "app"), os.path.join(ROOT, "momask")]

import spaces  # noqa: E402,F401  before anything touches CUDA (ZeroGPU)
from dotenv import load_dotenv  # noqa: E402

from server import api, ui  # noqa: E402

load_dotenv()  # OpenAI key: .env locally, a secret on the Space
api.start()
demo = ui.build()

if __name__ == "__main__":
    demo.launch()
