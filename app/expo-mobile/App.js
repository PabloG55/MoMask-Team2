import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { WebView } from 'react-native-webview';

// The show player is the TinyStage page on our Space. EXPO_PUBLIC_STORY_URL can point
// it at a local copy for development (use the Mac's LAN address, not localhost).
const STORY_URL = process.env.EXPO_PUBLIC_STORY_URL || 'https://pgarces-momask-team2.hf.space/tinystage/';
const EXAMPLES = [
  { icon: '🦕', text: 'A dino kid tries a big jump while his teddy bear cheers him on.' },
  { icon: '🚀', text: 'An astronaut meets a robot and a friendly alien on the moon.' },
  { icon: '🐸', text: 'A happy frog and a friend have a dance party in the park, speaking Spanish.' },
];
const LOADING_LINES = [
  'Writing the script…',
  'Casting the characters…',
  'Moving the characters…',
  'Recording the voices…',
  'Getting the stage ready…',
];

function ActionButton({ title, onPress, secondary = false, disabled = false }) {
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        secondary ? styles.secondaryButton : styles.primaryButton,
        (pressed || disabled) && { opacity: 0.7 },
      ]}
    >
      <Text style={[styles.buttonText, secondary && styles.secondaryButtonText]}>{title}</Text>
    </Pressable>
  );
}

function Curtains({ elapsed }) {
  const pulse = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1450, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1450, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);
  const floatY = pulse.interpolate({ inputRange: [0, 1], outputRange: [0, -13] });
  return (
    <View style={styles.curtainStage}>
      <View style={styles.curtainSides}>
        <View style={[styles.curtain, styles.leftCurtain]}>
          {Array.from({ length: 7 }, (_, i) => <View key={`left${i}`} style={styles.curtainPleat} />)}
        </View>
        <View style={[styles.curtain, styles.rightCurtain]}>
          {Array.from({ length: 7 }, (_, i) => <View key={`right${i}`} style={styles.curtainPleat} />)}
        </View>
      </View>
      <View style={styles.valance} />
      <View style={styles.loadingCenter}>
        <Animated.Text style={[styles.loadingStar, { transform: [{ translateY: floatY }] }]}>✦</Animated.Text>
        <Text style={styles.loadingKicker}>BEHIND THE CURTAIN…</Text>
        <Text style={styles.loadingTitle}>Your magic is in the making!</Text>
        <Text style={styles.loadingLine}>{LOADING_LINES[Math.floor(elapsed / 7) % LOADING_LINES.length]}</Text>
        <ActivityIndicator size="large" color="#ffe38d" style={{ marginTop: 20 }} />
        <Text style={styles.elapsed}>{elapsed} seconds elapsed</Text>
        <Text style={styles.loadingFoot}>Shows usually take 30 seconds or longer, especially when the Space is waking up.</Text>
      </View>
    </View>
  );
}

function makePlayerScript(story) {
  // Bridge the existing, unchanged browser player to React Native.
  // The WebView performs the existing /show request, loads GLBs/MP3, and renders Three.js.
  return `
    (() => {
      try {
        const storyText = ${JSON.stringify(story)};
        const send = (type, message = '') => {
          window.ReactNativeWebView?.postMessage(JSON.stringify({ type, message }));
        };
        const css = document.createElement('style');
        css.textContent = [
          '.site-header,.watch-heading,.watch-actions,.footer-note { display:none !important; }',
          'body { background:#fff !important; }',
          'main { max-width:none !important; padding:0 !important; margin:0 !important; }',
          '.watch-step { padding:0 !important; margin:0 !important; max-width:none !important; }',
          '.player-wrap { margin:0 !important; border-radius:0 !important; box-shadow:none !important; }',
          '.screen { height: min(67svh, 530px) !important; min-height: 260px !important; }',
          '.watch-note { padding:6px 12px !important; font-size:13px !important; }'
        ].join(' ');
        document.head.appendChild(css);
        let lastEvent = '';
        const check = () => {
          const write = document.getElementById('write-step');
          const watch = document.getElementById('watch-step');
          const loading = document.getElementById('loading-step');
          const status = document.getElementById('status');
          if (watch && loading && !watch.hidden && loading.hidden) {
            if (lastEvent !== 'ready') { lastEvent = 'ready'; send('ready'); }
          } else if (write && !write.hidden && status?.classList.contains('error')) {
            const msg = status.textContent || 'Could not generate the show.';
            if (lastEvent !== 'error:' + msg) { lastEvent = 'error:' + msg; send('error', msg); }
          }
        };
        new MutationObserver(check).observe(document.body, {
          childList: true, subtree: true, characterData: true, attributes: true,
          attributeFilter: ['hidden', 'class']
        });
        const input = document.getElementById('story');
        const button = document.getElementById('make');
        if (!input || !button) { send('error', 'The story player page is missing its controls.'); return; }
        input.value = storyText;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        // Wait for main.js to finish loading its modules and attaching click handlers.
        let attempts = 0;
        const readyPoll = setInterval(() => {
          attempts += 1;
          if (document.querySelector('[data-idea]')?.dataset.story) {
            clearInterval(readyPoll);
            button.click();
            check();
          } else if (attempts > 240) {
            clearInterval(readyPoll);
            send('error', 'The story page did not finish loading. Check the web server and your phone connection.');
          }
        }, 250);
      } catch (error) {
        window.ReactNativeWebView?.postMessage(JSON.stringify({ type:'error', message:String(error) }));
      }
    })();
    true;
  `;
}

