// Content rect of a video drawn with object-fit: contain inside an element box (CSS px).
// Returns the whole box until the video size is known.
export function containRect(vw: number, vh: number, ew: number, eh: number) {
  if (!vw || !vh) return { x: 0, y: 0, w: ew, h: eh };
  const scale = Math.min(ew / vw, eh / vh);
  const w = vw * scale;
  const h = vh * scale;
  return { x: (ew - w) / 2, y: (eh - h) / 2, w, h };
}
