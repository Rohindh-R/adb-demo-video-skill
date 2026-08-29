"""Your narration/visual contract. Copy to `claims.py` in the demo directory.

Each entry maps a narration PHRASE to the control(s) that prove it. audit.py matches these
against a token string built from the planned action, so:

    'MoveTo'      matches ('tapid','APP_Editor_MoveTo')
    '2184,197'    matches ('tap',2184,197)
    'settext'     matches any text-entry action
    'DELETE ROW'  matches ('taptext','DELETE ROW')
    'annot:key'   is satisfied by a HIGHLIGHT over `key` instead of an action - for the few
                  things the app will not let adb drive, or that must not be tapped

Write one for every promise the narration makes. If a sentence names a control, this table is
what makes the build fail when the video does not touch it.
"""
CLAIMS = [
 (r'name your staff|give it the name',   ['NameField'],                'the name field'),
 (r'window and priority',                ['Window_Plus','Priority_'],  'window and priority'),
 (r'\brotate\b',                         ['Rotate'],                   'rotate'),
 (r'another zone',                       ['MoveTo'],                   'move to zone'),
 (r'\bcopy\b',                           ['Panel_Copy'],               'the copy button'),
 (r'give it a colour|colour it',          ['Color'],                   'a colour swatch'),
 (r'\btype the words\b',                 ['settext'],                  'typing the name'),
 (r'create a new one with add zone',     ['annot:addzone'],            'Add Zone'),
 (r'reorder them',                       ['annot:reorder'],            'the reorder hint'),
 (r'try to delete it',                   ['DELETE RULE'],              'DELETE RULE'),
 (r'asks you first',                     ['156,58'],                   'Back'),
 (r'drag it into place|position it',     ['place'],                    'a drag'),
]
