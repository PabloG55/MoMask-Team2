---
title: MoMask Team2
emoji: 🕺
colorFrom: pink
colorTo: indigo
sdk: gradio
sdk_version: 6.30.0
python_version: '3.12'
app_file: app.py
pinned: false
license: mit
---

# MoMask as a service

ITCS 6166 (Computer Communication and Networks), Topic 2: Generative AI as a Service. Team 2:

- **Pablo Garces**: server (model, hosting, network measurements). This repository.
- **Ramisha Mahiyat**: client (Three.js character, narration).

The idea: instead of streaming video of a person moving, send a short text description and let the server generate the motion. This repository serves [MoMask](https://github.com/EricGuo5513/momask-codes), a text-to-3D-motion model, as an API. Send an action such as `a person walks forward` and get back:

| Output | What it is | Typical size (100 frames, 5 s) |
|---|---|---|
| BVH | the skeleton animation (22 joints, 20 fps). The client plays this on a character. | ~70 KB (~27 KB gzipped) |
| MP4 | a stick-figure preview video | ~40 KB |
| JSON | network measurements: frames, generation time, payload sizes | under 100 bytes |

It runs as a Hugging Face Space on ZeroGPU and falls back to CPU when no GPU is present. On first start, the pretrained checkpoints are downloaded from [`pgarces/momask-checkpoints`](https://huggingface.co/pgarces/momask-checkpoints).

## Run it locally

Tested on macOS (Apple silicon, CPU only) with Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt gradio
python app.py
```

Then open http://127.0.0.1:7860. The first start downloads the checkpoints into `checkpoints/`; later starts reuse them.

## Call the API

```python
from gradio_client import Client

client = Client("http://127.0.0.1:7860/")   # or "pgarces/MoMask-Team2" once the Space is up
bvh_path, mp4, stats = client.predict(
    "a person walks forward",  # action
    100,                       # frames (0 = let the model choose the length)
    42,                        # seed
    api_name="/generate",
)
print(stats)
# {"frames": 100, "generation_seconds": 2.62, "bvh_bytes": 70515, "mp4_bytes": 43364}
```

`generation_seconds` measures the model only (the example is from a Mac CPU). Converting to BVH and rendering the MP4 add a few seconds to the round trip.

## What we changed from upstream

This repository started as a copy of [EricGuo5513/momask-codes](https://github.com/EricGuo5513/momask-codes) at commit `94a6636`. The model, training and inference code are unchanged. We added:

- `app.py`: the Gradio service and its `/generate` API
- `requirements.txt`: rewritten for torch 2.11 / numpy 2.1.3. The original pins torch 1.12, which ZeroGPU does not accept.
- `packages.txt`: `ffmpeg`, for the MP4 preview

And made compatibility fixes so the original code runs on current libraries:

- `visualization/Animation.py`, `visualization/Quaternions.py`: `numpy.core.umath_tests.matrix_multiply` → `np.matmul` (removed in NumPy 2)
- `visualization/remove_fs.py`, `utils/motion_process.py`, `common/quaternion.py`: `np.float` → `float` (alias removed from NumPy)
- `utils/plot_script.py`: `Axes3D(fig)` → `fig.add_subplot(111, projection="3d")`, and frame clearing with `artist.remove()` (both required by newer Matplotlib)

Training, evaluation and dataset scripts from upstream are still here but untested with these dependencies. For those, follow the [upstream README](https://github.com/EricGuo5513/momask-codes#readme).

## Credit

MoMask is the work of Chuan Guo, Yuxuan Mu, Muhammad Gohar Javed, Sen Wang and Li Cheng (University of Alberta):

> *MoMask: Generative Masked Modeling of 3D Human Motions.* CVPR 2024. [Paper](https://arxiv.org/abs/2312.00063) · [Project page](https://ericguo5513.github.io/momask/) · [Code](https://github.com/EricGuo5513/momask-codes)

```bibtex
@inproceedings{guo2024momask,
  title={Momask: Generative masked modeling of 3d human motions},
  author={Guo, Chuan and Mu, Yuxuan and Javed, Muhammad Gohar and Wang, Sen and Cheng, Li},
  booktitle={Proceedings of the IEEE/CVF Conference on Computer Vision and Pattern Recognition},
  pages={1900--1910},
  year={2024}
}
```

The original code is MIT-licensed; its copyright notice is kept in [`LICENSE`](LICENSE).
