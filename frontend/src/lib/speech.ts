"use client";

/**
 * Live speech-to-text in the browser (Chrome/Edge Web Speech API). The transcript is sent with the recorded audio,
 * so the server can skip its own (slow, CPU-bound) transcription. Where the API is missing it simply returns "",
 * and the server transcribes the audio as before.
 */
type Recognition = {
  continuous: boolean; interimResults: boolean; lang: string;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null; onerror: (() => void) | null;
  start(): void; stop(): void;
};

type RecognitionCtor = new () => Recognition;
const recognitionCtor = (): RecognitionCtor | undefined => {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
};

export class LiveTranscriber {
  private rec: Recognition | null = null;
  private finals: string[] = [];
  private interim = "";
  private active = false;
  onText: ((text: string) => void) | null = null;

  static supported() {
    return !!recognitionCtor();
  }

  start(lang = "en-US") {
    this.finals = [];
    this.interim = "";
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = lang;
    rec.onresult = (e) => {
      this.interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) this.finals.push(r[0].transcript.trim());
        else this.interim += r[0].transcript;
      }
      this.onText?.(this.text);
    };
    // Chrome stops recognition after silences; restart while the candidate is still answering.
    rec.onend = () => { if (this.active) try { rec.start(); } catch { /* already running */ } };
    rec.onerror = () => undefined;
    this.rec = rec;
    this.active = true;
    try { rec.start(); } catch { this.active = false; }
  }

  get text() {
    return [...this.finals, this.interim.trim()].filter(Boolean).join(" ").trim();
  }

  stop(): string {
    this.active = false;
    try { this.rec?.stop(); } catch { /* ignore */ }
    this.rec = null;
    return this.text;
  }
}
