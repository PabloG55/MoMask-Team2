# MoMask — React Native + Expo (phone app)

This is **an Expo React Native app**, not the earlier Capacitor app. It uses native React Native components for the write, loading, and watch screens. It embeds the existing Three.js/VRM player inside `react-native-webview` so the `/show` backend, character models, synchronized voices, and subtitles continue working. It is a development starter, not a tested store-ready build.

## 1. Restore the browser show client if missing

From repository root:

```bash
git fetch origin
git ls-tree -r --name-only origin/ramisha-show-demo app/client/story
# Only if you see the story client files in that listing:
git restore --source=origin/ramisha-show-demo -- app/client/story/
```

The three-step frontend patch must be present. At minimum, `app/client/story/index.html`, `main.js`, `style.css`, `player.js`, `examples.json`, and the demo/character/set folders are needed. The Expo app does not copy these large assets: it loads them from the Python web server running on your Mac.

## 2. Create the Expo project in VS Code's terminal

From the `MoMask-Team2` repository root:

```bash
npx create-expo-app@latest app/expo-mobile --template blank
cd app/expo-mobile
npx expo install react-native-webview
```

**Now copy this patch's `App.js`, `.env.example`, and `README.md` into `app/expo-mobile/`**, replacing the template's `App.js`. If you extracted the patch before running create-expo-app, create the Expo project in a temporary directory instead, copy its generated package files into `app/expo-mobile/`, and keep the patch's `App.js`. To avoid any overwrite confusion, generating the Expo project *first* is recommended.

## 3. Start the show server on your Mac (Terminal 1)

From repository root:

```bash
python3 -m http.server 8831 --bind 0.0.0.0 --directory app/client/story
```

Determine your Mac's local Wi-Fi IP address:

```bash
ipconfig getifaddr en0
```

You might get an address like `192.168.1.23`. From your **phone's browser**, confirm `http://192.168.1.23:8831/index.html` loads. Both devices must be on the same Wi-Fi network. Your macOS firewall may ask permission to allow connections. If `en0` has no address, check the active network interface in System Settings.

## 4. Configure and start Expo (Terminal 2)

In `app/expo-mobile/`:

```bash
cp .env.example .env.local
```

Edit `.env.local` with the **actual IP address** from Step 3:

```ini
EXPO_PUBLIC_STORY_URL=http://192.168.1.23:8831/index.html
```

Then run:

```bash
npx expo start --clear
```

Install **Expo Go** on your iPhone or Android device and scan the QR code. This lets you run the app on a real phone without installing Xcode. You may need to sign into Expo Go. If QR scanning has connectivity issues, try `npx expo start --tunnel` (the Python story server must still be reachable from the phone over Wi-Fi; the Expo tunnel does not automatically tunnel the separate Python server).

## 5. Test

1. Tap an example idea, then **Make my show**.
2. A native full-screen curtain screen shows the elapsed time while the existing web player calls `Client.connect('pgarces/MoMask-Team2')` and `predict('/show', { story, seed: 42 })`.
3. Once motions, voice, and timeline are loaded, the native watch screen appears with the web player, subtitles, and play/pause/scrubbing.
4. Tap **Watch it again**, then **Make another story**.
5. To test the prerecorded examples without waiting for the live Space, enable **Use saved example shows**, select one of the three example ideas, and try again. This only avoids the API call; the phone still needs access to the Python server for saved `.glb`, `.mp3`, and model assets.

## Important limitations

- This is a *hybrid* Expo React Native app: React Native screens plus a WebView for Three.js. It isn't a pure-native GL/VRM renderer.
- The phone cannot reach `localhost` on the Mac; use its LAN IP or host the story site securely over HTTPS.
- Some iOS/Android WebView devices may block audio autoplay. If voices don't start, press Play in the viewer.
- The live `/show` request requires an available Space and server-side key for free text; an example's saved fallback can still work.
- Expo Go is for development; App Store / Play Store distribution is a separate build and signing step.
- JavaScript and the embedded 3D performance **have not been tested on a real phone** in this environment. Try the saved demo before relying on it in a presentation.
- Keep `.env.local` out of commits. Do not put API keys in Expo client code.

See Expo docs: https://docs.expo.dev/get-started/start-developing/ and https://docs.expo.dev/versions/latest/sdk/webview/
