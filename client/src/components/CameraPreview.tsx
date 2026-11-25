import { useRef, useState } from "react";
import { useSession } from "../hooks/useSession";
import { startWhip } from "../lib/whip";
import SessionPanel from "./SessionPanel";

export default function CameraPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPublishing, setIsPublishing] = useState(false);

  const session = useSession(async (isCurrent, register) => {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15 } },
      audio: false,
    });
    const stopTracks = () => stream.getTracks().forEach((track) => track.stop());

    if (!isCurrent()) {
      stopTracks();
      return async () => {};
    }

    if (videoRef.current) videoRef.current.srcObject = stream;
    register(stopTracks); // Stop Camera works while publishing is still negotiating

    let stopWhip;
    try {
      stopWhip = await startWhip(stream);
    } catch (err) {
      throw new Error(
        `Publish failed (is MediaMTX running?): ${err instanceof Error ? err.message : err}`,
      );
    }
    if (isCurrent()) setIsPublishing(true);
    return async () => {
      stopTracks();
      await stopWhip();
    };
  }, "Unable to access camera");

  function stopCamera() {
    session.stop();
    setIsPublishing(false);
    if (videoRef.current) videoRef.current.srcObject = null;
  }

  return (
    <SessionPanel
      title="Webcam Preview"
      videoRef={videoRef}
      startLabel="Start Camera"
      stopLabel="Stop Camera"
      {...session}
      onStart={session.start}
      onStop={stopCamera}
    >
      Status: {session.active ? "Streaming" : "Stopped"} | Publish: {isPublishing ? "Live" : "Off"}
    </SessionPanel>
  );
}
