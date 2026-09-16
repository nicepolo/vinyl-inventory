import os, json, uuid, base64, time, hmac, hashlib
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, Response, redirect
from flask_cors import CORS
import pg8000
import requests

app = Flask(__name__, static_folder="static", static_url_path="/static")
CORS(app)

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-2.5-flash")
GOOGLE_VISION_KEY = os.environ.get("GOOGLE_VISION_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
AI_TIMEOUT_SECONDS = float(os.environ.get("AI_TIMEOUT_SECONDS", "25"))
UNIFIED_SSO_SECRET = os.environ.get("UNIFIED_SSO_SECRET", "")
ADMIN_PORTAL_URL = os.environ.get("ADMIN_PORTAL_URL", "https://antique-register-production.up.railway.app").rstrip("/")

TRANSIENT_STATUSES = {408, 409, 425, 429, 500, 502, 503, 504}

class ProviderError(Exception):
    def __init__(self, message, status=503, transient=False):
        super().__init__(message)
        self.status = status
        self.transient = transient

def friendly_provider_error(provider, status, body=""):
    text = (body or "").lower()
    if status == 400 and any(word in text for word in ("credit", "balance", "billing")):
        return ProviderError(f"{provider} 額度不足，已嘗試其他可用辨識方式", 503)
    if status in (401, 403):
        return ProviderError(f"{provider} 金鑰無效或沒有權限，請由管理員檢查 Railway 設定", 503)
    if status == 429:
        return ProviderError(f"{provider} 目前請求過多，請稍後再試", 503, True)
    if status in TRANSIENT_STATUSES:
        return ProviderError(f"{provider} 暫時無法回應，請稍後再試", 503, True)
    return ProviderError(f"{provider} 辨識服務回應異常（HTTP {status}）", 503)

def post_with_retry(url, **kwargs):
    last_error = None
    for attempt in range(2):
        try:
            response = requests.post(url, timeout=AI_TIMEOUT_SECONDS, **kwargs)
            if response.status_code not in TRANSIENT_STATUSES or attempt == 1:
                return response
            last_error = friendly_provider_error("AI", response.status_code, response.text[:500])
        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = ProviderError("AI 辨識服務連線逾時，請稍後再試", 503, True)
            if attempt == 1:
                raise last_error from exc
        time.sleep(0.4 * (attempt + 1))
    raise last_error or ProviderError("AI 辨識服務暫時無法使用", 503)

def parse_json_object(text):
    cleaned = (text or "").replace("```json", "").replace("```", "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ProviderError("AI 回傳格式不正確，請重試", 502)
    return json.loads(cleaned[start:end + 1])

def recognize_with_gemini(image_data, media_type, prompt):
    last_error = None
    models = list(dict.fromkeys(model for model in (GEMINI_MODEL, GEMINI_FALLBACK_MODEL) if model))
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        response = post_with_retry(url, json={
            "contents": [{"parts": [
                {"inline_data": {"mime_type": media_type, "data": image_data}},
                {"text": prompt}
            ]}],
            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 1600}
        })
        if not response.ok:
            last_error = friendly_provider_error(f"Gemini {model}", response.status_code, response.text[:500])
            if last_error.transient and model != models[-1]:
                continue
            raise last_error
        payload = response.json()
        text = "".join(part.get("text", "") for part in payload.get("candidates", [{}])[0].get("content", {}).get("parts", []))
        if not text:
            raise ProviderError(f"Gemini {model} 沒有回傳可用內容，可能被安全過濾擋下", 502)
        return parse_json_object(text), model
    raise last_error or ProviderError("Gemini 暫時無法使用", 503)

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
            created_by TEXT DEFAULT '',
            photo_uploaded_by TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS created_by TEXT DEFAULT ''")
    cur.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS photo_uploaded_by TEXT DEFAULT ''")
    cur.execute("UPDATE records SET created_by='Polo' WHERE created_by IS NULL OR created_by=''")
    cur.execute("UPDATE records SET photo_uploaded_by='Polo' WHERE image_url<>'' AND (photo_uploaded_by IS NULL OR photo_uploaded_by='')")
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

def decode_token(token, audience):
    try:
        payload, signature = token.split(".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new(UNIFIED_SSO_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
        ).decode().rstrip("=")
        if not UNIFIED_SSO_SECRET or not hmac.compare_digest(signature, expected):
            return None
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode())
        if data.get("aud") != audience or int(data.get("exp", 0)) < int(time.time()):
            return None
        return data
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

