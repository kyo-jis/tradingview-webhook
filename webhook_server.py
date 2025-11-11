import os
import logging
from datetime import datetime
import requests
from flask import Flask, request, jsonify

# --- 設定 -----------------------------------------------------------------

# Renderなどのサーバー側で環境変数 "DISCORD_WEBHOOK_URL" を設定してください
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

# (オプション) シークレットキー。
# プレーンテキストモードでは使いにくいため、Noneのままを推奨
SECRET_KEY = None

# --- アプリケーションの初期化 -----------------------------------------------

app = Flask(__name__)

# Flaskの標準ロガーを設定
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# --- リクエスト前処理 -------------------------------------------------------

@app.before_request
def log_request_info():
    """リクエストごとに基本情報をログに出力"""
    app.logger.debug(f"Path: {request.path}")
    app.logger.debug(f"Headers: {request.headers}")
    app.logger.debug(f"Body: {request.get_data(as_text=True)}")

# --- メインのWebhookエンドポイント ------------------------------------------

@app.route('/webhook', methods=['POST'])
def webhook():
    """TradingViewからのアラートを受信し、Discordに転送する"""
    app.logger.info("Webhook received.")

    # 1. Webhook URLが設定されているか確認
    if not DISCORD_WEBHOOK_URL:
        app.logger.error("DISCORD_WEBHOOK_URL is not set in environment variables.")
        return jsonify({"status": "error", "message": "Internal server configuration error"}), 500

    # 2. JSONではなく、生のテキストデータ(Plain Text)として受信
    try:
        # request.data は生のバイナリデータなので、utf-8で文字列にデコード
        raw_message = request.data.decode('utf-8')
        
        if not raw_message:
            app.logger.warning("Request body is empty.")
            return jsonify({"status": "error", "message": "Empty body"}), 400
    
        app.logger.info(f"Received raw message: {raw_message}")

    except Exception as e:
        app.logger.error(f"Failed to decode request body: {e}")
        return jsonify({"status": "error", "message": "Failed to decode request body"}), 400

    # 3. (オプション) シークレットキーの検証
    # プレーンテキストにキーを含めるのは難しいため、通常このロジックは削除・無効化します
    if SECRET_KEY:
        # ここにテキスト用の検証ロジックを実装する必要があります (例: if not raw_message.startswith(SECRET_KEY): ...)
        # 今は検証をスキップします
        pass

    # 4. メッセージの構築 (送られてきた生データをそのまま使う)
    try:
        # TradingViewが {{ticker}} などを解決した後の文字列が raw_message に入っている
        discord_payload = {"content": raw_message}

    except Exception as e:
        app.logger.error(f"Error building Discord payload: {e}")
        return jsonify({"status": "error", "message": "Invalid data format"}), 400

    # 5. Discordへの送信
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=discord_payload, timeout=5)

        # Discordからのレスポンスステータスをチェック (成功 2xx 以外)
        if not (200 <= response.status_code < 300):
            app.logger.error(f"Discord API returned non-2xx status: {response.status_code} - {response.text}")
            return jsonify({
                "status": "error",
                "message": "Failed to relay message to Discord",
                "discord_response": response.text
            }), 502
        
        app.logger.info(f"Successfully sent raw message to Discord.")
        return jsonify({"status": "ok"}), 200

    except requests.exceptions.RequestException as e:
        # タイムアウト、DNSエラー、接続エラーなど
        app.logger.error(f"Network error while sending to Discord: {e}")
        return jsonify({"status": "error", "message": "Could not connect to Discord"}), 503

# --- サーバー起動 -----------------------------------------------------------

if __name__ == '__main__':
    if not DISCORD_WEBHOOK_URL:
        app.logger.warning("="*50)
        app.logger.warning("!!! 警告: 環境変数 'DISCORD_WEBHOOK_URL' が設定されていません !!!")
        app.logger.warning("!!! ローカルテスト時、Discordへの通知は失敗します。!!!")
        app.logger.warning("="*50)

    # 開発用サーバーで実行 (本番環境では gunicorn を使ってください)
    app.logger.info(f"Starting development server at http://0.0.0.0:5000")
    # Renderはport=5000を無視し、自動で10000番を使うのでローカルテストでは 5000 を使います
    app.run(host='0.0.0.0', port=5000, debug=True)
