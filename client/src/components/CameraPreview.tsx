import { useEffect, useRef, useState } from "react";
import { startWhip } from "../lib/whip";

export default function CameraPreview() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const stopWhipRef = useRef<(() => Promise<void>) | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  // Bumped by stop/unmount so an in-flight startCamera knows it was cancelled.
  const runRef = useRef(0);
  const [isStarting, setIsStarting] = useState(false);

  async function startCamera() {
    const run = ++runRef.current;
    setIsStarting(true);
    try {
      setError(null);

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 15 } },
        audio: false,
      });

      if (run !== runRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
      }

      setIsStreaming(true);

      try {
        const stopWhip = await startWhip(stream);
        if (run !== runRef.current) {
          void stopWhip();
          return;
        }
        stopWhipRef.current = stopWhip;
        setIsPublishing(true);
      } catch (err) {
        setError(
          `Publish failed (is MediaMTX running?): ${err instanceof Error ? err.message : err}`,
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to access camera");
    } finally {
      if (run === runRef.current) setIsStarting(false);
    }
  }

  function stopCamera() {
    runRef.current++;
    setIsStarting(false);
    void stopWhipRef.current?.();
    stopWhipRef.current = null;
    setIsPublishing(false);

    streamRef.current?.getTracks().forEach((track) => track.stop());

    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsStreaming(false);
  }

  useEffect(() => {
    return () => {
      runRef.current++;
      void stopWhipRef.current?.();
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  return (
    <div className="p-6">
      <h1 className="mb-4 text-2xl font-bold">Webcam Preview</h1>

      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="mb-4 w-full max-w-2xl rounded-xl bg-black"
      />

      <div className="flex gap-3">
        <button
          onClick={startCamera}
          disabled={isStreaming || isStarting}
          className="rounded-lg bg-green-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Start Camera
        </button>

        <button
          onClick={stopCamera}
          disabled={!isStreaming}
          className="rounded-lg bg-red-600 px-4 py-2 text-white disabled:opacity-50"
        >
          Stop Camera
        </button>
      </div>

      {error && <p className="mt-3 text-red-500">{error}</p>}

      <p className="mt-3 text-sm text-gray-500">
        Status: {isStreaming ? "Streaming" : "Stopped"} | Publish:{" "}
        {isPublishing ? "Live" : "Off"}
      </p>
    </div>
  );
}
