"""The files a request sends: one folder per request, deleted after an hour so the disk
doesn't fill up."""

import glob
import gzip
import os
import shutil
import time
import uuid

KEEP_SECONDS = 3600
KINDS = ("generate", "story", "show")


def new_dir(out_root, kind):
    clean_old(out_root)
    path = os.path.join(out_root, f"{kind}-{uuid.uuid4().hex[:10]}")
    os.makedirs(path)
    return path


def gzip_size(path):
    with open(path, "rb") as f:
        return len(gzip.compress(f.read(), 9))


def clean_old(out_root, now=None):
    # Safe to delete: Gradio already copied the returned files into its own cache.
    now = time.time() if now is None else now
    for kind in KINDS:
        for folder in glob.glob(os.path.join(out_root, f"{kind}-*")):
            if now - os.path.getmtime(folder) > KEEP_SECONDS:
                shutil.rmtree(folder, ignore_errors=True)
