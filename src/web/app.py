"""
Web 控制面板模块
Flask + SocketIO 实现实时状态推送和控制
"""

import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_socketio import SocketIO
from loguru import logger

# 延迟初始化，在 create_app 中绑定到 Flask app
socketio = SocketIO()


def create_app(bot) -> Flask:
    """
    创建 Flask 应用

    Args:
        bot: WeChatBot 实例
    """
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )
    app.config["SECRET_KEY"] = "wechat-auto-secret"

    # 绑定 SocketIO 到 app
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # 设置 bot 的回调，通过 SocketIO 推送事件到前端
    _setup_callbacks(bot)

    # ---- 页面路由 ----

    @app.route("/")
    def index():
        return render_template("index.html")

    # ---- QR码图片 ----

    @app.route("/api/qrcode")
    def get_qrcode():
        """获取QR码图片（从文件读取，作为备用）"""
        qr_path = Path("temp/qrcode.png")
        if qr_path.exists():
            return send_file(str(qr_path), mimetype="image/png")
        return "", 404

    # ---- 登录相关 ----

    @app.route("/api/login", methods=["POST"])
    def login():
        """触发微信登录"""
        if bot.wechat_handler.is_logged_in:
            return jsonify({"success": True, "message": "已登录", "nickname": bot.wechat_handler.my_nickname})

        # 在后台线程执行登录（不使用热加载，保证每次都显示二维码）
        def do_login():
            try:
                logger.info("Web登录线程启动")
                result = bot.wechat_handler.login(use_hot_reload=False)
                if result["success"]:
                    bot.wechat_handler.start_listening()
                    bot.livestream_notifier.start()
                socketio.emit("login_result", result)
            except Exception as e:
                logger.error(f"Web登录线程异常: {e}")
                socketio.emit("login_result", {"success": False, "message": str(e), "nickname": ""})

        threading.Thread(target=do_login, daemon=True).start()
        return jsonify({"success": True, "message": "正在登录，请扫描二维码..."}), 202

    @app.route("/api/logout", methods=["POST"])
    def logout():
        """退出登录"""
        try:
            bot.livestream_notifier.stop()
            bot.wechat_handler.logout()
            socketio.emit("status_update", bot.get_status())
            return jsonify({"success": True, "message": "已退出登录"})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500

    # ---- 状态查询 ----

    @app.route("/api/status")
    def get_status():
        """获取系统状态"""
        return jsonify(bot.get_status())

    # ---- 自动回复 ----

    @app.route("/api/auto-reply/toggle", methods=["POST"])
    def toggle_auto_reply():
        """开关自动回复"""
        data = request.get_json(silent=True) or {}
        if "enabled" in data:
            bot.wechat_handler.auto_reply_enabled = bool(data["enabled"])
        else:
            bot.wechat_handler.auto_reply_enabled = not bot.wechat_handler.auto_reply_enabled

        socketio.emit("status_update", bot.get_status())
        return jsonify({
            "success": True,
            "auto_reply": bot.wechat_handler.auto_reply_enabled
        })

    # ---- 直播通知 ----

    @app.route("/api/livestream/schedule", methods=["GET"])
    def get_schedule():
        """获取直播课表"""
        return jsonify({
            "schedule": bot.livestream_notifier.schedule,
            "notify_groups": bot.livestream_notifier.notify_groups,
            "notify_before": bot.livestream_notifier.notify_before,
        })

    @app.route("/api/livestream/schedule", methods=["POST"])
    def add_schedule():
        """添加直播时间"""
        data = request.get_json(silent=True) or {}
        day = data.get("day", "").strip()
        time_str = data.get("time", "").strip()
        content = data.get("content", "").strip()

        if not day or not time_str:
            return jsonify({"success": False, "message": "缺少必要参数"}), 400

        item = bot.livestream_notifier.add_schedule(day, time_str, content or "直播开始啦")
        socketio.emit("status_update", bot.get_status())
        return jsonify({"success": True, "item": item})

    @app.route("/api/livestream/schedule/<item_id>", methods=["DELETE"])
    def delete_schedule(item_id):
        """删除直播时间"""
        ok = bot.livestream_notifier.remove_schedule(item_id)
        if ok:
            socketio.emit("status_update", bot.get_status())
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "未找到该条目"}), 404

    @app.route("/api/livestream/schedule/<item_id>", methods=["PUT"])
    def update_schedule(item_id):
        """更新直播时间"""
        data = request.get_json(silent=True) or {}
        ok = bot.livestream_notifier.update_schedule(
            item_id,
            day=data.get("day"),
            time_str=data.get("time"),
            content=data.get("content"),
        )
        if ok:
            socketio.emit("status_update", bot.get_status())
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "未找到该条目"}), 404

    @app.route("/api/livestream/notify", methods=["POST"])
    def send_notify():
        """手动发送直播通知"""
        data = request.get_json(silent=True) or {}
        content = data.get("content", "").strip()
        if not content:
            return jsonify({"success": False, "message": "通知内容不能为空"}), 400

        bot.livestream_notifier.send_custom_notification(content)
        return jsonify({"success": True, "message": "通知已发送"})

    @app.route("/api/livestream/status", methods=["POST"])
    def set_live_status():
        """设置直播状态"""
        data = request.get_json(silent=True) or {}
        is_live = bool(data.get("is_live", False))
        activity = data.get("activity", "")
        bot.livestream_notifier.set_live_status(is_live, activity)
        socketio.emit("status_update", bot.get_status())
        return jsonify({"success": True, "is_live": is_live})

    # ---- 日志 ----

    @app.route("/api/logs")
    def get_logs():
        """获取最近日志"""
        log_file = Path("logs/bot.log")
        if log_file.exists():
            lines = log_file.read_text(encoding="utf-8").strip().split("\n")
            return jsonify({"logs": lines[-100:]})
        return jsonify({"logs": []})

    return app


def _setup_callbacks(bot):
    """设置 bot 回调，将事件推送到 Web 前端"""

    def on_message_log(msg_data):
        socketio.emit("new_message", msg_data)

    bot.wechat_handler.set_message_log_callback(on_message_log)

    def on_login_success(info):
        socketio.emit("status_update", bot.get_status())

    bot.wechat_handler.set_login_success_callback(on_login_success)

    def on_login_status(status: str):
        """登录状态变更时推送（scanning / scanned / confirmed / expired）"""
        socketio.emit("login_status", {"status": status})

    bot.wechat_handler.set_login_status_callback(on_login_status)
