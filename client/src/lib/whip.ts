import { MEDIAMTX_URL, STREAM_PATH } from "./config";
import { negotiate } from "./webrtc";

export function startWhip(stream: MediaStream) {
  const pc = new RTCPeerConnection();
  stream.getTracks().forEach((track) => pc.addTrack(track, stream));

  // Prefer H.264, VP8 fallback; skip if the browser can't reorder codecs.
  const codecs = RTCRtpSender.getCapabilities?.("video")?.codecs;
  const video = pc.getTransceivers().find((t) => t.sender.track?.kind === "video");
  if (codecs && video?.setCodecPreferences) {
    const rank = (c: RTCRtpCodec) =>
      c.mimeType === "video/H264" ? 0 : c.mimeType === "video/VP8" ? 1 : 2;
    video.setCodecPreferences([...codecs].sort((a, b) => rank(a) - rank(b)));
  }

  return negotiate(pc, `${MEDIAMTX_URL}/${STREAM_PATH}/whip`);
}
