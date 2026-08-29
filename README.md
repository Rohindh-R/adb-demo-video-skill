# ADB Demo Video Kit

Turn an Android app screen into a narrated, client-ready demo video — and make the narration and
the picture actually agree.

Output: a 1920x1200 mp4 with designed intro/agenda/outro cards, a drawn-on touch pointer,
element highlights, burned-in subtitles, a thumbnail, `TRANSCRIPT.md` and an `.srt`.

The interesting part is not the video. It is the machinery that stops the video from lying:
three automated gates that fail the build when a sentence describes something the picture does
not show.

---

## Install

From this repo, using the [skills.sh](https://skills.sh) CLI — it copies the whole skill
directory, `scripts/` and `templates/` included:

```bash
npx skills add Rohindh-R/adb-demo-video-skill --agent claude-code
```

That writes `.claude/skills/demo-video/` next to your project and records it in
`skills-lock.json`. Or copy it by hand:

```bash
cp -R skills/demo-video ~/.claude/skills/demo-video          # user-level, all projects
cp -R skills/demo-video <your-repo>/.claude/skills/demo-video # project-level, shared in git
```

`SKILL.md` carries the frontmatter, so `/demo-video` picks it up. It also reads as ordinary
documentation if you would rather run the scripts by hand.

**Requirements:** `adb`, `ffmpeg`/`ffprobe`, Python 3.9+ with `Pillow`, `whisper-cpp` for the
sentence alignment, and a TTS key (or bring your own `vo_master.wav`).

---

## Quickstart

```bash
mkdir ~/my-demo && cd ~/my-demo
KIT=.claude/skills/demo-video        # wherever the install put it

cp $KIT/demo.config.example.json     demo.config.json
cp $KIT/templates/segments.example.json  segments.json
cp $KIT/templates/plan.example.py        plan.py
cp $KIT/templates/claims.example.py      claims.py
cp $KIT/templates/highlights.example.py  highlights.py   # optional
cp $KIT/templates/assemble.sh            .

$KIT/scripts/cfg.py                  # sanity-check the config

export DEMO_DIR=$PWD
bash $KIT/scripts/preflight.sh       # patch the dev overlay out, build, prep the device
python3 $KIT/scripts/voice.py        # ONE TTS call -> vo_master.wav + timeline.json
python3 $KIT/scripts/sent.py .       # print the measured sentence spans, then write plan.py
python3 $KIT/scripts/rec.py 4 5 7 8  # record CONSECUTIVELY
./assemble.sh                        # build, gate, deliver, contact sheet
bash $KIT/scripts/restore.sh         # undo everything
```

Five files are yours; the rest is the kit:

| file | what it is |
|---|---|
| `demo.config.json` | package, device size, brand, the testID that guards the screen |
| `segments.json` | the narration, one entry per beat |
| `plan.py` | the beats: every action and **the sentence it must land in** |
| `claims.py` | the contract: which narration phrase each control proves |
| `highlights.py` | optional: which element to ring, during which sentence |

---

## The idea

**Every sentence must be shown while it is spoken.** Everything follows from that.

1. **Measure the narration, don't estimate it.** One TTS call, then align the script against a
   whisper transcript of the audio you actually shipped, at character level. Sentence spans are
   accurate to milliseconds. Pacing, subtitles, SRT, highlights and the gates all read those
   same spans — so they agree by construction.

2. **Anchor every action to a sentence.** In `plan.py` an action is
   `(sentence_index, action)`. That is the contract, in a machine-checkable form.

3. **Pace by trimming, not padding.** Takes come out *longer* than their narration, because
   verifying each step costs real seconds. So the pacer splits a take into movement and still
   stretches, never trims movement, and chooses how long to linger on each still. Extending a
   still is invisible (the frames are identical); freezing mid-motion is what makes a video feel
   like two clips spliced together.

4. **Gate it.** Three checks that a human eye misses:
   - `audit.py` — a claim with no action, an action outside its sentence, an action never
     filmed, an action trimmed out in post
   - `continuity.py` — every beat join, flagging state seams
   - `qc.py` — status bar, keyboard or dev-overlay intrusions in the raw clips

5. **Then look at it.** `sheet.py` gives you one captioned frame per beat. No automated check
   can tell you the beat shows what its narration *means*.

---

## Why the recorder is so defensive

`screenrecord` and the accessibility tree both lie, in specific ways. The version of this that
"worked" shipped a video in which **19 actions across 7 beats were never filmed** — the recorder
stopped while the verification steps were still running, and every per-beat check still passed,
because the actions really did execute. Just after the camera stopped.

So `rec.py` now aborts rather than ships when the last gesture is outside the clip, when the mp4
never finalised, or when a gesture changed nothing on screen. And placement is a closed loop:
drag by the delta needed, measure where the item actually landed, correct, and verify that only
the intended item moved.

`SKILL.md` documents eleven of these traps, each with what it looked like when it bit.

---

## What it will not do

- **Some gestures cannot be injected.** A long-press drag-to-reorder is the clearest example.
  Ring the app's own hint while the narration mentions it, mark that claim `annot:`, and say so
  in the deliverable. Never narrate something the picture does not show.
- **It will not press Save.** If your screen keeps changes local until an explicit save, the demo
  can build freely and discard at the end. Destructive controls are shown and cancelled.
- **The first pass will be partly wrong.** Plan for one re-record; `rec.py --replay` rebuilds
  state without filming so a fix only costs the beats after it.

---

## Layout

```
README.md                    this file
skills/demo-video/
  SKILL.md                   the method, and eleven device traps
  metadata.json              version + abstract for the directory
  demo.config.example.json   copy to your demo dir and edit
  scripts/
  cfg.py                     everything project-specific, in one place
  voice.py  sent.py          narration -> measured sentence spans
  rec.py  motion.py          recording that refuses to lie
  post.py  overlay.py  annots.py  cards.py  stills.py
  audit.py  continuity.py  qc.py  sheet.py       the gates
  deliver.py  tg.py          mp4, srt, transcript, delivery
  grab.py  measure.py  ui.py  uidump.py
    plugins/space.py         optional: canvas placement
    preflight.sh  restore.sh
  templates/                 plan / claims / highlights / segments / assemble.sh
```

Built while producing a 5:15 demo of a table-management screen. Six rebuilds; the lessons are in
`SKILL.md` so you only need one.
