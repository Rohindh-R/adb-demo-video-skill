---
name: demo-video
description: Produce a narrated, client-ready demo video of an Android app screen — script, single-call TTS voiceover, ADB-driven capture, a drawn-on touch pointer, pacing cut to the audio, burned-in subtitles, transcript and SRT. Use when someone says "make a demo video", "record a demo", "create a walkthrough video", "demo this feature to clients", or "record the app with narration".
---

# Demo video

Record an Android screen, narrate it, and cut the recording to the narration so that **every
sentence is shown while it is spoken**. Output: a 1920x1200 mp4 with designed intro/agenda/outro
cards, a touch pointer, burned-in subtitles, element highlights, a thumbnail, a transcript and
an SRT.

This skill is the distilled result of six full rebuilds of one demo. Most of it is not about
video — it is about the dozen ways an ADB-driven recording lies to you. **Read the gotchas
before writing any code.** Every one of them shipped a broken video first.

## What is yours and what is the kit's

The kit is app-agnostic. Four files in your demo directory are not:

| file | what it is |
|---|---|
| `demo.config.json` | your package, device size, brand, the testID that guards the screen |
| `segments.json` | the narration, one entry per beat |
| `plan.py` | the beats: every action, and **the sentence it must land in** |
| `claims.py` | the contract: which narration phrase each control proves |
| `highlights.py` | optional: which element to ring, and during which sentence |

Copy them from `templates/`. Nothing else needs editing.

## Budget

| Phase | Time | Notes |
|---|---|---|
| 1. Test case + beat plan | 15-25 min | the only genuinely open-ended part |
| 2. Preflight (patch + build) | 5 min | run it while writing the script |
| 3. Voiceover | 3 min | **exactly one** API call |
| 4. Record + gate | 25-30 min | ~100s per beat: every placement verifies itself |
| 5. Assemble | 12 min | mostly PIL + ffmpeg compute |
| 6. Deliver + restore | 5 min | includes a second build |

**Budget for a re-record, and make it cheap.** A pass takes half an hour and something will be
wrong in the first one. Two things keep that affordable: record **consecutively**, so a fix only
costs the beats after it, and use `rec.py --replay` to rebuild app state without filming — so
re-recording beat 16 does not mean re-recording 4 to 15. Check each beat's *content* from a
frame as soon as it lands: a stray item added in one beat went unnoticed for four beats and cost
a whole pass.

---

## Phase 1 — write the test case FIRST, and get it approved

**Do not record anything until a human has approved a written test case.** A content mistake
costs a 30-minute pass; the review costs two minutes. Write, per beat:

- the narration sentence, verbatim
- the action(s), and **which sentence each must land in**
- what the viewer should see as a result

