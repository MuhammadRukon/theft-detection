// Shared by WHIP and WHEP: offer -> wait for ICE -> POST SDP -> apply answer.
// Closes pc itself on failure. Returns stop(), which closes pc and DELETEs the session.
export async function negotiate(pc: RTCPeerConnection, url: string) {
  try {
    await pc.setLocalDescription(await pc.createOffer());
    if (pc.iceGatheringState !== "complete") {
      await new Promise<void>((resolve) => {
        const done = () => {
          clearTimeout(timer);
          pc.removeEventListener("icegatheringstatechange", check);
          resolve();
        };
        const check = () => pc.iceGatheringState === "complete" && done();
        pc.addEventListener("icegatheringstatechange", check);
        const timer = setTimeout(done, 2000); // shortcut: send what we have after 2s, fine on localhost
      });
    }

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription!.sdp,
    });
    if (!res.ok) throw new Error(`${url} responded ${res.status}`);
    const session = new URL(res.headers.get("Location") ?? "", url).href;
    await pc.setRemoteDescription({ type: "answer", sdp: await res.text() });

    return async () => {
      pc.close();
      await fetch(session, { method: "DELETE" }).catch(() => {});
    };
  } catch (err) {
    pc.close();
    throw err;
  }
}
