"""Your beat plan. Copy to `plan.py` in the demo directory and rewrite for your screen.

Every action declares the narration SENTENCE it must land in:

    acts = [ (sentence_index, action), ... ]

The index is into that beat's sentences as MEASURED by sent.py from the shipped audio - not a
guess. post.py solves its pacing so each action's visible reaction falls inside that sentence's
span, and audit.py fails the build if it does not.

Sentence indices are zero-based and printed by:

    python3 scripts/sent.py .

Optional per-beat keys:
    rec=<seconds>     advisory only; the recorder stops when the actions are done
    tail=<seconds>    frames kept AFTER the last action. Raise it when the beat ends on a
                      slow transition - a screen that takes 6s to draw needs tail=12 or the
                      beat ends on a half-drawn screen and the next join jumps.
    guard=False       skip the screen-guard check (only for a beat that navigates INTO the
                      screen, where the guard is not there yet)
    A third element on any action is its own pause, in seconds, before it fires. Give it to
    anything that follows a slow screen: a tap fired into a loading list lands on whatever
    was underneath.

ACTIONS
-------
  ('tap', x, y)                          a raw coordinate. Use sparingly.
  ('tapid', testid[, (fx,fy)])           resolve a testID, then tap it. Prefer this always.
  ('ntapid', testid, n)                  n taps on one control as ONE visible burst
  ('taptext', 'Label')                   match a row by its visible label (rows often have
                                         no testID)
  ('scrollto', testid, max_y[, tries])   scroll a panel until the target is properly inside
                                         the viewport. A partly-visible row reports full
                                         bounds and silently swallows taps.
  ('sel_item', pat, expect[, fx, fy])    tap an item AND confirm its editor opened. Aborts
                                         rather than tap blind.
  ('settext', testid, 'TEXT')            focus, empty, type, verify. Handles placeholders.
  ('closepanel',)                        close the editor ONLY if one is open
  ('swipe', x1,y1,x2,y2, ms)             a scroll
  ('mdrag', x1,y1,x2,y2[, steps])        a real drag (motionevent, with a hold before moving)
  ('key', keycode)                       e.g. 4 for BACK
  ('place', pat, px,py[, fx,fy])         canvas plugin: drag an item to a free spot near
                                         (px,py), measuring and correcting until it lands
  ('place_new', prefix, px,py[, skip])   canvas plugin: same, for an item whose id you cannot
                                         know in advance (a copy is auto-numbered)
"""

TOOL = {                      # your screen's fixed controls, measured once
    'thing':  (2320, 207),
    'other':  (2320, 339),
}

PLANS = {

 # A beat that navigates INTO the screen: guard off, long tail so the destination is fully
 # drawn before the beat ends.
 4: dict(guard=False, tail=14.0, desc="Settings > Feature", acts=[
      (0, ('tapid', 'APP_Settings_MyFeature')),
      (1, ('taptext', 'My Feature'), 3.2),
   ]),

 # A beat whose first sentence has no action: it simply dwells on the screen while the
 # narrator describes it. Extending a still is free and invisible - no recording tricks.
 5: dict(desc="The screen, and switching context", acts=[
      (1, ('tapid', 'APP_ContextSelector')),
      (2, ('tapid', 'APP_ContextOption_1'), 6.5),   # slow redraw: give it its own pause
      (2, ('tapid', 'APP_ContextSelector')),
      (2, ('tapid', 'APP_ContextOption_0')),
   ]),

 # Add / configure / place. Note how each action sits in the sentence that promises it.
 7: dict(desc="Add a thing, name it, size it", acts=[
      (0, ('tap', *TOOL['thing'])),
      (1, ('place', 'Item_THING', 1700, 1120, 156, 1564)),
      (2, ('sel_item', 'Item_THING', 'APP_Editor_NameField')),
      (2, ('settext', 'APP_Editor_NameField', '21')),
      (2, ('ntapid', 'APP_Editor_Height_Plus', 2)),
      (2, ('ntapid', 'APP_Editor_Width_Plus', 2)),
   ]),

 # Controls at a panel's bottom edge must be scrolled into view first, and a panel that
 # re-lays itself out springs back to the top - so scroll again after any such change.
 9: dict(desc="Shape, rotate, move", acts=[
      (0, ('swipe', 2320, 1200, 2320, 400, 400)),
      (0, ('tapid', 'APP_Editor_Shape_B')),
      (0, ('tapid', 'APP_Editor_Shape_A')),
      (1, ('scrollto', 'APP_Editor_MoveTo', 1250)),
      (1, ('ntapid', 'APP_Editor_RotateRight', 2)),
      (1, ('ntapid', 'APP_Editor_RotateLeft', 2)),    # rotate BACK: see the note below
      (1, ('tapid', 'APP_Editor_MoveTo')),
      (1, ('tapid', 'APP_MoveTo_Close')),
   ]),

 # A destructive control the demo must SHOW but never confirm. Match it by label, not by
 # coordinate: the one thing worse than missing a delete button is hitting something near it.
19: dict(desc="The live-state guard", acts=[
      (0, ('closepanel',)),
      (1, ('sel_item', 'Item_THING_42', 'APP_Editor_NameField')),
      (2, ('taptext', 'DELETE THING')),
   ]),
}

# NOTE on rotation: many canvases report a rotated item's UNROTATED bounding box. Leaving an
# item turned makes every overlap check lie. Rotate there and back within the beat, or do not
# rotate at all.
