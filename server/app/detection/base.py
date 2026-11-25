import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Detection:
    class_id: int
    class_name: str
    conf: float
    # pixel coords of the input image
    x1: float
    y1: float
    x2: float
    y2: float


class Detector(ABC):
    @abstractmethod
    def detect(self, image: np.ndarray) -> list[Detection]:
        """image is bgr24 HxWx3."""


class FakeDetector(Detector):
    """Test double: returns fixed detections, optionally after a delay."""

    def __init__(self, detections: list[Detection] | None = None, delay_s: float = 0.0):
        self.detections = detections or []
        self.delay_s = delay_s
        self.calls = 0

    def detect(self, image: np.ndarray) -> list[Detection]:
        self.calls += 1
        if self.delay_s:
            time.sleep(self.delay_s)
        return list(self.detections)
