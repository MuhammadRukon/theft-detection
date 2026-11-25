import { useEffect, useRef, useState } from "react";

type Stop = () => void | Promise<void>;

// Owns the run-counter cancellation for an async start/stop session.
// startFn(isCurrent, register): `register` hands over a stop early (marks active);
// the returned stop replaces it, and is called right away if the run was cancelled meanwhile.
export function useSession(
  startFn: (isCurrent: () => boolean, register: (stop: Stop) => void) => Promise<Stop>,
  fallbackError: string,
) {
  const runRef = useRef(0); // bumped by stop/unmount so an in-flight start knows it was cancelled
  const stopRef = useRef<Stop | null>(null);
  const [active, setActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function register(stop: Stop) {
    stopRef.current = stop;
    setActive(true);
  }

  async function start() {
    const run = ++runRef.current;
    const isCurrent = () => run === runRef.current;
    setBusy(true);
    try {
      setError(null);
      const stop = await startFn(isCurrent, register);
      if (!isCurrent()) {
        void stop();
        return;
      }
      register(stop);
    } catch (err) {
      setError(err instanceof Error ? err.message : fallbackError);
    } finally {
      if (isCurrent()) setBusy(false);
    }
  }

  function stop() {
    runRef.current++;
    setBusy(false);
    void stopRef.current?.();
    stopRef.current = null;
    setActive(false);
  }

  useEffect(() => {
    const [run, stop] = [runRef, stopRef]; // the refs themselves never change
    return () => {
      run.current++;
      void stop.current?.();
    };
  }, []);

  return { active, busy, error, start, stop };
}
