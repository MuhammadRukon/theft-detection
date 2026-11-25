import { useRef } from "react";
import { useSession } from "../hooks/useSession";
import { startWhep } from "../lib/whep";
import type { DetectionsEvent } from "../types/events";
import DetectionOverlay from "./DetectionOverlay";
import SessionPanel from "./SessionPanel";

export default function StreamViewer({ detections }: { detections: DetectionsEvent | null }) {
  const videoRef = useRef<HTMLVideoElement>(null);

  const session = useSession(
    async (isCurrent) =>
      startWhep((stream) => {
        if (isCurrent() && videoRef.current) videoRef.current.srcObject = stream;
      }),
    "Unable to connect",
  );

  function disconnect() {
    session.stop();
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  return (
    <SessionPanel
      title="Stream Viewer"
      videoRef={videoRef}
      startLabel="Connect"
      stopLabel="Disconnect"
      {...session}
      overlay={
        <DetectionOverlay videoRef={videoRef} detections={detections} active={session.active} />
      }
      onStart={session.start}
      onStop={disconnect}
    >
      Status: {session.active ? "Connected" : "Disconnected"}
    </SessionPanel>
  );
}
