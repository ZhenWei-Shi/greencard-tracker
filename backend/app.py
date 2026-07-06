import json
import os

from flask import Flask, jsonify
from flask_cors import CORS

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
ALLOWED_ORIGIN = "https://zhenwei-shi.github.io"

app = Flask(__name__)
CORS(app, origins=[ALLOWED_ORIGIN])


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/index")
def api_index():
    data = load_json("index.json")
    if data is None:
        return jsonify({"error": "index.json not found"}), 404
    return jsonify(data)


@app.get("/api/bulletin/<int:year>/<int:month>")
def api_bulletin(year, month):
    data = load_json(f"bulletin_{year}_{month:02d}.json")
    if data is None:
        return jsonify({"error": "bulletin not found"}), 404
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001)
