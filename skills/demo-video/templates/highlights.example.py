"""Which element to ring, and when. Copy to `highlights.py` in the demo directory.

A highlight names the SENTENCE it belongs to, not a timestamp, so it cannot drift away from the
words it explains when the pacing changes.

    ANN = { beat: [ (bounds_key, sentence_index, (from,to) fraction of that span or None) ] }

`sentence_index` may be a TUPLE (i,j) meaning "sentence i's start to sentence j's end" - use it
when a one-word sentence is too brief for a ring to read.

`bounds_key` refers to an entry in bounds.json, captured from the live UI with:

    python3 scripts/grab.py save=APP_Save addzone=APP_AddZoneButton
    python3 scripts/grab.py --pad-by 10 builtins=Available,Seated,Cleaning

A ring is also the honest way to cover something the app will not let adb drive, or that must
NOT be tapped because it would create real data. audit.py accepts a ring as proof for exactly
the claims you mark `annot:` in claims.py, and nothing else.
"""
ANN = {
 3:  [('features_card', 0, None), ('settings_card', 1, None)],
 5:  [('addzone', 2, (0.52, 1.0))],
 6:  [('tool_RULE', 1, (0.00, 0.46)), ('tool_GROUP', 1, (0.52, 1.0)),
      ('tool_STATION', (2, 3), (0.00, 0.46)), ('tool_ZONE', (2, 3), (0.52, 1.0))],
 17: [('builtins', 1, None), ('reorder', 2, (0.50, 0.78))],
 20: [('save', 0, None), ('unsaved', 2, None)],
}
