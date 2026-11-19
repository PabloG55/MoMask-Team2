# MoMask — React Native + Expo (phone app)

This is **an Expo React Native app**, not the earlier Capacitor app. It uses native React Native components for the write, loading, and watch screens. It embeds the existing Three.js/VRM player inside `react-native-webview` so the `/show` backend, character models, synchronized voices, and subtitles continue working. It is a development starter, not a tested store-ready build.

## 1. Install and start

From `app/expo-mobile/`:

```bash
npm install
npx expo start
```

Install **Expo Go** on your iPhone or Android phone and scan the QR code.

The app loads the show player from the Space, https://pgarces-momask-team2.hf.space/tinystage/, so no server on your Mac is needed. To test a local copy of `app/client/story/` instead, copy `.env.example` to `.env.local` and set `EXPO_PUBLIC_STORY_URL` to your Mac's Wi-Fi address (not localhost).

## 2. Test

1. Tap an example idea, then **Make my show**.
2. A native full-screen curtain screen shows the elapsed time while the existing web player calls `Client.connect('pgarces/MoMask-Team2')` and `predict('/show', { story, seed: 42 })`.
3. Once motions, voice, and timeline are loaded, the native watch screen appears with the web player, subtitles, and play/pause/scrubbing.
4. Tap **Watch it again**, then **Make another story**.
5. To test the prerecorded examples without waiting for the live Space, enable **Use saved example shows**, select one of the three example ideas, and try again. This only avoids the API call; the saved `.glb` and `.mp3` files still come from the Space.

## Important limitations

- This is a *hybrid* Expo React Native app: React Native screens plus a WebView for Three.js. It isn't a pure-native GL/VRM renderer.
- Some iOS/Android WebView devices may block audio autoplay. If voices don't start, press Play in the viewer.
- The live `/show` request requires an available Space and server-side key for free text; an example's saved fallback can still work.
- Expo Go is for development; App Store / Play Store distribution is a separate build and signing step.
- JavaScript and the embedded 3D performance **have not been tested on a real phone** in this environment. Try the saved demo before relying on it in a presentation.
- Keep `.env.local` out of commits. Do not put API keys in Expo client code.

See Expo docs: https://docs.expo.dev/get-started/start-developing/ and https://docs.expo.dev/versions/latest/sdk/webview/
