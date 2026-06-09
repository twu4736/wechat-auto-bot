"""
微信主播拟人化陪聊工具 - 主入口
支持 CLI 模式和 Web 控制面板模式
"""

import sys
import signal
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from src.utils.config import load_config, setup_logging
from src.llm.client import LLMClient
from src.wechat.handler import WeChatHandler
from src.livestream.notifier import LivestreamNotifier


class WeChatBot:
    """微信主播陪聊机器人"""

    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = load_config(config_path)
        setup_logging(self.config)

        logger.info("=" * 50)
        logger.info("微信主播陪聊工具 v2.0.0")
        logger.info("=" * 50)

        # 初始化各模块
        self.llm_client = LLMClient(self.config.get("llm", {}))
        self.wechat_handler = WeChatHandler(self.config.get("wechat", {}))
        self.livestream_notifier = LivestreamNotifier(self.config.get("livestream", {}))

        # 设置消息处理回调
        self.wechat_handler.set_message_handler(self._handle_message)
        self.livestream_notifier.set_send_callback(self._send_notification)

        # 注入直播课表到 LLM system prompt，让主播知道当前排班
        self.llm_client.set_dynamic_info_callback(self._get_schedule_context)

        # 消息计数
        self._message_count = 0

    def _handle_message(self, user_id: str, message: str, is_group: bool) -> str:
        """处理收到的消息"""
        self._message_count += 1
        logger.debug(f"处理消息: user={user_id}, is_group={is_group}, msg={message}")

        reply = self._check_commands(user_id, message)
        if reply:
            return reply

        reply = self.llm_client.chat(user_id, message)
        return reply

    def _check_commands(self, user_id: str, message: str) -> str:
        """检查特殊指令"""
        msg = message.strip().lower()

        if msg in ["直播时间", "直播安排", "什么时候直播", "直播时间表"]:
            return self.livestream_notifier.get_schedule_text()

        if msg in ["直播间", "直播间链接", "在哪看直播"]:
            info = self.livestream_notifier.get_live_info()
            if info["is_live"]:
                return f"正在直播中哦~快来！\n📺 {info['room_name']}\n🔗 {info['room_url']}"
            else:
                return f"现在没在直播哦~\n🔗 直播间收藏: {info['room_url']}"

        if msg in ["在直播吗", "直播状态", "正在直播吗"]:
            info = self.livestream_notifier.get_live_info()
            if info["is_live"]:
                return f"在播在播！正在直播 {info['current_activity']}，快来呀~🥰"
            else:
                return "现在没有在直播哦~看看直播时间表，下次来陪我吧~💕"

        if msg in ["重新开始", "清空记录", "新对话"]:
            self.llm_client.clear_history(user_id)
            return "好的呢~我们重新开始聊天吧！✨"

        return ""

    def _get_schedule_context(self) -> str:
        """生成直播课表上下文，注入到 system prompt"""
        schedule = self.livestream_notifier.schedule
        if not schedule:
            return "当前没有安排直播。"

        lines = ["以下是你当前的直播排班表（粉丝问直播时间时参考此表回答）："]
        for item in schedule:
            lines.append(f"- {item['day']} {item['time']}：{item['content']}")
        lines.append(f"直播间链接：{self.livestream_notifier.room_url}")
        return "\n".join(lines)

    def _send_notification(self, group_names: list, message: str):
        """发送通知消息"""
        self.wechat_handler.send_to_groups(group_names, message)

    def start_cli(self):
        """CLI 模式启动（阻塞）"""
        signal.signal(signal.SIGINT, self._shutdown_cli)
        signal.signal(signal.SIGTERM, self._shutdown_cli)

        logger.info("正在启动机器人（CLI模式）...")
        self.livestream_notifier.start()
        logger.info("直播通知已启动")
        logger.info("正在启动微信消息监听...")
        self.wechat_handler.start()

    def _shutdown_cli(self, signum, frame):
        """CLI模式关闭"""
        logger.info("正在关闭机器人...")
        self.livestream_notifier.stop()
        self.wechat_handler.logout()
        logger.info("机器人已关闭")
        sys.exit(0)

    def start_web(self, host: str = "0.0.0.0", port: int = 5000):
        """Web 控制面板模式启动"""
        from src.web.app import create_app, socketio

        app = create_app(self)
        logger.info(f"Web 控制面板启动中... http://{host}:{port}")
        socketio.run(app, host=host, port=port, allow_unsafe_werkzeug=True)

    def get_status(self) -> dict:
        """获取系统整体状态"""
        return {
            "wechat": {
                "logged_in": self.wechat_handler.is_logged_in,
                "running": self.wechat_handler.is_running,
                "nickname": self.wechat_handler.my_nickname,
                "auto_reply": self.wechat_handler.auto_reply_enabled,
            },
            "livestream": self.livestream_notifier.get_status(),
            "message_count": self._message_count,
        }


def main():
    parser = argparse.ArgumentParser(description="微信主播陪聊工具")
    parser.add_argument("--web", action="store_true", help="启动Web控制面板模式")
    parser.add_argument("--host", default="0.0.0.0", help="Web服务监听地址")
    parser.add_argument("--port", type=int, default=5000, help="Web服务端口")
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    args = parser.parse_args()

    try:
        bot = WeChatBot(config_path=args.config)

        if args.web:
            bot.start_web(host=args.host, port=args.port)
        else:
            bot.start_cli()

    except FileNotFoundError as e:
        logger.error(f"启动失败: {e}")
        print("\n请确保配置文件存在: config/config.yaml")
        print("可以复制示例配置: cp config/config.example.yaml config/config.yaml")
    except Exception as e:
        logger.error(f"启动异常: {e}")
        raise


if __name__ == "__main__":
    main()
