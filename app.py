import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import anthropic

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

UPLOAD_FOLDER = "uploads"
DATA_FILE = "inventory.json"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


def load_inventory():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_inventory(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/records", methods=["GET"])
def get_records():
    return jsonify(load_inventory())


@app.route("/api/records", methods=["POST"])
def add_record():
    data = request.json
    inventory = load_inventory()
    record = {
        "id": str(uuid.uuid4()),
        "artist": data.get("artist", ""),
        "album": data.get("album", ""),
        "year": data.get("year", ""),
        "label": data.get("label", ""),
        "format": data.get("format", "LP (33轉)"),
        "genre": data.get("genre", ""),
        "grade": data.get("grade", "B"),
        "condition": data.get("condition", ""),
        "tracks": data.get("tracks", ""),
        "notes": data.get("notes", ""),
        "estimated_value": data.get("estimated_value", ""),
        "image_url": data.get("image_url", ""),
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }
    inventory.insert(0, record)
    save_inventory(inventory)
    return jsonify(record), 201


@app.route("/api/records/<record_id>", methods=["PUT"])
def update_record(record_id):
    data = request.json
    inventory = load_inventory()
    for i, r in enumerate(inventory):
        if r["id"] == record_id:
            inventory[i].update(data)
            inventory[i]["updated_at"] = datetime.now().isoformat()
            save_inventory(inventory)
            return jsonify(inventory[i])
    return jsonify({"error": "Not found"}), 404


@app.route("/api/records/<record_id>", methods=["DELETE"])
def delete_record(record_id):
    inventory = load_inventory()
    inventory = [r for r in inventory if r["id"] != record_id]
    save_inventory(inventory)
    return jsonify({"ok": True})


@app.route("/api/upload", methods=["POST"])
def upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    file = request.files["file"]
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
    filename = str(uuid.uuid4()) + "." + ext
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)
    return jsonify({"url": "/uploads/" + filename})


@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/ai-recognize", methods=["POST"])
def ai_recognize():
    data = request.json
    image_url = data.get("image_url", "")
    filename = image_url.replace("/uploads/", "")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Image not found"}), 404
    with open(filepath, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    ext = filepath.rsplit(".", 1)[-1].lower()
    media_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/" + ext
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": "你是黑膠唱片專家，熟悉Discogs實際成交行情。請用繁體中文分析圖片。估價規則（保守估價寧低勿高）：K-tel/Ronco合輯約USD$1-5；一般流行LP約USD$2-15；知名藝人熱門專輯約USD$5-50；稀有絕版LP約USD$20-150；78轉蟲膠SP依年代約USD$5-80。只回傳JSON不要其他文字，格式：{artist,album,year,label,format,genre,tracks,condition,suggested_grade,estimated_value,notes}，estimated_value格式為USD$X-Y（約NT$X-Y）"}
        ]}]
    )
    text = message.content[0].text
    try:
        clean = text.replace("```json", "").replace("```", "").strip()
        return jsonify(json.loads(clean))
    except:
        return jsonify({})


@app.route("/api/export-csv")
def export_csv():
    import csv, io
    inventory = load_inventory()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["藝人","專輯","年份","廠牌","格式","類型","等級","品相","曲目","估計價值","備註","建立時間"])
    for r in inventory:
        writer.writerow([r.get("artist",""),r.get("album",""),r.get("year",""),r.get("label",""),r.get("format",""),r.get("genre",""),r.get("grade",""),r.get("condition",""),r.get("tracks",""),r.get("estimated_value",""),r.get("notes",""),r.get("created_at","")[:10]])
    return Response("\ufeff"+output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=vinyl_inventory.csv"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