Then state plainly what is *not* covered, and what you cannot do at all (see "Be honest about
what you cannot drive"). Get a yes. Then record.

## Phase 1b — plan the beats

A demo is **cards + app beats + card**. Write the narration first, then choose actions that fit
the seconds available. Rules that survive contact:

- **One idea per beat.** A beat is a sentence or three of narration and the actions that prove
  them.
- **Follow the app's own order.** Walk the toolbox/panel top to bottom. Skipping around and
  coming back reads as disorganised.
- **Count the seconds.** If a sentence names four controls, the beat needs the seconds for four
  controls at ~1s apart. Write narration to match what can be shown, or split the beat.
- **Build something coherent.** Every item added should be configured and placed so the end
  state looks like a real screen someone set up — not a scatter of test objects.
- **Never leave things overlapping or half-done** before moving on. That reads as a bug.

## Phase 2 — preflight

```bash
bash scripts/preflight.sh
```

Patches the dev warning overlay out of the build (React Native: `LogBox.uninstall()`), rebuilds,
and sets device state: `show_touches` off (the pointer is drawn in post), screen stays on, DND
on, **soft keyboard disabled**. Do not undo any of it until the video is finished.

## Phase 3 — voiceover (ONE API call)

```bash
python3 scripts/voice.py            # segments.json -> vo_master.wav + vo_tr.json + timeline.json
```

**Exactly one TTS call for the whole narration.** Two reasons: quota, and pitch/pace drift
audibly between calls even with the same voice. Then `sent.py` aligns the narration against a
whisper transcript of the audio you actually shipped, at character level, and writes the
measured sentence spans into `timeline.json`.

**Everything downstream reads those spans** — pacing, subtitles, SRT, highlights, the audit. So
the burned-in subtitle and the voice agree by construction. Splitting a beat by character count
is out by seconds on a long beat; that is what makes a transcript "not match the video".

## Phase 4 — record, then GATE

Put the app in the first beat's exact starting state, then record **consecutively**:

```bash
python3 scripts/rec.py 4 5 7 8 9 ...      # ALWAYS in order, never one beat out of sequence
python3 scripts/qc.py clips --sheet qc.png
```

`rec.py` fails the beat rather than shipping it when:

* the last gesture is outside the clip (the truncation bug — gotcha 1), or
* `screenrecord` never finalised the mp4, or
* a gesture changed nothing on screen — nearly always a tap that missed, which means every
  later tap in the beat lands somewhere unintended.

Re-record **consecutively from the first affected beat**: coordinates are only valid for the
state the previous beat left behind. An abort mid-beat leaves `screenrecord` running —
`adb shell pkill -INT screenrecord` before retrying.

## Phase 5 — assemble

```bash
./assemble.sh          # copied from templates/
```

**Both gates must pass before you ship.** They catch what a contact sheet cannot: a sentence
describing something the video never does, and an action landing outside its own sentence.

### Pacing: trim the stills, do not freeze frames

Takes come out **longer** than their narration — verification adds real seconds — so pacing is a
trimming problem, not a padding one. `post.py` splits each take into movement and still
stretches, never trims movement, and chooses how long to linger on each still so the beat hits
its narration duration exactly and every gesture lands inside its own sentence.

* **Extending a still is free and invisible** (the frames are identical), so a beat whose
  opening sentence has no action simply dwells there.
* **Nothing is frozen mid-motion.** Weight-distributed freeze-frames are what make a video feel
  like two clips spliced together; there is no equivalent here.
* **Per-sentence dwell budget:** how much dwell a sentence's earlier gestures may take before
  its last one is pushed out of the window. Zeroing it outright fixes a late action but makes
  the next sentence's first action land a second early.
* **The last gesture of a beat gets a longer lead-in**, so whatever it opens is on screen long
  enough to read instead of flashing for twenty frames.
* **A correction is not a claim.** Drags from the placement loop's second iteration onward are
  flagged as machinery, or a beat fails for tidying up after itself.

## The narration/visual contract (verify it, do not assume it)

**Every sentence must be SHOWN while it is SPOKEN.** This is the thing most likely to make an
otherwise clean demo feel wrong. It fails in four ways; `audit.py` checks all four.

1. **A claim with no action.** The narration says "give it the number your staff will call it"
   and nothing ever touches that field. Every action declares its sentence
   (`acts=[(sentence_index, action)]`); `audit.py` fails when a sentence promises a control no
   action anchored to it touches. Keep `claims.py` in step with the narration.
2. **Drift.** The action exists but not while its sentence is spoken. Never distribute padding by
   fixed weights.
3. **A lost action.** Planned, executed, never filmed — see gotcha 1.
4. **An action TRIMMED OUT in post.** The claim check passes and the clip contains it, but the
   pacing solver cut it. A floor picker landed at 11.7s and 12.5s in an 11.3s beat and never
   reached the video — the same feature lost twice by two different mechanisms. Only the DRIFT
   check on the BUILT video catches this, so treat a DRIFT past a beat's own end as **"this
   never shipped"**, not "this is late".

**Diagnose drift by tracing the map, not by staring at the beat.** Printing every gesture's
`src -> out` answers in one step what guessing does not: late, early, trimmed, or a correction.
Three of four "drifts" in one cut turned out to be the placement loop's corrective nudge, with
the real drag perfectly on time.

## Seams and stalls (do not let the joins show)

- **State seams.** The last frame of beat N must be the same app state as the first frame of
  N+1. `continuity.py` diffs every join and flags anything over ~8% (card cuts exempt). This is
  why beats are recorded **consecutively in one session**.
- A join that fails is usually not an editing artifact: check whether the beat's screen had
  finished loading. One beat ended on an empty canvas because the content never drew inside the
  take — `tail=` fixes that, re-recording does not.
- **Motion stalls.** A long freeze stops motion dead and then resumes, which reads as two clips
  spliced even when the state matches perfectly.

## Pointer, subtitles and highlights

- **Draw the pointer in post.** `screenrecord` does not capture `show_touches`. Mimic the system
  indicator — a translucent disc with a ripple, no centre dot, no colour. A bespoke cursor looks
  like a debug overlay.
- **Highlights must use REAL bounds.** Guessing cuts off a row on one card and starts inside the
  wrong one on another. Capture them from the live UI with `grab.py`; refine to the *painted*
  box with `measure.py` when the accessibility node is not the card (nodes reporting 480x132 at
  x=2080 while the card paints 509x105 at x=2027 is normal).
- **Time highlights by sentence, not by timestamp** (`annots.py`), so they cannot drift when the
  pacing changes.
- **Subtitles**: sentence-level, small, bottom-centre, from the measured spans. There is no
  libass in most ffmpeg builds — draw them into the overlay instead of using the `subtitles`
  filter.

## No zooming

Push-ins are more trouble than they are worth. ffmpeg's `zoompan` quantises its pan to whole
pixels, so a slow zoom sits still for four frames then jumps two — visibly jittery — and every
highlight then has to be mapped through the per-frame transform or it slides off its target.
**Highlight instead of zooming.** If you must zoom, resample a float crop box in PIL and export
the transform.

## Acting on the app safely (the expensive lessons)

**Never tap a coordinate you have not just looked up, never trust a gesture you have not
measured, and never continue after a tap that did not do what it should.**

- **Resolve by testID before touching.** Tile grids reflow between sessions; one control moved
  (664,1351) → (1485,1368).
- **A drag must be reproducible before it is trusted.** Six coarse MOVEs put the same target
  180px apart between runs, the second landing on another item. Use many finer steps, a repeated
  final MOVE, and a settle before UP.
- **A finger target is not where the item lands** (grab offset + grid snap); the residual
  measured up to **150px**. Open-loop placement drifts: each item is fitted around the previous
  one's wrong position. Close the loop — drag by the DELTA needed, measure where it landed,
  correct until within tolerance.
- **Never grab an item at a point another item covers.** One item's centre sat 20px under
  another that is above it in z-order, so the drag grabbed the wrong thing and moved it 700px —
  twice, because the retry did it again.
- **Verify that only the intended item moved.** Snapshot every item's centre before a drag,
  compare after, abort if anything else moved. This one invariant would have saved two passes.
- **Measure the canvas limits; do not read them off the painted edge.** An item could not be
  dragged past x≈1852 though the canvas paints to 2000. Positions beyond that were unreachable,
  and the permanent residual read as drag imprecision. Prove it: drag one item at an edge
  repeatedly and watch the axis stop moving while the other converges.
- **Simulate the layout before recording it.** Adding six items to a full screen is a packing
  problem; discovering it does not fit costs a pass — it cost two. Run the intended build order
  of sizes and preferred positions through the same scoring offline first.
- **`sel_item` must confirm the editor actually opened.** A silent miss is the worst failure:
  every following tap lands on whatever is underneath and the run keeps "succeeding".
- **The recorder refuses to run off-screen** (`screen_guard`). One missed tap otherwise sends the
  whole remaining run into another feature while still reporting success.
- **Close the editor before a beat that taps a toolbar** — with a panel open the rail is
  scrolled and destructive buttons slide under harmless coordinates.
- **But never close it BLINDLY.** A close control can sit inside another control's hit box, so a
  blind close on a beat whose predecessor already closed its panel silently ADDS an item. Use
  `closepanel`, which taps only if the close control is actually in the tree.
- **Panel layout changes with state**, and a panel that re-lays itself out springs back to the
  top — so a control that was at y=969 is simply absent. Address panel controls by testID and
  re-scroll after any such change.
- **A partly-visible row reports full bounds and swallows taps.** One fling lands short of the
  stop; a row's reported centre can be inside the clipped region and three taps on it do
  nothing, silently. Use `scrollto`. Not the same failure as a missing node — the node is right
  there, it just cannot be hit.
- **Wait for the screen before the next tap.** A tap fired 1.15s after opening a list landed on
  the *previous* screen's tile and the run carried on happily in the wrong feature.
- **Accessibility dumps go partial** on a busy tree, and some element types drop out at random.
  Retry hard, keep a realistic fallback box, and **confirm from a frame**.
- **Element bounds are SCREEN space, and canvases pan.** A drag toward an edge scrolls
  everything, so coordinates from one beat are not comparable with another and caching a box to
  use as an obstacle later is unsound. Overlap checks must use one live dump at one moment.
- **A rotated item's reported bounds are its UNROTATED box.** Leaving an item turned makes every
  overlap check lie. Rotate there and back within the beat, or not at all.
- **Text fields:** disable the IME and the whole class of problem disappears (see gotcha 8).
  Confirm the field is **empty** before typing, and remember **a placeholder is not a value** —
  an empty field reports its placeholder as `text`, so "is it empty yet?" never becomes true and
  the typing step is skipped forever.
- **Check the text you typed actually FITS.** A name that wrapped to two lines contradicted the
  sentence that said it was on the plan. Read it back off a frame.

## Never press Save

If the screen keeps changes local until an explicit Save, the demo can add, move, restyle and
delete freely, and a `Back → Discard` at the end leaves the real data untouched. **Show** the
Save button and the unsaved-changes prompt; never tap Save. For destructive controls, show the
confirm dialog and press Cancel — and match the button by label, not coordinate. Confirm the
data is unchanged from a **fresh app launch** before calling it done.

## Be honest about what you cannot drive

Some things adb will not do. A long-press drag-to-reorder, for instance: longer holds, a
creeping start and keep-alive events all just scroll the list. Ring the app's own hint while the
narration mentions it, mark that claim `annot:` so the gate accepts a ring for that one promise,
and **say so in the deliverable**. Never quietly narrate something the video does not show, and
never widen a gate to make a real gap pass.

## Sending to Telegram

`sendVideo` must be given `width`, `height` and `duration` explicitly, plus a small JPEG
thumbnail. Without them Telegram records the video as **320x320, duration 0** and the player
squeezes it. Send the caption as plain text — an underscore in something like `TABLE_45` breaks
Markdown parsing and the API rejects the whole request. `scripts/tg.py` does all of this.

## Phase 6 — restore

```bash
bash scripts/restore.sh
```

Reverts the overlay patch and rebuilds (a dev build that hides warnings is a debugging hazard),
and **re-enables the IME**, which is otherwise left disabled for the whole device. Then discard
on-device edits and **verify from a fresh app launch**.

Check the dev overlay is genuinely gone at the START of the next session too: the rebuild at the
end of the previous one puts it straight back, and it takes one screenshot to notice rather than
a whole pass.

---

## The device gotchas

Each of these cost 10-40 minutes to find, and the first four shipped a broken video before they
were understood.

1. **`--time-limit` IS honoured, and that is the trap.** Setting it to the beat's narration
   length, then running actions that verify themselves on device, stops the recording while the
   actions are still running: **19 actions across 7 beats were never filmed**, and validation
   still printed "validated". Use a generous limit, stop explicitly, and assert the last gesture
   is inside the clip.
2. **A killed `screenrecord` leaves an unreadable file.** SIGINT makes it write the moov atom,
   but that takes time proportional to the clip; pulling too early gives you a few hundred KB of
   mdat that ffprobe reports as 0 seconds. Signal, then keep pulling until ffprobe can read a
   duration.
3. **"Frames only on change" is not reliable.** True until something animates on its own: leave
   a text field focused and its caret blinks, producing a frame every 0.5s for the whole take and
   erasing every gap. Never derive timing or pacing from packet timestamps. `motion.py` measures
   the fraction of the frame that changed instead — a caret is 0.00008, a stepper digit 0.0003, a
   panel opening 0.02, a full redraw 0.7. Two thresholds: `TOUCH` for "did anything happen"
   (missed-tap detection) and `MOVE` for "worth showing" (what may be cut).
4. **Video PTS 0 is NOT when `screenrecord` launches.** It starts capturing 0.3-2.5s later. Do
   not infer the offset from the first frame-change (a UI still settling from the previous beat is
   change number one) and do not fit it globally (it picks a confident wrong answer when the
   changes are small — measured 4.3s out). Measure it: screenrecord writes its file header when
   encoding starts, so poll `stat -c %s` and start the clock at the first non-zero size.
5. **`screenrecord` does not capture `show_touches`** at any press duration. Draw the pointer in
   post.
6. **`LogBox.ignoreAllLogs()` does not suppress `console.error`.** Warnings go quiet but a red
   banner, and eventually a full-screen inspector, still appear. Use `LogBox.uninstall()`. It
   needs a rebuild: a debug APK loads a baked bundle, not your dev server.
7. **A drag starting in the bottom ~48px summons the system bars.** Use `motionevent` with a
   hold after DOWN — long enough that the edge gesture is not recognised, while the app's gesture
   handler still claims the drag.
8. **Disable the IME — it fixes two problems at once.** No soft keyboard covering the screen, and
   `input text` becomes deterministic. Six attempts across two sessions failed to rename one
   field (`TERRACEo`, `LTERRACE`, `T`) and it was written off as unfixable: the culprit was the
   IME's composing text, not the key events. With it off, first time, every time. Android
   silently re-enables the default IME, so re-assert it immediately before every text action.
   **Restore it in phase 6.**
9. **The app's own error banners will land on camera.** A network toast covered five seconds of
   two beats. Not something the demo does and not preventable, so detect it by colour and cut
   those source ranges in post — it sits over a static screen, so the join is invisible. A range
   containing a gesture is kept and reported instead.
10. **The app can exit or background itself mid-run** with no crash trace. Check the foreground
    package before trusting a state, and be ready to relaunch and replay.
11. **Some gestures simply cannot be injected.** See "Be honest about what you cannot drive".

## The scripts

| script | does |
|---|---|
| `cfg.py` | reads `demo.config.json`; everything project-specific in one place |
| `voice.py` | one TTS call, then whisper transcription |
| `sent.py` | measured sentence spans; writes `timeline.json` |
| `rec.py` | records a beat, times its gestures, aborts on truncation or a missed tap |
| `motion.py` | where a take actually moves, measured from pixels |
| `post.py` | cuts dead time, paces so each action lands inside its sentence |
| `annots.py` | builds `annot.json` from sentence spans |
| `grab.py` / `measure.py` | real element bounds for highlights |
| `overlay.py` | pointer, ripple, chip, highlights, burned-in subtitles |
| `cards.py` / `stills.py` | intro/agenda/outro cards and still beats |
| `audit.py` | the narration/visual contract gate |
| `continuity.py` | the seam gate |
| `deliver.py` | concat, mux, `.srt`, `TRANSCRIPT.md` |
| `sheet.py` | contact sheet, one captioned frame per beat, for the human pass |
| `qc.py` | status bar / keyboard / dev-overlay intrusion check |
| `tg.py` | send to Telegram with correct dimensions |
| `plugins/space.py` | optional: free-spot search for apps that drag items on a canvas |
| `preflight.sh` / `restore.sh` | device and build setup, and teardown |

## Requirements

- macOS or Linux, `adb` on PATH, a connected device or emulator
- `ffmpeg` + `ffprobe`
- Python 3.9+ with `Pillow`
- `whisper-cpp` (or any transcriber writing the same JSON) for the sentence alignment
- a TTS API key for the voiceover, or supply your own `vo_master.wav`
