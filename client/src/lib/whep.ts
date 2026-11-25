import { MEDIAMTX_URL, STREAM_PATH } from "./config";
import { negotiate } from "./whip";

export async function startWhep(onStream: (stream: MediaStream) => void) {
  const pc = new RTCPeerConnection();
  pc.addTransceiver("video", { direction: "recvonly" });
  pc.ontrack = (e) => onStream(e.streams[0]);

  try {
    return await negotiate(pc, `${MEDIAMTX_URL}/${STREAM_PATH}/whep`);
  } catch (err) {
    pc.close();
    throw err;
  }
}
