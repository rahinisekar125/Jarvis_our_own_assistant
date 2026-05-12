#!/usr/bin/env python
import sys
print("Starting Jarvis voice test...", flush=True)
try:
    from jarvis_assistant.main import main
    sys.argv = ["main", "--mode", "voice"]
    main()
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
