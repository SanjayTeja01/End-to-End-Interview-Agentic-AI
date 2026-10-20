"use client";

/**
 * WebRTC for live video. The candidate's browser publishes its camera/mic stream to each institution monitor
 * (peer-to-peer, signalled over the session WebSocket). Video is used only for the live interview experience
 * and monitoring — never for facial, emotional or biometric analysis.
 */
type Send = (type: string, data: unknown) => void;

const iceConfig = (servers: string[]): RTCConfiguration => ({ iceServers: servers.length ? [{ urls: servers }] : [] });

export class CandidatePublisher {
  private peers = new Map<string, RTCPeerConnection>();
  constructor(private stream: () => MediaStream | null, private send: Send, private ice: string[]) {}

  async handleSignal(data: Record<string, unknown>) {
    const monitor = String(data.sender_id ?? data.monitor_id ?? "");
    if (data.kind === "monitor_joined" || data.kind === "request_offer") return this.offer(String(data.monitor_id ?? monitor));
    const pc = this.peers.get(monitor);
    if (!pc) return;
    if (data.kind === "answer") await pc.setRemoteDescription(data.sdp as RTCSessionDescriptionInit);
    if (data.kind === "ice" && data.candidate) await pc.addIceCandidate(data.candidate as RTCIceCandidateInit).catch(() => undefined);
  }

  private async offer(monitorId: string) {
    const stream = this.stream();
    if (!stream || !monitorId) return;
    this.peers.get(monitorId)?.close();
    const pc = new RTCPeerConnection(iceConfig(this.ice));
    this.peers.set(monitorId, pc);
    stream.getTracks().forEach((t) => pc.addTrack(t, stream));
    pc.onicecandidate = (e) => e.candidate && this.send("signal", { kind: "ice", candidate: e.candidate.toJSON(), target: monitorId });
    pc.onconnectionstatechange = () => {
      if (["failed", "closed"].includes(pc.connectionState)) this.peers.delete(monitorId);
    };
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    this.send("signal", { kind: "offer", sdp: pc.localDescription?.toJSON(), target: monitorId });
  }

  close() {
    this.peers.forEach((p) => p.close());
    this.peers.clear();
  }
}

export class MonitorViewer {
  private pc: RTCPeerConnection | null = null;
  constructor(private myId: string, private send: Send, private ice: string[], private onStream: (s: MediaStream) => void) {}

  requestOffer() {
    this.send("signal", { kind: "request_offer", monitor_id: this.myId });
  }

  async handleSignal(data: Record<string, unknown>) {
    if (data.target && data.target !== this.myId) return; // addressed to another monitor
    if (data.kind === "offer") {
      this.pc?.close();
      const pc = new RTCPeerConnection(iceConfig(this.ice));
      this.pc = pc;
      pc.ontrack = (e) => e.streams[0] && this.onStream(e.streams[0]);
      pc.onicecandidate = (e) => e.candidate && this.send("signal", { kind: "ice", candidate: e.candidate.toJSON() });
      await pc.setRemoteDescription(data.sdp as RTCSessionDescriptionInit);
      const answer = await pc.createAnswer();
      await pc.setLocalDescription(answer);
      this.send("signal", { kind: "answer", sdp: pc.localDescription?.toJSON() });
    } else if (data.kind === "ice" && data.candidate && this.pc) {
      await this.pc.addIceCandidate(data.candidate as RTCIceCandidateInit).catch(() => undefined);
    }
  }

  close() {
    this.pc?.close();
    this.pc = null;
  }
}
