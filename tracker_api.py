import os
from flask import Flask, request, redirect, jsonify
from gsheet import update_tracking

app = Flask(__name__)

LANDING_PAGE_URL = os.getenv("LANDING_PAGE_URL", "https://your-landing-page.com")
THANKYOU_PAGE_URL = os.getenv("THANKYOU_PAGE_URL", "https://your-thankyou-page.com")


@app.route("/")
def home():
    return "Tracking API is running"


@app.route("/track")
def track():
    cid = request.args.get("cid")
    action = request.args.get("action", "click")
    target = request.args.get("target", LANDING_PAGE_URL)

    if not cid:
        return jsonify({"error": "missing cid"}), 400

    try:
        update_tracking(cid, action if action in ("click", "lead") else "click")
    except Exception as e:
        return jsonify({"error": f"tracking failed: {str(e)}"}), 500

    return redirect(target)


@app.route("/lead")
def lead():
    cid = request.args.get("cid")
    target = request.args.get("target", THANKYOU_PAGE_URL)

    if not cid:
        return jsonify({"error": "missing cid"}), 400

    try:
        update_tracking(cid, "lead")
    except Exception as e:
        return jsonify({"error": f"lead tracking failed: {str(e)}"}), 500

    return redirect(target)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
