"""The service: models.py loads MoMask, api.py runs the endpoints, ui.py is the page."""

import os

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOMASK_DIR = os.path.join(os.path.dirname(APP_DIR), "momask")
