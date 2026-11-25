import "./App.css";
import AlertList from "./components/AlertList";
import CameraPreview from "./components/CameraPreview";
import StatsPanel from "./components/StatsPanel";
import StreamViewer from "./components/StreamViewer";
import { useCameraEvents } from "./hooks/useCameraEvents";
import { STREAM_PATH } from "./lib/config";

function App() {
  const { stats, detections, alerts, zones, connection } = useCameraEvents(STREAM_PATH);
  return (
    <div className="App">
      <CameraPreview />
      <StreamViewer detections={detections} zones={zones} />
      <StatsPanel stats={stats} connection={connection} />
      <AlertList alerts={alerts} />
    </div>
  );
}

export default App;
