import os, json, uuid, base64
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import anthropic
import pg8000

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
GOOGLE_VISION_KEY = os.environ.get("GOOGLE_VISION_KEY", "AIzaSyBfIQN6Uvs0wAhezO25OTK-Vx-Uht-yfr8")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

def parse_db_url(url):
    # postgresql://user:pass@host:port/dbname
    url = url.replace("postgresql://", "").replace("postgres://", "")
    userinfo, rest = url.split("@", 1)
    user, password = userinfo.split(":", 1)
    hostport, dbname = rest.split("/", 1)
    if ":" in hostport:
        host, port = hostport.split(":", 1)
        port = int(port)
    else:
        host, port = hostport, 5432
    return user, password, host, port, dbname

def get_db():
    user, password, host, port, dbname = parse_db_url(DATABASE_URL)
    return pg8000.connect(user=user, password=password, host=host, port=port, database=dbname)

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
            format TEXT DEFAULT 'LP (33\u8f49)',
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
    print("DB initialized OK")
except Exception as e:
    print("DB init error:", e)

def row_to_dict(columns, row):
    d = {}
    for i, col in enumerate(columns):
        val = row[i]
        if hasattr(val, 'isoformat'):
            val = val.isoformat()
        d[col] = val
    return d

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/records", methods=["GET"])
def get_records():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id,artist,album,year,label,format,genre,grade,condition,tracks,notes,estimated_value,image_url,created_at,updated_at FROM records ORDER BY created_at DESC")
        cols = ["id","artist","album","year","label","format","genre","grade","condition","tracks","notes","estimated_value","image_url","created_at","updated_at"]
        rows = [row_to_dict(cols, r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify([])

@app.route("/api/records", methods=["POST"])
def add_record():
    data = request.json
    rid = str(uuid.uuid4())
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""INSERT INTO records (id,artist,album,year,label,format,genre,grade,condition,tracks,notes,estimated_value,image_url)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, data.get("artist",""), data.get("album",""), data.get("year",""), data.get("label",""),
             data.get("format","LP (33\u8f49)"), data.get("genre",""), data.get("grade","B"),
             data.get("condition",""), data.get("tracks",""), data.get("notes",""),
             data.get("estimated_value",""), data.get("image_url","")))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"id": rid, **data}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/records/<rid>", methods=["PUT"])
def update_record(rid):
    data = request.json
    try:
        conn = get_db()
        cur = conn.cursor()
        allowed = ["artist","album","year","label","format","genre","grade","condition","tracks","notes","estimated_value","image_url"]
        fields = [f"{k}=%s" for k in allowed if k in data]
        values = [data[k] for k in allowed if k in data]
        fields.append("updated_at=NOW()")
        values.append(rid)
        cur.execute(f"UPDATE records SET {','.join(fields)} WHERE id=%s", values)
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/records/<rid>", methods=["DELETE"])
def delete_record(rid):
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("DELETE FROM records WHERE id=%s", (rid,))
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
    ocr_text = ""
    try:
        vision_url = "https://vision.googleapis.com/v1/images:annotate?key=" + GOOGLE_VISION_KEY
        vision_payload = {"requests": [{"image": {"content": image_data}, "features": [{"type": "TEXT_DETECTION"}, {"type": "LABEL_DETECTION", "maxResults": 10}, {"type": "LOGO_DETECTION", "maxResults": 5}]}]}
        annotations = req.post(vision_url, json=vision_payload, timeout=15).json().get("responses", [{}])[0]
        full_text = annotations.get("fullTextAnnotation", {}).get("text", "")
        labels = [l.get("description","") for l in annotations.get("labelAnnotations", [])]
        logos = [l.get("description","") for l in annotations.get("logoAnnotations", [])]
        ocr_text = "OCR\u6587\u5b57\uff1a" + full_text + "\n\u6a19\u7c3a\uff1a" + ",".join(labels) + "\nLogo\uff1a" + ",".join(logos)
    except Exception as e:
        ocr_text = "OCR\u5931\u6557"
    ext2 = filepath.rsplit(".", 1)[-1].lower()
    media_type = "image/jpeg" if ext2 in ["jpg","jpeg"] else "image/" + ext2
    prompt = ("\u4f60\u662f\u9ed1\u8a60\u5531\u7247\u5c08\u5bb6\uff0c\u719f\u6089Discogs\u5be6\u969b\u6210\u4ea4\u884c\u60c5\u3002\n"
              "Google Vision\u8fa8\u8b58\u7d50\u679c\uff1a\n" + ocr_text + "\n\n"
              "\u8acb\u7528\u7e41\u9ad4\u4e2d\u6587\u5206\u6790\uff0csuggested_grade\u53ea\u80fd\u586bA/B/C\u3002\n"
              "\u4f30\u50f9\uff1aK-tel\u5408\u8f2fUSD$1-5\uff1b\u4e00\u822cLP USD$2-15\uff1b\u77e5\u540d\u85dd\u4ebaPUSSD$5-50\uff1b\u7a00\u6709USD$20-150\uff1b78\u8f49USD$5-80\u3002\n"
              "\u6240\u6709\u6b04\u4f4d\u7e41\u9ad4\u4e2d\u6587\u3002\n"
              '\u53ea\u56de\u50b3JSON: {"artist":"","album":"","year":"","label":"","format":"","genre":"","tracks":"","condition":"","suggested_grade":"","estimated_value":"USD$X-Y\uff08\u7d04NT$X-Y\uff09","notes":""}')
    message = client.messages.create(
        model="claude-haiku-4-5-20251001", max_tokens=1024,
        messages=[{"role":"user","content":[
            {"type":"image","source":{"type":"base64","media_type":media_type,"data":image_data}},
            {"type":"text","text":prompt}
        ]}]
    )
    try:
        return jsonify(json.loads(message.content[0].text.replace("```json","").replace("```","").strip()))
    except:
        return jsonify({})

@app.route("/api/export-csv")
def export_csv():
    import csv, io
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT artist,album,year,label,format,genre,grade,condition,tracks,estimated_value,notes,created_at FROM records ORDER BY created_at DESC")
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except:
        rows = []
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["\u85dd\u4eba","\u5c08\u8f2f","\u5e74\u4efd","\u5ee0\u724c","\u683c\u5f0f","\u985e\u578b","\u7b49\u7d1a","\u54c1\u76f8","\u66f2\u76ee","\u4f30\u8a08\u50f9\u5024","\u5099\u8a3b","\u5efa\u7acb\u6642\u9593"])
    for r in rows:
        writer.writerow([str(v) if v else "" for v in r])
    return Response("\ufeff"+output.getvalue(), mimetype="text/csv", headers={"Content-Disposition":"attachment; filename=vinyl_inventory.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
