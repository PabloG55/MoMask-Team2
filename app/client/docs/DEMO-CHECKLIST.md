# Progress 2 evidence — what to capture

The repo contains working-source implementation and real local test assets, but the live browser API integration must be verified in your browser before claiming successful playback.

## Quick commands

```bash
git clone https://github.com/PabloG55/MoMask-Team2.git
cd MoMask-Team2
# Copy the contents of the supplied docs/ folder into this checkout's docs/
python3 -m http.server 8000
```

Open: `http://localhost:8000/docs/`.

**First check:** the left status says `Playing · built-in walk` and Xbot's body moves; the right says `Playing · offline sample` and the skeleton moves. Drag over a viewer to orbit. Use **Wave sample** to switch the local animation.

**Second check:** press **Generate motion** with `a person walks forward`, frames 100, seed 42. The button changes to **Generating…**. After the live server responds, the right skeleton should move and the status should say `Playing · API result`. Browser timings and stats should populate. Run `a person waves his hand` too.

## Recording — 25-second shot list

- 00–04 sec: Show both viewers, with Xbot walking and offline sample on the right.
- 04–08 sec: Type `a person waves his hand` into the prompt box.
- 08–16 sec: Click Generate; show the **Generating…** indicator (real elapsed time may vary).
- 16–23 sec: Show the returned BVH skeleton moving, Xbot still walking, and the performance stats.
- 23–25 sec: Scroll to the measurement log.

Record with macOS Cmd+Shift+5 / QuickTime, or your OS's screen recorder. If inference takes more or less time, trim or adjust the recording after capture — don't falsify the generation state.

## Slide placements

- **Slide 13:** `client-architecture.svg` / `screenshots/client-architecture.png`.
- **Slide 14:** screenshot showing left viewer with **Playing · built-in walk** after actually loading Xbot.
- **Slide 15:** screenshot showing the returned, moving BVH skeleton, API stats, and browser latency.
- **Slide 16:** insert the actual screen recording (20–30 s).
- **Slide 17:** export CSV after 3–5 successful browser requests each for the exact two prompts.

Never substitute the PDF's 7.8 s / 5.5 s preexisting API observations for *your browser's* `performance.now()` measurements. Screenshot files labeled `preview-not-live` are visual layouts only.
