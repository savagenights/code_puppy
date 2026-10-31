"""5-second live smoke test for the OSC 2 tab-title stopgap (Phase 1).

Run it IN A REAL TERMINAL (Windows Terminal) with the tool's own python,
so it exercises the INSTALLED package:

    C:\\Users\\savag\\AppData\\Roaming\\uv\\tools\\code-puppy\\Scripts\\python.exe ^
        F:\\FORKS\\code_puppy\\scripts\\smoke_tab_title.py

Watch the terminal TAB, not the screen. Expected sequence (~1 second
apart):

    45.9k/262.1k tokens (17%)
    45.9k/262.1k tokens (17%) · Working
    45.9k/262.1k tokens (17%) · Thinking
    45.9k/262.1k tokens (17%) · Idle
    code-puppy            (reset)

If the tab never changes: OSC 2 not honored (rare — WT always does) or
the wrong python (not the code-puppy tool venv). If it changes but the
final reset is missing, atexit did not run (Ctrl-C'd the script).
"""

import time

from code_puppy.messaging import tab_title

CONTEXT = "45.9k/262.1k tokens (17%)"

tab_title.set_context(CONTEXT)
time.sleep(1)
tab_title.set_activity("Working")
time.sleep(1)
tab_title.set_activity("Thinking")
time.sleep(1)
tab_title.set_activity("Idle")
time.sleep(1)
tab_title.reset()
print("smoke done — tab should read 'code-puppy' again")
