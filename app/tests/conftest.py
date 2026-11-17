import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [APP_DIR, os.path.join(os.path.dirname(APP_DIR), "momask")]
os.chdir(APP_DIR)