export default function App() {
  const [story, setStory] = useState('');
  const [phase, setPhase] = useState('write');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState('');
  const [run, setRun] = useState(null);
  const [demoMode, setDemoMode] = useState(false);
  const webRef = useRef(null);
  const playerScript = useMemo(() => (run ? makePlayerScript(run.story) : ''), [run]);

  useEffect(() => {
    if (phase !== 'loading') return;
    const timer = setInterval(() => setSeconds(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, [phase]);

  const start = () => {
    if (!story.trim()) { setError('First, tell us what your story is about.'); return; }
    if (!STORY_URL) {
      setError('Set EXPO_PUBLIC_STORY_URL in app/expo-mobile/.env.local first (see README).');
      return;
    }
    if (demoMode && !EXAMPLES.some(example => example.text === story.trim())) {
      setError('Saved demo mode supports the three example ideas. Tap an idea below.');
      return;
    }
    Keyboard.dismiss();
    setError('');
    setSeconds(0);
    setRun({ story: story.trim(), id: Date.now() });
    setPhase('loading');
  };

  const reset = () => {
    setRun(null); // unmounting the WebView also stops the old audio and rendering loop
    setSeconds(0);
    setPhase('write');
    setError('');
    setStory('');
  };

  const handleMessage = event => {
    try {
      const data = JSON.parse(event.nativeEvent.data);
      if (data.type === 'ready') setPhase('watch');
      if (data.type === 'error') {
        setRun(null);
        setPhase('write');
        setError(data.message || 'Could not make your show. Try one of the example ideas.');
      }
    } catch { /* ignore irrelevant webview messages */ }
  };

  const playerURL = STORY_URL
    ? `${STORY_URL}${STORY_URL.includes('?') ? '&' : '?'}${demoMode ? 'demo=1&' : ''}expo=1`
    : '';

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar barStyle={phase === 'loading' ? 'light-content' : 'dark-content'} />
      {phase === 'write' && (
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={styles.writeContent} keyboardShouldPersistTaps="handled">
            <View style={styles.brandRow}>
              <Text style={styles.brand}>✦ TinyStage<Text style={styles.brandDot}>.</Text></Text>
              <Text style={styles.brandTag}>A little story. A big show.</Text>
            </View>
            <Text style={styles.eyebrow}>✧ YOUR IMAGINATION, ON STAGE ✧</Text>
            <Text style={styles.headline}>Every great show starts with <Text style={styles.headlineAccent}>your</Text> story.</Text>
            <Text style={styles.subtitle}>Dream up a little adventure. We'll bring the characters, movement, and voices to life.</Text>
            <View style={styles.storyCard}>
              <Text style={styles.fieldTitle}>What should your story be about?</Text>
              <TextInput
                multiline
                value={story}
                onChangeText={text => { setStory(text); if (error) setError(''); }}
                placeholder="Once upon a time, a little dinosaur…"
                placeholderTextColor="#a49ab7"
                maxLength={3000}
                textAlignVertical="top"
                style={styles.input}
                accessibilityLabel="Your story"
              />
              <Text style={styles.helper}>{story.length} / 3000 characters</Text>
              <ActionButton title="✦  Make my show  →" onPress={start} />
              {!!error && <Text style={styles.error}>{error}</Text>}
            </View>
            <Text style={styles.ideasTitle}>✨ Need a little inspiration?</Text>
            {EXAMPLES.map(({ icon, text }) => (
              <Pressable key={text} style={styles.ideaCard} onPress={() => { setStory(text); setError(''); Keyboard.dismiss(); }}>
                <Text style={styles.ideaIcon}>{icon}</Text><Text style={styles.ideaText}>{text}</Text><Text style={styles.ideaArrow}>↗</Text>
              </Pressable>
            ))}
            <Pressable onPress={() => setDemoMode(value => !value)} style={styles.demoToggle}>
              <Text style={styles.demoToggleText}>{demoMode ? '✓ Saved demo mode on' : 'Use saved example shows (offline fallback)'}</Text>
            </Pressable>
          </ScrollView>
        </KeyboardAvoidingView>
      )}

      {/* Keep the browser's Three.js renderer mounted while generating, behind the native loading screen. */}
      {!!run && (
        <View style={[styles.playerContainer, phase === 'loading' && styles.hiddenPlayer]}>
          {phase === 'watch' && (
            <View style={styles.watchHeader}>
              <Text style={styles.eyebrow}>✦ THE STAGE IS YOURS</Text>
              <Text style={styles.watchTitle}>It's showtime!</Text>
            </View>
          )}
          <WebView
            key={run.id}
            ref={webRef}
            source={{ uri: playerURL }}
            onMessage={handleMessage}
            onError={event => {
              setRun(null); setPhase('write');
              setError(`Can't reach the story server. Check your Mac's IP address and the Python server. ${event.nativeEvent.description || ''}`);
            }}
            onHttpError={event => {
              if (event.nativeEvent.statusCode >= 400 && event.nativeEvent.url === playerURL) {
                setRun(null); setPhase('write');
                setError(`The story server returned HTTP ${event.nativeEvent.statusCode}. Check the server URL.`);
              }
            }}
            injectedJavaScript={playerScript}
            mediaPlaybackRequiresUserAction={false}
            allowsInlineMediaPlayback
            javaScriptEnabled
            domStorageEnabled
            originWhitelist={['*']}
            style={{ flex: 1, backgroundColor: '#fff' }}
          />
          {phase === 'watch' && (
            <View style={styles.watchActions}>
              <ActionButton title="↻  Watch it again" onPress={() => webRef.current?.injectJavaScript("document.getElementById('again')?.click(); true;")} />
              <ActionButton title="←  Make another story" onPress={reset} secondary />
            </View>
          )}
        </View>
      )}
      {phase === 'loading' && <Curtains elapsed={seconds} />}
    </SafeAreaView>
  );
}

const PURPLE = '#7037cf';
const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: '#faf7ff' },
  writeContent: { paddingHorizontal: 22, paddingBottom: 52, paddingTop: 14 },
  brandRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 38 },
  brand: { color: '#40206a', fontSize: 24, fontWeight: '900' },
  brandDot: { color: '#b17df3' },
  brandTag: { color: '#86729f', fontWeight: '600', fontSize: 10, maxWidth: 125, textAlign: 'right' },
  eyebrow: { color: '#8c4ad5', fontSize: 11, letterSpacing: 1.2, textAlign: 'center', fontWeight: '800' },
  headline: { marginTop: 14, fontWeight: '900', fontSize: 35, color: '#322044', textAlign: 'center', lineHeight: 42 },
  headlineAccent: { color: PURPLE },
  subtitle: { textAlign: 'center', color: '#716680', fontSize: 15, lineHeight: 23, marginTop: 15, marginBottom: 27 },
  storyCard: { padding: 19, borderRadius: 22, backgroundColor: '#fff', borderColor: '#e9defb', borderWidth: 1, shadowColor: PURPLE, shadowOpacity: 0.08, shadowRadius: 16, elevation: 3 },
  fieldTitle: { color: '#352447', fontWeight: '800', fontSize: 16, marginBottom: 12 },
  input: { borderColor: '#e3d8f5', borderWidth: 1, borderRadius: 13, backgroundColor: '#fdfbff', padding: 14, fontSize: 16, lineHeight: 23, minHeight: 138, color: '#30213f' },
  helper: { textAlign: 'right', color: '#998aad', fontSize: 11, marginTop: 8, marginBottom: 14 },
  button: { paddingVertical: 16, borderRadius: 13, alignItems: 'center', justifyContent: 'center', width: '100%' },
  primaryButton: { backgroundColor: PURPLE },
  secondaryButton: { backgroundColor: '#eee7fb', marginTop: 10 },
  buttonText: { color: '#fff', fontWeight: '800', fontSize: 16 },
  secondaryButtonText: { color: '#593092' },
  error: { color: '#ad2652', marginTop: 12, fontSize: 14 },
  ideasTitle: { textAlign: 'center', color: '#513870', fontWeight: '800', fontSize: 16, marginTop: 30, marginBottom: 13 },
  ideaCard: { backgroundColor: '#fff', borderRadius: 15, borderWidth: 1, borderColor: '#eae2f6', paddingHorizontal: 15, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', marginBottom: 10 },
  ideaIcon: { fontSize: 23, marginRight: 13 },
  ideaText: { color: '#544962', fontSize: 14, lineHeight: 20, flex: 1 },
  ideaArrow: { color: '#8f58ce', fontSize: 18, marginLeft: 8 },
  demoToggle: { alignSelf: 'center', padding: 14, marginTop: 8 },
  demoToggleText: { fontSize: 12, color: '#8a799a', textDecorationLine: 'underline' },
  playerContainer: { flex: 1, backgroundColor: '#fff' },
  hiddenPlayer: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, opacity: 0 },
  watchHeader: { paddingTop: 16, paddingHorizontal: 20, paddingBottom: 8, backgroundColor: '#faf7ff' },
  watchTitle: { textAlign: 'center', fontSize: 29, color: '#322044', fontWeight: '900', marginTop: 4 },
  watchActions: { backgroundColor: '#fff', paddingVertical: 14, paddingHorizontal: 18, borderTopWidth: 1, borderTopColor: '#eee7f7' },
  curtainStage: { flex: 1, backgroundColor: '#1c0b37', overflow: 'hidden', justifyContent: 'center' },
  curtainSides: { ...StyleSheet.absoluteFillObject, flexDirection: 'row', justifyContent: 'space-between' },
  curtain: { width: '51%', height: '100%', flexDirection: 'row', overflow: 'hidden', backgroundColor: '#66207d' },
  leftCurtain: { borderRightWidth: 10, borderRightColor: '#4a125b' },
  rightCurtain: { borderLeftWidth: 10, borderLeftColor: '#4a125b' },
  curtainPleat: { flex: 1, backgroundColor: '#762486', marginRight: 3, borderRightWidth: 3, borderRightColor: '#5a176d' },
  valance: { position: 'absolute', height: 66, top: 0, left: 0, right: 0, backgroundColor: '#8c2a8d', borderBottomWidth: 13, borderBottomColor: '#d4905f' },
  loadingCenter: { padding: 26, margin: 22, backgroundColor: 'rgba(32,12,62,0.89)', borderRadius: 24, alignItems: 'center', borderWidth: 1, borderColor: '#ad75bd' },
  loadingStar: { fontSize: 60, color: '#ffe38d', marginBottom: 12 },
  loadingKicker: { color: '#dbc0f4', fontSize: 12, fontWeight: '800', letterSpacing: 1.2 },
  loadingTitle: { color: '#fff', fontSize: 29, fontWeight: '900', textAlign: 'center', lineHeight: 34, marginTop: 11, marginBottom: 13 },
  loadingLine: { color: '#ffdd94', fontSize: 19, fontWeight: '700', textAlign: 'center' },
  elapsed: { color: '#fff', fontSize: 15, fontWeight: '700', marginTop: 17 },
  loadingFoot: { textAlign: 'center', color: '#cdb4e7', fontSize: 12, marginTop: 14, lineHeight: 18 },
});
