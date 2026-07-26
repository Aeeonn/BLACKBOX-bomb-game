
"""Spawn a room and open every role in its own tab.  python tools/devroom.py"""
import json
import sys
import urllib.request
import webbrowser

HOST = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
ROLES = ["hands", "eyes", "book", "scope"]

req = urllib.request.Request(HOST + "/api/room", method="POST")
code = json.load(urllib.request.urlopen(req))["room"]
print("room", code)
for r in ROLES:
    url = "%s/%s.html?room=%s&role=%s" % (HOST, r, code, r)
    print(" ", url)
    webbrowser.open_new_tab(url)
