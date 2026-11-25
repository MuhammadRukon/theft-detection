import { MEDIAMTX_URL, STREAM_PATH } from "./config";

// Shared by WHIP and WHEP: offer -> wait for ICE -> POST SDP -> apply answer.
// Returns stop(), which closes the peer connection and DELETEs the session.
export async function negotiate(pc: RTCPeerConnection, url: string) {
  await pc.setLocalDescription(await pc.createOffer());
  if (pc.iceGatheringState !== "complete") {
    await new Promise<void>((resolve) => {
      const done = () => {
        pc.removeEventListener("icegatheringstatechange", check);
        resolve();
      };
      const check = () => pc.iceGatheringState === "complete" && done();
      pc.addEventListener("icegatheringstatechange", check);
      setTimeout(done, 2000); // shortcut: send what we have after 2s, fine on localhost
    });
  }

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/sdp" },
    body: pc.localDescription!.sdp,
  });
  if (!res.ok) throw new Error(`${url} responded ${res.status}`);
  const session = new URL(res.headers.get("Location") ?? "", url).href;
  await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });

  return async () => {
    pc.close();
    await fetch(session, { method: "DELETE" }).catch(() => {});
  };
}

export async function startWhip(stream: MediaStream) {
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

  try {
    return await negotiate(pc, `${MEDIAMTX_URL}/${STREAM_PATH}/whip`);
  } catch (err) {
    pc.close();
    throw err;
  }
}
