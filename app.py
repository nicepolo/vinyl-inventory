import os
import json
import uuid
import base64
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import anthropic
import psycopg2
from psycopg2.extras import RealDictCursor

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
GOOGLE_VISION_KEY = os.environ.get("GOOGLE_VISION_KEY", "")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY,
            artist TEXT DEFAULT '',
            album TEXT DEFAULT '',
            year TEXT DEFAULT '',
            label TEXT DEFAULT '',
            format TEXT DEFAULT 'LP (33轉)',
            genre TEXT DEFAULT '',
            grade TEXT DEFAULT 'B',
            condition TEXT DEFAULT '',
            tracks TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            estimated_value TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

try:
    init_db()
except Exception as e:
    print("DB init error:", e)


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/records", methods=["GET"])
def get_records():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM records ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        result = []
        for r in rows:
            record = dict(r)
            if record.get("created_at"):
                record["created_at"] = record["created_at"].isoformat()
            if record.get("updated_at"):
                record["updated_at"] = record["updated_at"].isoformat()
            result.append(record)
        return jsonify(result)
    except Exception as e:
        return jsonify([])


@app.route("/api/records", methods=["POST"])
def add_record():
    data = request.json
    record_id = str(uuid.uuid4())
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO records (id, artist, album, year, label, format, genre, grade, condition, tracks, notes, estimated_value, image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
        """, (
            record_id,
            data.get("artist", ""),
            data.get("album", ""),
            data.get("year", ""),
            data.get("label", ""),
            data.get("format", "LP (33轉)"),
            data.get("genre", ""),
            data.get("grade", "B"),
            data.get("condition", ""),
            data.get("tracks", ""),
            data.get("notes", ""),
            data.get("estimated_value", ""),
            data.get("image_url", ""),
        ))
        row = dict(cur.fetchone())
        conn.commit()
        cur.close()
        conn.close()
        if row.get("created_at"):
            row["created_at"] = row["created_at"].isoformat()
        if row.get("updated_at"):
            row["updated_at"] = row["updated_at"].isoformat()
        return jsonify(row), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/records/<record_id>", methods=["PUT"])
def update_record(record_id):
    data = request.json
    try:
        conn = get_db()
        cur = conn.cursor()
        fields = []
        values = []
        allowed = ["artist", "album", "year", "label", "format", "genre", "grade", "condition", "tracks", "notes", "estimated_value", "image_url"]
        for k in allowed:
            if k in data:
                fields.append(f"{k} = %s")
                values.append(data[k])
        fields.append("updated_at = NOW()")
        values.append(record_id)
        cur.execute(f"UPDATE records SET {', '.join(fields)} WHERE id = %s RETURNING *", values)
        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        if row:
            row = dict(row)
            if row.get("created_at"):
                row["created_at"] = row["created_at"].isoformat()
            if row.get("updated_at"):
                row["updated_at"] = row["updated_at"].isoformat()
            return jsonify(row)
        return jsonify({"error": "Not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/records/<record_id>", methods=["DELETE"])
def delete_record(record_id):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM records WHERE id = %s", (record_id,))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    import requests as req
    data = request.json
    image_url = data.get("image_url", "")
    filename = image_url.replace("/uploads/", "")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "Image not found"}), 404
    with open(filepath, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")

    # Step 1: Google Vision OCR
    ocr_text = ""
    try:
        vision_url = "https://vision.googleapis.com/v1/images:annotate?key=" + GOOGLE_VISION_KEY
        vision_payload = {
            "requests": [{
                "image": {"content": image_data},
                "features": [
                    {"type": "TEXT_DETECTION", "maxResults": 1},
                    {"type": "LABEL_DETECTION", "maxResults": 10},
                    {"type": "LOGO_DETECTION", "maxResults": 5}
                ]
            }]
        }
        vision_resp = req.post(vision_url, json=vision_payload, timeout=15)
        vision_data = vision_resp.json()
        annotations = vision_data.get("responses", [{}])[0]
        full_text = annotations.get("fullTextAnnotation", {}).get("text", "")
        labels = [l.get("description", "") for l in annotations.get("labelAnnotations", [])]
        logos = [l.get("description", "") for l in annotations.get("logoAnnotations", [])]
        ocr_text = "OCR文字：" + full_text + "\n標籤：" + ", ".join(labels) + "\nLogo：" + ", ".join(logos)
    except Exception as e:
        ocr_text = "OCR失敗：" + str(e)

    # Step 2: Claude analyzes OCR + image
    ext = filepath.rsplit(".", 1)[-1].lower()
    media_type = "image/jpeg" if ext in ["jpg", "jpeg"] else "image/" + ext
    prompt = ("你是黑膠唱片專家，熟悉Discogs實際成交行情。\n"
              "Google Vision已從圖片辨識出以下資訊：\n" + ocr_text + "\n\n"
              "請根據以上OCR資訊和圖片，用繁體中文分析這張黑膠唱片。\n"
              "注意：suggested_grade只能填A、B或C（A=稀有高價值，B=一般流通，C=散貨低價值）。\n"
              "估價規則（保守估價）：K-tel/Ronco合輯約USD$1-5；一般流行LP約USD$2-15；知名藝人約USD$5-50；稀有絕版約USD$20-150；78轉蟲膠約USD$5-80。\n"
              "所有欄位必須用繁體中文。\n"
              'only return JSON: {"artist":"","album":"","year":"","label":"","format":"","genre":"","tracks":"","condition":"","suggested_grade":"","estimated_value":"USD$X-Y（約NT$X-Y）","notes":""}')

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
            {"type": "text", "text": prompt}
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
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT * FROM records ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except:
        rows = []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["藝人", "專輯", "年份", "廠牌", "格式", "類型", "等級", "品相", "曲目", "估計價值", "備註", "建立時間"])
    for r in rows:
        r = dict(r)
        writer.writerow([
            r.get("artist", ""), r.get("album", ""), r.get("year", ""),
            r.get("label", ""), r.get("format", ""), r.get("genre", ""),
            r.get("grade", ""), r.get("condition", ""), r.get("tracks", ""),
            r.get("estimated_value", ""), r.get("notes", ""),
            str(r.get("created_at", ""))[:10]
        ])
    return Response("\ufeff" + output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=vinyl_inventory.csv"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
