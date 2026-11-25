import os

import numpy as np

from app.config import Settings
from app.detection.base import Detection, Detector

PERSON = 0


class YoloDetector(Detector):
    def __init__(self, settings: Settings | None = None):
        # Lazy: torch/ultralytics take seconds to import and are absent in some CI.
        # Ultralytics otherwise posts usage analytics to Google; this is a surveillance product.
        os.environ.setdefault("YOLO_OFFLINE", "1")
        import torch
        from ultralytics import YOLO

        s = settings or Settings()
        torch.set_num_threads(s.torch_threads)
        self._conf = s.detect_conf
        self._model = YOLO(s.model_path)
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
