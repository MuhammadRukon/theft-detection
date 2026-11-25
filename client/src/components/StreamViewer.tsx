import { useEffect, useRef, useState } from "react";
import { startWhep } from "../lib/whep";

export default function StreamViewer() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopRef = useRef<(() => Promise<void>) | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  async function connect() {
    try {
      setError(null);
      stopRef.current = await startWhep((stream) => {
        if (videoRef.current) videoRef.current.srcObject = stream;
      });
      setIsConnected(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to connect");
    }
  }

  function disconnect() {
    void stopRef.current?.();
    stopRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsConnected(false);
  }

  useEffect(() => {
    return () => {
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
          disabled={isConnected}
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
