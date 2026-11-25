import "./App.css";
import CameraPreview from "./components/CameraPreview";
import StreamViewer from "./components/StreamViewer";

function App() {
  return (
    <div className="App">
      <CameraPreview />
      <StreamViewer />
    </div>
  );
}

export default App;
