import cv2
import numpy as np

BOX = (0, 255, 0)
ZONE = (255, 160, 0)
HOT = (0, 0, 255)


def render_snapshot(image: np.ndarray, tracks: list, zones: list, alert) -> bytes:
    """JPEG of the frame with person boxes, all zones outlined, the alert's zone highlighted."""
    img = image.copy()
    h, w = img.shape[:2]
    for z in zones:
        pts = np.array([[x * w, y * h] for x, y in z.polygon], np.int32)
        if z.name == alert.zone:
            fill = img.copy()
            cv2.fillPoly(fill, [pts], HOT)
            img = cv2.addWeighted(fill, 0.3, img, 0.7, 0)
        cv2.polylines(img, [pts], True, HOT if z.name == alert.zone else ZONE, 2)
        cv2.putText(img, z.name, tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ZONE, 2)
    for t in tracks:
        p1, p2 = (int(t.x1), int(t.y1)), (int(t.x2), int(t.y2))
        thick = 3 if t.track_id in alert.track_ids else 2
        cv2.rectangle(img, p1, p2, BOX, thick)
        cv2.putText(img, f"#{t.track_id}", (p1[0], max(p1[1] - 6, 12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, BOX, 2)  # fmt: skip
    ok, buf = cv2.imencode(".jpg", img)
    if not ok:
        raise RuntimeError("jpeg encode failed")
    return buf.tobytes()
