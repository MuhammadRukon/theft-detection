import "./App.css";
import CameraPreview from "./components/CameraPreview";
import StatsPanel from "./components/StatsPanel";
import StreamViewer from "./components/StreamViewer";
import { useCameraEvents } from "./hooks/useCameraEvents";
import { STREAM_PATH } from "./lib/config";

function App() {
  const { stats, detections, connection } = useCameraEvents(STREAM_PATH);
  return (
    <div className="App">
      <CameraPreview />
      <StreamViewer detections={detections} />
      <StatsPanel stats={stats} connection={connection} />
    </div>
  );
}

export default App;