def issue_session(name):
    data = {"name": name, "aud": "vinyl-session", "exp": int(time.time()) + 30 * 24 * 3600}
    payload = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(UNIFIED_SSO_SECRET.encode(), payload.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{payload}.{signature}"

@app.before_request
def require_unified_login():
    if request.method == "OPTIONS" or request.path in ("/sso", "/healthz"):
        return None
    session = decode_token(request.cookies.get("vinyl_session", ""), "vinyl-session")
    if session:
        request.user_name = session.get("name", "管理員")
        return None
    if request.path.startswith("/api/") or request.path.startswith("/uploads/"):
        return jsonify({"error": "請從萬鴻統一管理入口登入"}), 401
    return redirect(ADMIN_PORTAL_URL)

@app.route("/sso")
def sso_login():
    data = decode_token(request.args.get("token", ""), "vinyl-sso")
    if not data:
        return redirect(ADMIN_PORTAL_URL)
    response = redirect("/")
    response.set_cookie(
        "vinyl_session", issue_session(data.get("name", "管理員")),
        max_age=30 * 24 * 3600, httponly=True, secure=True, samesite="Lax"
    )
    return response

@app.route("/logout")
def logout():
    response = redirect(ADMIN_PORTAL_URL)
    response.delete_cookie("vinyl_session")
    return response

@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/records", methods=["GET"])
def get_records():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT id,artist,album,year,label,format,genre,grade,condition,tracks,notes,estimated_value,image_url,created_by,photo_uploaded_by,created_at,updated_at FROM records ORDER BY created_at DESC")
        cols = ["id","artist","album","year","label","format","genre","grade","condition","tracks","notes","estimated_value","image_url","created_by","photo_uploaded_by","created_at","updated_at"]
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
        cur.execute("""INSERT INTO records (id,artist,album,year,label,format,genre,grade,condition,tracks,notes,estimated_value,image_url,created_by,photo_uploaded_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (rid, data.get("artist",""), data.get("album",""), data.get("year",""), data.get("label",""),
             data.get("format","LP (33\u8f49)"), data.get("genre",""), data.get("grade","B"),
             data.get("condition",""), data.get("tracks",""), data.get("notes",""),
             data.get("estimated_value",""), data.get("image_url",""), request.user_name,
             request.user_name if data.get("image_url","") else ""))
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
        if data.get("image_url"):
            fields.append("photo_uploaded_by=%s")
            values.append(request.user_name)
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
    data = request.get_json(silent=True) or {}
    image_url = data.get("image_url", "")
    inline_image = data.get("image_data", "")
    media_type = "image/jpeg"
    if inline_image:
        if "," in inline_image:
            header, image_data = inline_image.split(",", 1)
            if header.startswith("data:image/"):
                media_type = header[5:].split(";", 1)[0]
        else:
            image_data = inline_image
        if not image_data or len(image_data) > 18_000_000:
            return jsonify({"error": "照片格式不正確或檔案過大"}), 400
    else:
        filename = os.path.basename(image_url.replace("/uploads/", ""))
        if not image_url.startswith("/uploads/") or not filename:
            return jsonify({"error": "圖片路徑無效"}), 400
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "找不到要辨識的圖片"}), 404
        with open(filepath, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        ext2 = filepath.rsplit(".", 1)[-1].lower()
        media_type = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif"}.get(ext2, "image/jpeg")
    full_text, labels, logos = "", [], []
    vision_error = None
    if GOOGLE_VISION_KEY:
        try:
            vision_url = "https://vision.googleapis.com/v1/images:annotate?key=" + GOOGLE_VISION_KEY
            vision_payload = {"requests": [{"image": {"content": image_data}, "features": [{"type": "TEXT_DETECTION"}, {"type": "LABEL_DETECTION", "maxResults": 10}, {"type": "LOGO_DETECTION", "maxResults": 5}]}]}
            response = post_with_retry(vision_url, json=vision_payload)
            if not response.ok:
                raise friendly_provider_error("Google Vision", response.status_code, response.text[:500])
            annotations = response.json().get("responses", [{}])[0]
            if annotations.get("error"):
                err = annotations["error"]
                raise friendly_provider_error("Google Vision", int(err.get("code", 500)), str(err.get("message", "")))
            full_text = annotations.get("fullTextAnnotation", {}).get("text", "")
            labels = [l.get("description", "") for l in annotations.get("labelAnnotations", []) if l.get("description")]
            logos = [l.get("description", "") for l in annotations.get("logoAnnotations", []) if l.get("description")]
        except ProviderError as exc:
            vision_error = exc
    else:
        vision_error = ProviderError("尚未設定 Google Vision", 503)
    ocr_text = "OCR文字：" + full_text[:4000] + "\n標籤：" + ",".join(labels) + "\nLogo：" + ",".join(logos)
    prompt = ("你是黑膠唱片入庫助理。根據封面與下列 Google Vision OCR，只填寫照片中可合理辨識的資料；不確定就留空，不可捏造版本、年份、曲目、品相或價格。\n"
              + ocr_text + "\n\n"
              "請用繁體中文，只回傳 JSON。suggested_grade 只能是 A、B、C；單張封面無法確認唱片實際品相時用 B，並在 low_confidence 列出 condition 與 suggested_grade。estimated_value 一律留空，除非照片清楚印有售價。\n"
              '格式：{"artist":"","album":"","year":"","label":"","format":"","genre":"","tracks":"","condition":"","suggested_grade":"B","estimated_value":"","notes":"","low_confidence":[]}')
    gemini_error = None
    if GEMINI_API_KEY:
        try:
            result, gemini_model = recognize_with_gemini(image_data, media_type, prompt)
            if result.get("suggested_grade") not in ("A", "B", "C"):
                result["suggested_grade"] = "B"
            result["estimated_value"] = ""
            result["_engine"] = "gemini+google_vision" if (full_text or labels or logos) else "gemini"
            result["_model"] = gemini_model
            return jsonify(result)
        except (ProviderError, json.JSONDecodeError, KeyError, IndexError) as exc:
            gemini_error = exc if isinstance(exc, ProviderError) else ProviderError("Gemini 回傳格式不正確，已改用備援服務", 502)
    else:
        gemini_error = ProviderError("尚未設定 Gemini", 503)

    anthropic_error = None
    if ANTHROPIC_API_KEY:
        try:
            response = post_with_retry(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
                json={"model": ANTHROPIC_MODEL, "max_tokens": 1024, "temperature": 0.1, "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                    {"type": "text", "text": prompt}
                ]}]}
            )
            if not response.ok:
                raise friendly_provider_error("Anthropic", response.status_code, response.text[:500])
            payload = response.json()
            text = "".join(part.get("text", "") for part in payload.get("content", []) if part.get("type") == "text")
            result = parse_json_object(text)
            if result.get("suggested_grade") not in ("A", "B", "C"):
                result["suggested_grade"] = "B"
            result["estimated_value"] = ""
            result["_engine"] = "anthropic+google_vision" if (full_text or labels or logos) else "anthropic"
            if gemini_error:
                result["warning"] = str(gemini_error)
            return jsonify(result)
        except (ProviderError, json.JSONDecodeError) as exc:
            anthropic_error = exc if isinstance(exc, ProviderError) else ProviderError("AI 回傳格式不正確，請重試", 502)
    else:
        anthropic_error = ProviderError("尚未設定 Anthropic", 503)

    if full_text or labels or logos:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        artist = logos[0] if logos else (lines[0] if lines else "")
        album = lines[1] if len(lines) > 1 else ""
        return jsonify({
            "artist": artist[:120], "album": album[:160], "year": "", "label": "",
            "format": "", "genre": ", ".join(labels[:3]), "tracks": "", "condition": "待人工確認",
            "suggested_grade": "B", "estimated_value": "",
            "notes": "目前使用 Google Vision 備援辨識；請依封面文字人工確認。",
            "low_confidence": ["artist", "album", "year", "label", "format", "genre", "tracks", "condition", "suggested_grade"],
            "_engine": "google_vision_fallback",
            "warning": "；".join(str(err) for err in (gemini_error, anthropic_error) if err)
        })

    errors = [str(err) for err in (gemini_error, anthropic_error, vision_error) if err]
    return jsonify({"error": "辨識暫時無法完成。" + "；".join(errors)}), 503

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
