"""RF Verification App - Flask entry point."""
import os
import webbrowser
from threading import Timer
from flask import Flask, jsonify, render_template, request
from core import config_store, paths
from core.logger import live_tail
from core.session import SESSION, SessionError
app = Flask(__name__,
            template_folder=os.path.join(paths.resource_dir(), "templates"),
            static_folder=os.path.join(paths.resource_dir(), "static"))
HOST = "127.0.0.1"
PORT = 5000
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/settings")
def settings():
    return render_template("settings.html")
@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(config_store.load_config())
@app.route("/api/config", methods=["POST"])
def post_config():
    config_store.save_config(request.get_json(force=True))
    return jsonify({"ok": True})
@app.route("/api/units", methods=["GET"])
def get_units():
    return jsonify({"units": config_store.list_units()})
@app.route("/api/freqlist/<unit>", methods=["GET"])
def get_freqlist(unit):
    try:
        freqs = config_store.load_freq_list(unit)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
    path = os.path.join(config_store.FREQ_LIST_DIR, unit + ".txt")
    text = ""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    return jsonify({"unit": unit, "freqs": freqs, "text": text})
@app.route("/api/freqlist/<unit>", methods=["POST"])
def post_freqlist(unit):
    config_store.save_freq_list(unit, request.get_json(force=True).get("text", ""))
    return jsonify({"ok": True})
@app.route("/api/run/start", methods=["POST"])
def run_start():
    body = request.get_json(force=True)
    try:
        info = SESSION.start(body.get("check"), body.get("unit"), body.get("mode", "manual"),
                             body.get("freqs", []), body.get("params", {}))
        return jsonify(info)
    except (SessionError, KeyError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/measure", methods=["POST"])
def run_measure():
    body = request.get_json(force=True) or {}
    try:
        return jsonify(SESSION.measure(body.get("manual", {})))
    except SessionError as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/next", methods=["POST"])
def run_next():
    try:
        return jsonify(SESSION.next())
    except SessionError as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/skip", methods=["POST"])
def run_skip():
    try:
        return jsonify(SESSION.skip())
    except SessionError as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/stop", methods=["POST"])
def run_stop():
    try:
        return jsonify(SESSION.stop())
    except SessionError as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/confirm", methods=["POST"])
def run_confirm():
    try:
        return jsonify(SESSION.confirm())
    except SessionError as exc:
        return jsonify({"error": str(exc)}), 400
@app.route("/api/run/status", methods=["GET"])
def run_status():
    if SESSION.check is None:
        return jsonify({"active": SESSION.is_active(), "idle": True})
    return jsonify(SESSION.status())
@app.route("/api/run/logs", methods=["GET"])
def run_logs():
    since = request.args.get("since", default=0, type=int)
    return jsonify(live_tail(since))
def _open_browser():
    webbrowser.open("http://%s:%d" % (HOST, PORT))
if __name__ == "__main__":
    Timer(1.0, _open_browser).start()
    app.run(host=HOST, port=PORT, threaded=True, debug=False)
