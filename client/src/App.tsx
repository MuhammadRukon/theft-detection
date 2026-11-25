import "./App.css";
import CameraPreview from "./components/CameraPreview";
import StatsPanel from "./components/StatsPanel";
import StreamViewer from "./components/StreamViewer";

function App() {
  return (
    <div className="App">
      <CameraPreview />
      <StreamViewer />
      <StatsPanel />
    </div>
  );
}

export default App;
