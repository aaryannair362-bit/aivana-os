// Records microphone audio via MediaRecorder and uploads it to POST {apiBase}/transcribe-audio
// for server-side transcription (backend/app/main.py's transcribe_audio_endpoint, which calls
// ScribeEngine.transcribe_audio -- Groq Whisper). Replaces the old browser
// SpeechRecognition-based live captioning, which mis-transcribed Hindi/Hinglish speech into
// English-phonetic nonsense (a real drug name came out as unrelated English words -- Whisper
// handles code-switched Hindi+English far better). There is no more incremental "live caption"
// concept: only a single transcript comes back, after stop() uploads the full recording.
//
// Shared by frontend/opd.html, frontend/ipd.html (nursing note + ward round), and
// frontend/headnurse.html -- plain <script src="/js/voice-capture.js">, no build step/module
// system, matching this app's existing frontend style (see frontend/js/ipd-shared.js).
//
// Usage:
//   const recorder = createVoiceRecorder({ apiBase: API_BASE, getAuthToken: () => accessToken });
//   if (!recorder.isSupported()) { /* fall back to manual typing, same as before */ }
//   await recorder.start();            // throws if mic permission denied
//   const transcript = await recorder.stop();   // throws if upload/transcription fails
//   recorder.getLevel();               // 0-1 live mic input level while recording, see below

function createVoiceRecorder({ apiBase, getAuthToken }) {
    // Chrome/Firefox produce webm; Safari doesn't support webm at all and needs mp4. Groq's
    // accepted upload formats include both, so no client-side transcoding is needed -- just
    // use whatever the browser can actually produce, in accuracy-preference order.
    const MIME_CANDIDATES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];

    let mediaRecorder = null;
    let stream = null;
    let chunks = [];
    let audioCtx = null;
    let analyser = null;
    let levelData = null;

    function isSupported() {
        return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
    }

    function pickMimeType() {
        if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
        return MIME_CANDIDATES.find((t) => MediaRecorder.isTypeSupported(t)) || '';
    }

    // Live 0-1 input level (RMS of the current time-domain buffer), meant to be polled from a
    // requestAnimationFrame loop while recording to drive a visual "yes, I can hear you" meter.
    // Not transcription feedback (this app deliberately dropped live captions -- see the module
    // comment above) -- purely a signal that the mic is actually picking up sound as the doctor
    // talks, added because without ANY feedback during the silent recording phase, doctors
    // reported having to speak unnaturally slowly/over-enunciate out of uncertainty that
    // anything was being captured at all. Returns 0 when not recording or before the first
    // analyser frame is available.
    function getLevel() {
        if (!analyser || !levelData) return 0;
        analyser.getByteTimeDomainData(levelData);
        let sumSquares = 0;
        for (let i = 0; i < levelData.length; i++) {
            const centered = (levelData[i] - 128) / 128;
            sumSquares += centered * centered;
        }
        return Math.min(1, Math.sqrt(sumSquares / levelData.length) * 4);
    }

    async function start() {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        chunks = [];
        const mimeType = pickMimeType();
        mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
        mediaRecorder.ondataavailable = (e) => {
            if (e.data && e.data.size > 0) chunks.push(e.data);
        };
        const started = new Promise((resolve, reject) => {
            mediaRecorder.onstart = resolve;
            mediaRecorder.onerror = (e) => reject(e.error || new Error('Recording failed to start'));
        });
        mediaRecorder.start();
        await started;

        // Best-effort: a browser without Web Audio API (or one that throws on construction)
        // just means getLevel() always returns 0 -- the recording/transcription path above is
        // fully independent of this and must not be affected by it.
        try {
            const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
            audioCtx = new AudioContextCtor();
            const source = audioCtx.createMediaStreamSource(stream);
            analyser = audioCtx.createAnalyser();
            analyser.fftSize = 256;
            levelData = new Uint8Array(analyser.frequencyBinCount);
            // Deliberately NOT connected to audioCtx.destination -- this taps the stream for
            // level metering only; routing it to output would echo the doctor's own mic back
            // through their speakers.
            source.connect(analyser);
        } catch (err) {
            audioCtx = null;
            analyser = null;
            levelData = null;
        }
    }

    function stop() {
        return new Promise((resolve, reject) => {
            if (!mediaRecorder) {
                reject(new Error('Not recording'));
                return;
            }
            const recorder = mediaRecorder;
            mediaRecorder = null;
            if (audioCtx) {
                audioCtx.close().catch(() => {});
                audioCtx = null;
                analyser = null;
                levelData = null;
            }
            recorder.onstop = async () => {
                if (stream) {
                    stream.getTracks().forEach((t) => t.stop());
                    stream = null;
                }
                if (chunks.length === 0) {
                    resolve('');
                    return;
                }
                const mimeType = recorder.mimeType || 'audio/webm';
                const ext = mimeType.includes('mp4') ? 'mp4' : mimeType.includes('ogg') ? 'ogg' : 'webm';
                const blob = new Blob(chunks, { type: mimeType });
                chunks = [];
                try {
                    const form = new FormData();
                    form.append('audio', blob, `recording.${ext}`);
                    const headers = {};
                    const token = getAuthToken && getAuthToken();
                    if (token) headers['Authorization'] = `Bearer ${token}`;
                    // Deliberately NOT going through this page's JSON apiRequest() helper --
                    // it hardcodes 'Content-Type: application/json' as a header default, which
                    // is incompatible with FormData (the browser must set the multipart
                    // boundary itself, which only happens when no Content-Type is set at all).
                    const res = await fetch(`${apiBase}/transcribe-audio`, { method: 'POST', headers, body: form });
                    if (!res.ok) {
                        const data = await res.json().catch(() => ({}));
                        throw new Error(data.detail || `Transcription failed (${res.status})`);
                    }
                    const data = await res.json();
                    resolve(data.transcript || '');
                } catch (err) {
                    reject(err);
                }
            };
            recorder.stop();
        });
    }

    return { start, stop, isSupported, getLevel };
}
