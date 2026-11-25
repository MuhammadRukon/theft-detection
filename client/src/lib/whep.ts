import { MEDIAMTX_URL, STREAM_PATH } from "./config";
import { negotiate } from "./webrtc";

export function startWhep(onStream: (stream: MediaStream) => void) {
  const pc = new RTCPeerConnection();
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (e) => onStream(e.streams[0]);

  return negotiate(pc, `${MEDIAMTX_URL}/${STREAM_PATH}/whep`);
}
