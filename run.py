"""Start the app:  python run.py   then open http://127.0.0.1:5000

Debug mode (auto-reload + in-browser debugger) is off by default. It's unreliable on Windows
and should never be left on where others can reach it. Turn it on while developing with:
    set FLASK_DEBUG=1      (macOS/Linux: export FLASK_DEBUG=1)
"""
import os

from tracker import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
