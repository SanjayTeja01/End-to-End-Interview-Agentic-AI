"use client";

/** Records one answer at a time from the live microphone (and optionally camera) tracks. */
export class AnswerRecorder {
  private audio: MediaRecorder | null = null;
  private video: MediaRecorder | null = null;
  private audioChunks: Blob[] = [];
  private videoChunks: Blob[] = [];
  startedAt: Date | null = null;

  static audioMime() {
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    return types.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) ?? "";
  }

  start(stream: MediaStream, withVideo: boolean) {
    this.audioChunks = [];
    this.videoChunks = [];
    const audioStream = new MediaStream(stream.getAudioTracks());
    this.audio = new MediaRecorder(audioStream, AnswerRecorder.audioMime() ? { mimeType: AnswerRecorder.audioMime() } : undefined);
    this.audio.ondataavailable = (e) => e.data.size && this.audioChunks.push(e.data);
    this.audio.start(1000);
    if (withVideo && stream.getVideoTracks().length && MediaRecorder.isTypeSupported("video/webm")) {
      this.video = new MediaRecorder(stream, { mimeType: "video/webm", videoBitsPerSecond: 500_000 });
      this.video.ondataavailable = (e) => e.data.size && this.videoChunks.push(e.data);
      this.video.start(1000);
    }
    this.startedAt = new Date();
  }

  get recording() {
    return this.audio?.state === "recording";
  }

  async stop(): Promise<{ audio: Blob; video: Blob | null; startedAt: Date; endedAt: Date }> {
    const stopOne = (r: MediaRecorder | null) =>
      new Promise<void>((res) => {
        if (!r || r.state === "inactive") return res();
        r.onstop = () => res();
        r.stop();
      });
    await Promise.all([stopOne(this.audio), stopOne(this.video)]);
    const type = this.audio?.mimeType || "audio/webm";
    return {
      audio: new Blob(this.audioChunks, { type }),
      video: this.videoChunks.length ? new Blob(this.videoChunks, { type: "video/webm" }) : null,
      startedAt: this.startedAt ?? new Date(),
      endedAt: new Date(),
    };
  }
}

export function extFor(mime: string) {
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("mp4")) return "mp4";
  return "webm";
}
