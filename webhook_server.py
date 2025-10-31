from flask import Flask, request, jsonify
import requests
from datetime import datetime
import logging
import os  # 環境変数を読み込むためにosをインポート

# --- 設定 -----------------------------------------------------------------

# 環境変数からDiscord Webhook URLを取得
# サーバー側（Render, Heroku, VPSなど）で環境変数を設定してください
# ローカルテスト用: export DISCORD_WEBHOOK_URL="https://..." のように設定
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# (オプション) Webhookを保護するためのシークレットキー
# これを設定した場合、TradingViewのアラートメッセージのJSONに "key" を含める必要があります
# 例: {"key": "mysecret123", "ticker": "{{ticker}}", ...}
# これも環境変数から取得するのがベストです
# SECRET_KEY = os.environ.get("WEBHOOK_SECRET_KEY")
SECRET_KEY = None  # ここにシークレットキーを文字列で設定するか、Noneのままにする

# --- アプリケーションの初期化 -----------------------------------------------

app = Flask(__name__)

# Flaskの標準ロガーを設定
# print() の代わりに app.logger を使うことで、ログのレベル管理やファイル出力が容易になります
logging.basicConfig(level=logging.INFO)  # 本番環境ではINFO、開発中はDEBUG
app.logger.setLevel(logging.INFO)

# --- リクエスト前処理 -------------------------------------------------------

@app.before_request
def log_request_info():
    """リクエストごとに基本情報をログに出力"""
    app.logger.debug(f"Path: {request.path}")
    app.logger.debug(f"Headers: {request.headers}")
    # ボディは get_data() で生データを取得します
    # ※大きなデータが送られる可能性がある場合はログ出力を省略することも検討
    app.logger.debug(f"Body: {request.get_data(as_text=True)}")

# --- メインのWebhookエンドポイント ------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingViewからのアラートを受信し、Discordに転送する"""
    app.logger.info("Webhook received.")

    # 1. Webhook URLが設定されているか確認
    if not DISCORD_WEBHOOK_URL:
        app.logger.error("DISCORD_WEBHOOK_URL is not set in environment variables.")
        # サーバー内部の設定ミスなので 500 Internal Server Error を返す
        return jsonify({"status": "error", "message": "Internal server configuration error"}), 500

    # 2. JSONデータのパース
    try:
        # request.json は Content-Type が application/json でない場合や
        # データが不正な場合に例外 (BadRequest) を発生させます
        data = request.json
        if data is None:
            app.logger.warning("Request body is empty or not valid JSON.")
            return jsonify({"status": "error", "message": "Invalid JSON or empty body"}), 400
    except Exception as e:
        app.logger.error(f"Failed to parse JSON: {e}")
        return jsonify({"status": "error", "message": "Failed to parse JSON"}), 400

    app.logger.debug(f"Received data: {data}")

    # 3. (オプション) シークレットキーの検証
    if SECRET_KEY:
        if data.get("key") != SECRET_KEY:
            app.logger.warning("Unauthorized access: Invalid or missing secret key.")
            return jsonify({"status": "error", "message": "Unauthorized"}), 403  # 403 Forbidden

    # 4. メッセージの構築
    try:
        symbol = data.get('ticker', 'unknown')
        signal = data.get('strategy', {}).get('order_action', 'none')
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Discordで見やすいようにマークダウンを使用
        msg_content = f"[{time_str}] **{symbol}**: `{signal.upper()}` シグナルを検出"
        discord_payload = {"content": msg_content}

    except Exception as e:
        app.logger.error(f"Error building message from data: {e}")
        return jsonify({"status": "error", "message": "Invalid data format"}), 400

    # 5. Discordへの送信
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=5)

        # Discordからのレスポンスステータスをチェック
        # 成功 (2xx) 以外はエラーとして扱う
        if not (200 <= response.status_code < 300):
            app.logger.error(f"Discord API returned non-2xx status: {response.status_code} - {response.text}")
            # Discord側(上流サーバー)の問題なので 502 Bad Gateway を返す
            return jsonify({
                "status": "error",
                "message": "Failed to relay message to Discord",
                "discord_response": response.text
            }), 502
        
        app.logger.info(f"Successfully sent message to Discord: {msg_content}")
        return jsonify({"status": "ok"}), 200

    except requests.exceptions.RequestException as e:
        # タイムアウト、DNSエラー、接続エラーなど
        app.logger.error(f"Network error while sending to Discord: {e}")
        # Discordに到達できなかったので 503 Service Unavailable や 504 Gateway Timeout が適切
        return jsonify({"status": "error", "message": "Could not connect to Discord"}), 503

# --- サーバー起動 -----------------------------------------------------------

if __name__ == '__main__':
    if not DISCORD_WEBHOOK_URL:
        app.logger.warning("="*50)
        app.logger.warning("!!! 警告: 環境変数 'DISCORD_WEBHOOK_URL' が設定されていません !!!")
        app.logger.warning("!!! Discordへの通知は失敗します。!!!")
        app.logger.warning("="*50)

    # 開発用サーバーで実行
    # 警告: 本番環境では `gunicorn` などのWSGIサーバーを使用してください
    # 例: gunicorn -w 4 -b 0.0.0.0:5000 your_app_file:app
    app.logger.info(f"Starting development server at http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True) # 開発中は debug=True でもOK