from datetime import datetime, timezone
import json
import logging
import random
from flask import Flask, jsonify, request
import requests

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

captured_requests = []

DEFAULT_TITLE_ID = "87F0E"
DEFAULT_PLAYFAB_ID = "9EB6BDFDA5FB38EA"
DEFAULT_ENTITY_ID = "1CE79C2ED1CDE4C0"


def _add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Authorization"
    )
    return response


def _build_cors_response():
    response = jsonify({"status": "ok"})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Authorization"
    )
    return response, 204


def generate_random_custom_id():
    # Generates a random Oculus-style Custom ID like the ones used in requests
    random_digits = "".join([str(random.randint(0, 9)) for _ in range(17)])
    return f"OCULUS{random_digits}"


def get_session_ticket_lookup(custom_id, title_id=DEFAULT_TITLE_ID):
    url = f"https://{title_id}.playfabapi.com/Client/LoginWithCustomID"
    payload = {
        "TitleId": title_id,
        "CustomId": custom_id,
        "CreateAccount": True,  # Always create a new account if it doesn't exist
        "InfoRequestParameters": {
            "GetUserAccountInfo": True,
            "GetPlayerProfile": True,
            "GetUserInventory": False,
            "GetUserVirtualCurrency": False,
            "GetUserData": False,
            "GetTitleData": False,
            "GetPlayerStatistics": False,
        },
    }
    headers = {"Content-Type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        data = resp.json()
        if data.get("code") == 200:
            d = data.get("data", {})
            entity = d.get("EntityToken", {})
            return {
                "success": True,
                "session_ticket": d.get("SessionTicket"),
                "playfab_id": d.get("PlayFabId"),
                "newly_created": d.get("NewlyCreated", False),
                "entity_token": entity.get("EntityToken"),
                "entity_id": entity.get("Entity", {}).get("Id"),
                "entity_type": entity.get("Entity", {}).get("Type"),
                "token_expiration": entity.get("TokenExpiration"),
                "custom_id": custom_id,
                "title_id": title_id,
            }
        return {
            "success": False,
            "error": data.get("errorMessage", "Login failed"),
            "error_code": data.get("errorCode"),
            "raw": data,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route("/api/PlayFabAuthentication", methods=["GET", "POST", "OPTIONS"])
def authenticate():
    if request.method == "OPTIONS":
        return _build_cors_response()

    # Support both GET and POST requests for triggering account generation
    if request.method == "POST":
        raw_body = request.get_data(as_text=True)
        try:
            body_json = json.loads(raw_body) if raw_body else {}
        except Exception:
            body_json = {}
    else:
        body_json = request.args.to_dict()

    logger.info(f"Auth request received: {body_json}")
    captured_requests.append(
        {"timestamp": datetime.now(timezone.utc).isoformat(), "body_or_params": body_json}
    )

    # Determine Title ID or use default
    title_id = body_json.get("TitleId") or DEFAULT_TITLE_ID

    # Generate a brand-new random Custom ID on every request
    generated_custom_id = generate_random_custom_id()
    logger.info(f"Generated brand-new CustomId for login: {generated_custom_id}")

    # Call PlayFab to register/login the new account
    lookup_result = get_session_ticket_lookup(generated_custom_id, title_id)

    if not lookup_result["success"]:
        logger.error(f"PlayFab account generation failed: {lookup_result}")
        response = jsonify({
            "code": 400,
            "status": "BadRequest",
            "error": "Failed to generate new PlayFab account",
            "details": lookup_result
        })
        return _add_cors_headers(response), 400

    # Build response using the newly generated account data
    response_data = {
        "AccountCreationIsoTimestamp": datetime.now(timezone.utc).isoformat(),
        "EntityId": lookup_result.get("entity_id", DEFAULT_ENTITY_ID),
        "EntityToken": lookup_result.get("entity_token", ""),
        "EntityType": lookup_result.get("entity_type", "title_player_account"),
        "HeartbeatSecret": "07e156aefcfb43669c4dc4652659b6ff178821dca1a19ed5b796e9db8282458c",
        "PlayFabId": lookup_result.get("playfab_id", DEFAULT_PLAYFAB_ID),
        "SessionTicket": lookup_result.get("session_ticket", ""),
        "sessionToken": f"{lookup_result.get('playfab_id')}|1788565891|637670|50cf73601c696df3ef4107543a2f184558f6ba9caabf73eb00fc8568a6886a55",
        "TrustScore": 100,
        "NewlyCreated": lookup_result.get("newly_created", True),
        "SettingsForUser": {
            "GatherDeviceInfo": True,
            "GatherFocusInfo": True,
            "NeedsAttribution": False,
        },
        "TreatmentAssignment": {"Variables": [], "Variants": []},
    }
    
    response = jsonify(response_data)
    return _add_cors_headers(response), 200


@app.route("/api/get-session-ticket", methods=["GET", "POST"])
def api_get_session_ticket():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        custom_id = data.get("custom_id", "")
        title_id = data.get("title_id", DEFAULT_TITLE_ID)
    else:
        custom_id = request.args.get("custom_id", "")
        title_id = request.args.get("title_id", DEFAULT_TITLE_ID)

    if not custom_id:
        return (
            jsonify({"success": False, "error": "custom_id is required"}),
            400,
        )

    result = get_session_ticket_lookup(custom_id, title_id)
    return jsonify(result), 200 if result["success"] else 400


@app.route("/session-ticket", methods=["GET"])
def session_ticket_page():
    sample_custom_id = generate_random_custom_id()
    title_id = request.args.get("title_id", DEFAULT_TITLE_ID)
    return (
        f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PlayFab Session Ticket Lookup</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0a0a0f;
            color: #e0e0e0;
            font-family: 'Segoe UI', system-ui, sans-serif;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .container {{ width: 100%; max-width: 800px; }}
        .header {{ text-align: center; margin-bottom: 40px; }}
        .header h1 {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #6366f1, #8b5cf6, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 8px;
        }}
        .header p {{ color: #6b7280; font-size: 0.95rem; }}
        .card {{
            background: #111118;
            border: 1px solid #1f1f2e;
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
            box-shadow: 0 4px 24px rgba(0,0,0,0.4);
        }}
        .form-group {{ margin-bottom: 20px; }}
        label {{
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: #9ca3af;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
        }}
        input {{
            width: 100%;
            background: #0d0d14;
            border: 1px solid #2d2d3d;
            border-radius: 10px;
            padding: 12px 16px;
            color: #e0e0e0;
            font-size: 0.95rem;
            font-family: 'Courier New', monospace;
            transition: border-color 0.2s, box-shadow 0.2s;
            outline: none;
        }}
        input:focus {{
            border-color: #6366f1;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
        }}
        input::placeholder {{ color: #4b5563; }}
        .btn {{
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            border: none;
            border-radius: 10px;
            color: white;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s, transform 0.1s;
            margin-top: 8px;
        }}
        .btn:hover {{ opacity: 0.9; }}
        .btn:active {{ transform: scale(0.99); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        .result-card {{
            display: none;
            background: #111118;
            border: 1px solid #1f1f2e;
            border-radius: 16px;
            padding: 32px;
            margin-bottom: 24px;
        }}
        .result-card.success {{ border-color: #059669; }}
        .result-card.error {{ border-color: #dc2626; }}
        .result-header {{ display: flex; align-items: center; gap: 10px; margin-bottom: 24px; }}
        .badge {{
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
        }}
        .badge.success {{ background: rgba(5,150,105,0.15); color: #10b981; border: 1px solid #059669; }}
        .badge.error {{ background: rgba(220,38,38,0.15); color: #f87171; border: 1px solid #dc2626; }}
        .result-title {{ font-size: 1.1rem; font-weight: 600; }}
        .field {{ margin-bottom: 16px; }}
        .field-label {{
            font-size: 0.75rem;
            font-weight: 600;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }}
        .field-value {{
            background: #0d0d14;
            border: 1px solid #2d2d3d;
            border-radius: 8px;
            padding: 10px 14px;
            font-family: 'Courier New', monospace;
            font-size: 0.82rem;
            color: #a78bfa;
            word-break: break-all;
        }}
        .copy-btn {{
            display: inline-block;
            margin-top: 6px;
            padding: 4px 12px;
            background: #1f1f2e;
            border: 1px solid #2d2d3d;
            border-radius: 6px;
            color: #9ca3af;
            font-size: 0.75rem;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .copy-btn:hover {{ background: #2d2d3d; color: #e0e0e0; }}
        .copy-btn.copied {{ background: rgba(5,150,105,0.15); border-color: #059669; color: #10b981; }}
        .expiry {{ font-size: 0.85rem; color: #f59e0b; margin-top: 8px; }}
        .loading {{ display: none; text-align: center; padding: 20px; color: #6b7280; }}
        .spinner {{
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid #2d2d3d;
            border-top-color: #6366f1;
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
            margin-right: 8px;
            vertical-align: middle;
        }}
        @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
        .divider {{ border: none; border-top: 1px solid #1f1f2e; margin: 20px 0; }}
        .raw-toggle {{ color: #6366f1; cursor: pointer; font-size: 0.85rem; background: none; border: none; padding: 0; text-decoration: underline; }}
        .raw-json {{
            display: none;
            background: #0d0d14;
            border: 1px solid #2d2d3d;
            border-radius: 8px;
            padding: 16px;
            font-family: 'Courier New', monospace;
            font-size: 0.8rem;
            color: #9ca3af;
            white-space: pre-wrap;
            word-break: break-all;
            margin-top: 10px;
            max-height: 300px;
            overflow-y: auto;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>PlayFab Session Ticket</h1>
            <p>Look up session tickets using a Custom ID and Title ID</p>
        </div>
        <div class="card">
            <div class="form-group">
                <label>Title ID</label>
                <input type="text" id="titleId" placeholder="e.g. 87F0E" value="{title_id}" />
            </div>
            <div class="form-group">
                <label>Custom ID</label>
                <input type="text" id="customId" placeholder="e.g. OCULUS39372129122432269" value="{sample_custom_id}" />
            </div>
            <button class="btn" onclick="lookup()" id="lookupBtn">Get Session Ticket</button>
        </div>
        <div class="loading" id="loading">
            <span class="spinner"></span> Looking up session ticket...
        </div>
        <div class="result-card" id="resultCard">
            <div class="result-header">
                <span class="badge" id="resultBadge"></span>
                <span class="result-title" id="resultTitle"></span>
            </div>
            <div id="successContent" style="display:none">
                <div class="field">
                    <div class="field-label">Session Ticket</div>
                    <div class="field-value" id="sessionTicket"></div>
                    <span class="copy-btn" onclick="copyField('sessionTicket', this)">Copy</span>
                </div>
                <div class="field">
                    <div class="field-label">PlayFab ID</div>
                    <div class="field-value" id="playfabId"></div>
                    <span class="copy-btn" onclick="copyField('playfabId', this)">Copy</span>
                </div>
                <div class="field">
                    <div class="field-label">Entity Token</div>
                    <div class="field-value" id="entityToken"></div>
                    <span class="copy-btn" onclick="copyField('entityToken', this)">Copy</span>
                </div>
                <div class="field">
                    <div class="field-label">Entity ID</div>
                    <div class="field-value" id="entityId"></div>
                    <span class="copy-btn" onclick="copyField('entityId', this)">Copy</span>
                </div>
                <div class="field">
                    <div class="field-label">Token Expiration</div>
                    <div class="field-value" id="tokenExpiration"></div>
                </div>
                <div class="expiry" id="expiryWarning"></div>
            </div>
            <div id="errorContent" style="display:none">
                <div class="field">
                    <div class="field-label">Error</div>
                    <div class="field-value" id="errorMsg" style="color:#f87171"></div>
                </div>
            </div>
            <hr class="divider">
            <button class="raw-toggle" onclick="toggleRaw()">Show Raw Response</button>
            <div class="raw-json" id="rawJson"></div>
        </div>
    </div>
    <script>
        let rawVisible = false;
        async function lookup() {{
            const customId = document.getElementById('customId').value.trim();
            const titleId = document.getElementById('titleId').value.trim();
            if (!customId || !titleId) {{ alert('Please enter both fields'); return; }}
            document.getElementById('lookupBtn').disabled = true;
            document.getElementById('loading').style.display = 'block';
            document.getElementById('resultCard').style.display = 'none';
            try {{
                const resp = await fetch('/api/get-session-ticket', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{custom_id: customId, title_id: titleId}})
                }});
                const data = await resp.json();
                showResult(data);
            }} catch(e) {{
                showResult({{success: false, error: e.message}});
            }} finally {{
                document.getElementById('lookupBtn').disabled = false;
                document.getElementById('loading').style.display = 'none';
            }}
        }}
        function showResult(data) {{
            const card = document.getElementById('resultCard');
            const badge = document.getElementById('resultBadge');
            const title = document.getElementById('resultTitle');
            card.style.display = 'block';
            card.className = 'result-card ' + (data.success ? 'success' : 'error');
            badge.className = 'badge ' + (data.success ? 'success' : 'error');
            badge.textContent = data.success ? 'SUCCESS' : 'ERROR';
            if (data.success) {{
                title.textContent = 'Session ticket retrieved successfully';
                document.getElementById('successContent').style.display = 'block';
                document.getElementById('errorContent').style.display = 'none';
                document.getElementById('sessionTicket').textContent = data.session_ticket || '';
                document.getElementById('playfabId').textContent = data.playfab_id || '';
                document.getElementById('entityToken').textContent = data.entity_token || '';
                document.getElementById('entityId').textContent = data.entity_id || '';
                document.getElementById('tokenExpiration').textContent = data.token_expiration || '';
                if (data.token_expiration) {{
                    const exp = new Date(data.token_expiration);
                    const now = new Date();
                    const diffH = Math.round((exp - now) / 3600000);
                    document.getElementById('expiryWarning').textContent = '⚠ Token expires in approximately ' + diffH + ' hour(s)';
                }}
            }} else {{
                title.textContent = 'Failed to retrieve session ticket';
                document.getElementById('successContent').style.display = 'none';
                document.getElementById('errorContent').style.display = 'block';
                document.getElementById('errorMsg').textContent = data.error || JSON.stringify(data);
            }}
            document.getElementById('rawJson').textContent = JSON.stringify(data, null, 2);
        }}
        function copyField(id, btn) {{
            const text = document.getElementById(id).textContent;
            navigator.clipboard.writeText(text).then(() => {{
                btn.textContent = 'Copied!';
                btn.classList.add('copied');
                setTimeout(() => {{ btn.textContent = 'Copy'; btn.classList.remove('copied'); }}, 2000);
            }});
        }}
        function toggleRaw() {{
            rawVisible = !rawVisible;
            document.getElementById('rawJson').style.display = rawVisible ? 'block' : 'none';
        }}
        document.addEventListener('keydown', e => {{ if (e.key === 'Enter') lookup(); }});
    </script>
</body>
</html>
""",
        200,
    )


@app.route("/captured", methods=["GET"])
def view_captured():
    return (
        jsonify({"count": len(captured_requests), "requests": captured_requests}),
        200,
    )


@app.route("/api/TitleData", methods=["GET", "POST"])
def TitleData():
    return jsonify({
        "MOTD": "<color=green>This was made by zenith. Thanks matin for some help.</color>\n\n<color=cyan>And We have certainly made the Quran easy for remembrance, so is there any who will remember?</color>\n<color=green>(Surah Al-Qamar 54:17)</color>"
    })


@app.route("/captured/latest", methods=["GET"])
def view_latest():
    if not captured_requests:
        return jsonify({"error": "nothing yet"}), 404
    return jsonify(captured_requests[-1]), 200


@app.route("/captured/clear", methods=["GET", "POST"])
def clear_captured():
    captured_requests.clear()
    return jsonify({"cleared": True}), 200


@app.route("/api/health", methods=["GET"])
def health():
    response = jsonify({
        "status": "healthy",
        "title_id": DEFAULT_TITLE_ID,
    })
    return _add_cors_headers(response), 200


@app.route("/", methods=["GET"])
def index():
    response = jsonify({
        "status": "online",
        "title_id": DEFAULT_TITLE_ID,
        "endpoints": [
            "GET/POST /api/PlayFabAuthentication - generates a brand new PlayFab account on every hit",
            "POST /api/get-session-ticket    - get session ticket from custom id",
            "GET  /session-ticket             - session ticket lookup UI",
            "GET  /captured                   - see captured requests",
            "GET  /captured/latest            - see latest request",
            "GET  /captured/clear             - clear log",
            "GET  /api/health                 - health check",
            "POST AND GET /api/TitleData        - TitleData"
        ],
    })
    return _add_cors_headers(response), 200


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
