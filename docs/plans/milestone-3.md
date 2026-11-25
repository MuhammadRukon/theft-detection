# Milestone 3 (DRAFT): threat and carried objects, tied to people

Status: **draft, NOT approved.** An earlier "yes" was given by mistake and was withdrawn; the plan is being grilled with the user and must be explicitly approved before any code. Execution would start only after Milestone 2 is finished and committed. See [architecture](../architecture.md) build order step 2 and [milestone 2](milestone-2.md).

**Goal:** detect objects that matter for theft and threat (knife, baseball bat, backpack, handbag, suitcase) with the same pretrained YOLO11 nano, track them, and say which person each one is with. Show it on the dashboard. No alerts, risk scores, or behavior rules yet (that is Milestone 4).

**Done when:** on the live webcam, holding a backpack, handbag or bottle-sized stand-in shows a labelled box on the object, and the SSE event says which person track it is associated with; person tracking and ingest FPS are no worse than Milestone 2; inference time and the added CPU cost are measured and reported.

## Proposed decisions (to confirm)

1. **Classes (COCO, same model, no training):** person (0), backpack (24), handbag (26), suitcase (28), knife (43), baseball bat (34). Configurable list, not hard-coded. **Honest limit:** the nano model is weak on small or partly hidden objects (knives especially, and a knife held in a hand at 720p is often missed). We measure and report real recall on our own footage instead of assuming it. Guns, machetes, masks and helmets are not in COCO and stay for a later custom-model milestone.
2. **One model pass, per-class confidence.** Keep a single inference pass over all listed classes. Add per-class confidence floors (objects usually need a lower floor than people) in `Settings`.
3. **Tracking:** keep the person tracker as is. Run a second `PersonTracker`-style tracker for objects (generalize the class to a plain `Tracker`), so object IDs do not mix with person IDs. Objects get IDs only so the overlay and association stay stable across frames.
4. **Association (object to person):** simple geometry, no learning. An object belongs to the person whose box contains the object's centre (or has the largest overlap with it), with a small margin around the person box. Smoothed over a few frames so a bag does not flip owners on one noisy frame. Output a nullable `holder_id` on each object track.
5. **Events:** `detections` tracks keep their shape and gain `holder_id` (nullable). The `class` field already carries the class name. No new event type.
6. **Overlay:** objects drawn in a different colour from people, label `bag #7 (person #2)`.
7. **Limits stay honest:** no alerts, no "suspicious" labels, no risk score in this milestone.

## Draft phases

1. **Detector:** multi-class `YoloDetector` driven by `Settings` (class list, per-class conf); fake-detector tests for the filter logic; measure ms/frame vs person-only on this CPU.
2. **Tracker generalization:** `PersonTracker` becomes a small generic `Tracker`; pipeline runs one instance for people and one for objects; tests for independent ID spaces.
3. **Association:** pure function (people tracks + object tracks -> holder_id) with temporal smoothing; unit tests for containment, overlap, ties, flicker.
4. **Events and dashboard:** `holder_id` in schema and TS types; overlay colours and labels; stats panel unchanged.
5. **Real check and review:** webcam test with a backpack or bag you own (and a harmless knife-like prop only if you choose); report measured recall and false positives, ingest FPS and latency; cross-validation pass.

## Open questions for the user

- Q1: Is the class list above right, or should it be limited (e.g. bags only for now)?
- Q2: Is a harmless prop test (a bag, a bottle) enough for the real-webcam check, or do you have footage to use? Real surveillance-style footage would give more honest numbers than your desk webcam.
- Q3: Should the association be shown to the user as "carried by" only, or also as "left alone" (an object with no holder for N seconds)? The latter is a theft/abandoned-bag signal and would bring in the first time-based rule, so I recommend deferring it to Milestone 4.
- Q4: Keep the `Milestone 3` name for this, or do you prefer the track-only behavior rules (group rushing a door, loitering, running) first, since they need no new model?

## Out of scope

Guns, machetes, masks, helmets, custom training, alerts, risk scores, evidence storage, ONNX/GPU, multi-camera, auth, database.
