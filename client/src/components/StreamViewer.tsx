import { useEffect, useRef, useState } from "react";
import { startWhep } from "../lib/whep";

export default function StreamViewer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopRef = useRef<(() => Promise<void>) | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // Bumped by disconnect/unmount so an in-flight connect knows it was cancelled.
  const runRef = useRef(0);
  const [isConnecting, setIsConnecting] = useState(false);

  async function connect() {
    const run = ++runRef.current;
    setIsConnecting(true);
    try {
      setError(null);
      const stop = await startWhep((stream) => {
        if (run === runRef.current && videoRef.current) videoRef.current.srcObject = stream;
      });
      if (run !== runRef.current) {
        void stop();
        return;
      }
      stopRef.current = stop;
      setIsConnected(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect");
    } finally {
      if (run === runRef.current) setIsConnecting(false);
    }
  }

  function disconnect() {
    runRef.current++;
    setIsConnecting(false);
    void stopRef.current?.();
    stopRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsConnected(false);
  }

  useEffect(() => {
    return () => {
      runRef.current++;
      void stopRef.current?.();
    };
  }, []);

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Stream Viewer</h1>

      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="mb-4 w-full max-w-2xl rounded-xl bg-black"
      />

      <div className="flex gap-3">
        <button
          onClick={connect}
          disabled={isConnected || isConnecting}
          className="rounded-lg bg-green-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Connect
        </button>

        <button
          onClick={disconnect}
          disabled={!isConnected}
          className="rounded-lg bg-red-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>

      {error && <p className="mt-3 text-red-500">{error}</p>}

      <p className="mt-3 text-sm text-gray-500">
        Status: {isConnected ? "Connected" : "Disconnected"}
      </p>
    </div>
  );
}
