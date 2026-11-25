import os
from pathlib import Path

import numpy as np

from app.config import Settings
from app.detection.base import Detection, Detector

PERSON = 0


class YoloDetector(Detector):
    def __init__(self, settings: Settings | None = None):
        s = settings or Settings()
        # Ultralytics resolves a missing .pt by name, downloading it from GitHub. Fail first,
        # before torch is imported, and name the missing file. YOLO_OFFLINE also stops the checks.
        path = Path(s.model_path)
        if not path.is_file():
            raise FileNotFoundError(f"model not found: {path}")
        # Lazy: torch/ultralytics take seconds to import and are absent in some CI.
        # Ultralytics otherwise posts usage analytics to Google; this is a surveillance product.
        os.environ["YOLO_OFFLINE"] = "1"
        import torch
        from ultralytics import YOLO

        torch.set_num_threads(s.torch_threads)
        self._conf = s.detect_conf
        self._model = YOLO(str(path))
        self.detect(np.zeros((640, 640, 3), np.uint8))  # warmup

    def detect(self, image: np.ndarray) -> list[Detection]:
        r = self._model.predict(
            image, classes=[PERSON], conf=self._conf, imgsz=640, device="cpu", verbose=False
        )[0]
        return [
            Detection(int(c), r.names[int(c)], float(p), *map(float, xyxy))
            for xyxy, p, c in zip(
                r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist(), strict=True
            )
        ]
