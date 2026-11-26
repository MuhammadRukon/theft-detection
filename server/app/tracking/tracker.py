from dataclasses import dataclass

import numpy as np
import supervision as sv
from trackers import ByteTrackTracker

from app.detection.base import Detection


@dataclass(frozen=True)
class TrackedDetection:
    track_id: int
    class_id: int
    class_name: str
    conf: float
    # pixel coords of the input image
    x1: float
    y1: float
    x2: float
    y2: float


class PersonTracker:
    def __init__(self, frame_rate: float, min_conf: float = 0.4):
        # frame_rate is the inference rate, not the camera's. lost_track_buffer is counted in 30 fps
        # frames whatever the rate: 60 = 2 s (10 frames @5fps), matching the dwell rule's grace.
        # Library defaults (0.7 / 0.6) would never start a track for persons at detect_conf 0.4.
        self._tracker = ByteTrackTracker(
            lost_track_buffer=60,
            frame_rate=frame_rate,
            track_activation_threshold=min_conf,
            high_conf_det_threshold=min_conf,
        )

    def update(self, detections: list[Detection]) -> list[TrackedDetection]:
        """Advance the tracker. New tracks are only reported after 2 consecutive matches."""
        sv_dets = sv.Detections(
            xyxy=np.array([[d.x1, d.y1, d.x2, d.y2] for d in detections], dtype=float).reshape(
                -1, 4
            ),
            confidence=np.array([d.conf for d in detections], dtype=float),
            class_id=np.array([d.class_id for d in detections], dtype=int),
            data={"class_name": np.array([d.class_name for d in detections], dtype=object)},
        )
        out = self._tracker.update(sv_dets)
        if out.tracker_id is None:
            return []
        return [
            TrackedDetection(int(tid), int(cid), str(name), float(conf), *map(float, box))
            for tid, cid, name, conf, box in zip(
                out.tracker_id,
                out.class_id,
                out.data["class_name"],
                out.confidence,
                out.xyxy,
                strict=True,
            )
            if tid != -1
        ]
