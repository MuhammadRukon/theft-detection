import { useRef } from "react";
import { useSession } from "../hooks/useSession";
import { startWhep } from "../lib/whep";
import SessionPanel from "./SessionPanel";

export default function StreamViewer() {
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
      onStart={session.start}
      onStop={disconnect}
    >
      Status: {session.active ? "Connected" : "Disconnected"}
    </SessionPanel>
  );
}
