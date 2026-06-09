"""
微信消息处理模块
使用itchat实现微信消息接收和发送
"""

import time
import random
import threading
from pathlib import Path
from typing import Callable, Optional, List
from loguru import logger

try:
    import itchat
    from itchat.content import TEXT
except ImportError:
    logger.warning("itchat未安装，请运行: pip install itchat-uos")
    itchat = None


class WeChatHandler:
    """微信消息处理器"""

    def __init__(self, config: dict):
        self.config = config
        self.auto_login = config.get("auto_login", True)
        self.hot_reload = config.get("hot_reload", True)
        self.reply_delay = config.get("reply_delay", {"min": 1, "max": 3})
        self.whitelist = set(config.get("whitelist", []))
        self.blacklist = set(config.get("blacklist", []))

        # 消息处理回调
        self._message_handler: Optional[Callable] = None
        # 登录成功回调
        self._login_success_callback: Optional[Callable[[dict], None]] = None
        # 消息日志回调
        self._message_log_callback: Optional[Callable[[dict], None]] = None
        # 登录状态变更回调
        self._login_status_callback: Optional[Callable[[str], None]] = None

        # 状态
        self._running = False
        self._logged_in = False
        self._my_username = None
        self._my_nickname = None
        self._auto_reply = True  # 自动回复开关

        # itchat 消息注册（只注册一次）
        self._msg_registered = False

    def set_message_handler(self, handler: Callable[[str, str, bool], str]):
        """设置消息处理回调"""
        self._message_handler = handler

    def set_login_status_callback(self, callback: Callable[[str], None]):
        """设置登录状态变更回调"""
        self._login_status_callback = callback

    def set_login_success_callback(self, callback: Callable[[dict], None]):
        """设置登录成功回调"""
        self._login_success_callback = callback

    def set_message_log_callback(self, callback: Callable[[dict], None]):
        """设置消息日志回调，用于Web界面实时显示"""
        self._message_log_callback = callback

    @property
    def is_logged_in(self) -> bool:
        return self._logged_in

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def auto_reply_enabled(self) -> bool:
        return self._auto_reply

    @auto_reply_enabled.setter
    def auto_reply_enabled(self, value: bool):
        self._auto_reply = value
        logger.info(f"自动回复已{'开启' if value else '关闭'}")

    @property
    def my_nickname(self) -> str:
        return self._my_nickname or ""

    def _should_reply(self, username: str, nickname: str) -> bool:
        """判断是否应该回复该用户"""
        if username in self.blacklist or nickname in self.blacklist:
            return False
        if not self.whitelist:
            return True
        return username in self.whitelist or nickname in self.whitelist

    def _simulate_delay(self):
        """模拟打字延迟"""
        min_delay = self.reply_delay.get("min", 1)
        max_delay = self.reply_delay.get("max", 3)
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    def _handle_text_message(self, msg):
        """处理文本消息"""
        try:
            sender = msg["FromUserName"]
            content = msg["Text"].strip()
            is_group = msg.get("IsAt", False) or "@@" in sender

            if is_group:
                actual_sender = msg.get("ActualUserName", sender)
                nickname = msg.get("ActualNickName", "未知用户")
            else:
                actual_sender = sender
                nickname = msg["User"].get("NickName", "未知用户")

            # 过滤自己发的消息
            if self._my_username and actual_sender == self._my_username:
                return

            logger.info(f"收到消息 [{nickname}]: {content}")

            # 推送消息日志到Web界面
            if self._message_log_callback:
                self._message_log_callback({
                    "type": "receive",
                    "nickname": nickname,
                    "content": content,
                    "is_group": is_group,
                    "time": time.strftime("%H:%M:%S")
                })

            # 检查是否需要回复
            if not self._should_reply(actual_sender, nickname):
                logger.debug(f"跳过用户: {nickname}")
                return

            # 群消息需要@才回复
            if is_group and not msg.get("IsAt", False):
                logger.debug(f"群消息未@，跳过: {nickname}")
                return

            # 自动回复开关
            if not self._auto_reply:
                logger.debug("自动回复已关闭，跳过")
                return

            # 调用消息处理回调
            if self._message_handler:
                self._simulate_delay()
                reply = self._message_handler(actual_sender, content, is_group)

                if reply:
                    if is_group:
                        msg["User"].send(f"@{nickname} {reply}")
                    else:
                        msg["User"].send(reply)

                    logger.info(f"回复 [{nickname}]: {reply}")

                    # 推送回复日志
                    if self._message_log_callback:
                        self._message_log_callback({
                            "type": "reply",
                            "nickname": nickname,
                            "content": reply,
                            "is_group": is_group,
                            "time": time.strftime("%H:%M:%S")
                        })

        except Exception as e:
            logger.error(f"处理消息异常: {e}")

    def login(self, use_hot_reload: bool = False) -> dict:
        """
        执行微信登录（阻塞直到登录完成）
        使用 itchat 默认的图片查看器弹出二维码。

        Args:
            use_hot_reload: 是否使用热加载

        Returns:
            {"success": bool, "message": str, "nickname": str}
        """
        if itchat is None:
            return {"success": False, "message": "itchat未安装", "nickname": ""}

        if self._logged_in:
            return {"success": True, "message": "已登录", "nickname": self._my_nickname}

        # statusStorageDir 是 pkl 文件路径，用于保存/加载登录状态
        pkl_file = str(Path("config") / "itchat.pkl")
        Path("config").mkdir(exist_ok=True)

        try:
            logger.info("正在登录微信...")

            # 重置 itchat 状态，防止上次登录残留导致跳过
            itchat_instance = getattr(itchat, 'instance', None)
            if itchat_instance:
                if getattr(itchat_instance, 'isLogging', False):
                    logger.warning("itchat.isLogging=True，重置为False")
                    itchat_instance.isLogging = False
                if getattr(itchat_instance, 'alive', False):
                    logger.warning("itchat.alive=True，先执行logout")
                    itchat_instance.alive = False

            # 非热加载模式删除旧的登录缓存，强制重新扫码
            if not use_hot_reload and Path(pkl_file).exists():
                Path(pkl_file).unlink()
                logger.info("已删除旧登录缓存，强制重新扫码")

            # 开启 itchat 的详细日志
            import logging as _logging
            itchat_logger = _logging.getLogger('itchat')
            itchat_logger.setLevel(_logging.DEBUG)

            class ItchatLoguruHandler(_logging.Handler):
                def emit(self, record):
                    try:
                        msg = self.format(record)
                        if record.levelno >= _logging.ERROR:
                            logger.error(f"[itchat] {msg}")
                        elif record.levelno >= _logging.WARNING:
                            logger.warning(f"[itchat] {msg}")
                        elif record.levelno >= _logging.INFO:
                            logger.info(f"[itchat] {msg}")
                        else:
                            logger.debug(f"[itchat] {msg}")
                    except Exception:
                        pass

            itchat_handler = ItchatLoguruHandler()
            itchat_handler.setFormatter(_logging.Formatter('%(message)s'))
            if not any(isinstance(h, ItchatLoguruHandler) for h in itchat_logger.handlers):
                itchat_logger.addHandler(itchat_handler)

            # 注册消息处理（只注册一次）
            if not self._msg_registered:
                @itchat.msg_register(TEXT)
                def text_reply(msg):
                    self._handle_text_message(msg)
                self._msg_registered = True

            def on_login():
                logger.info("微信登录确认成功，正在加载联系人...")
                self._notify_login_status("confirmed")

            # Monkey-patch check_login：加 sleep（阻止疯狂轮询）+ 记录服务器原始返回
            _original_check_login = itchat.instance.check_login

            def _check_login_with_throttle():
                import time as _time
                _time.sleep(1.0)
                result = _original_check_login()
                if result not in ('200', '201', '408'):
                    # 非正常状态码时记录，帮助诊断
                    logger.warning(f"[check_login] 状态码={result}, 时间={_time.strftime('%H:%M:%S')}")
                elif result == '201':
                    logger.debug(f"[check_login] 状态码=201 (等确认)")
                return result

            itchat.instance.check_login = _check_login_with_throttle

            # 先尝试热加载缓存，失败后再扫码
            if not use_hot_reload and Path(pkl_file).exists():
                logger.info("发现登录缓存，先尝试热加载...")
                try:
                    itchat.auto_login(
                        hotReload=True,
                        statusStorageDir=pkl_file,
                        loginCallback=on_login,
                    )
                    logger.info("热加载登录成功！")
                except Exception:
                    logger.info("热加载失败，重新扫码")

                    # 清理后重新调用
                    itchat.auto_login(
                        hotReload=False,
                        statusStorageDir=pkl_file,
                        loginCallback=on_login,
                    )
            else:
                logger.info("调用 itchat.auto_login（默认图片查看器显示二维码）")
                itchat.auto_login(
                    hotReload=use_hot_reload,
                    statusStorageDir=pkl_file,
                    loginCallback=on_login,
                )

            logger.info("itchat.auto_login 返回，正在验证登录状态...")

            # 验证 itchat 是否真正登录成功
            if itchat_instance and not getattr(itchat_instance, 'alive', False):
                logger.error("itchat.auto_login 返回但 alive=False，登录失败")
                self._notify_login_status("failed")
                return {
                    "success": False,
                    "message": "微信登录失败，可能是账号受限或网络问题",
                    "nickname": ""
                }

            # 登录成功
            self._logged_in = True
            try:
                friends = itchat.search_friends()
                if friends:
                    self._my_username = friends.get("UserName")
                    self._my_nickname = friends.get("NickName", "未知用户")
                else:
                    self._my_username = None
                    self._my_nickname = "未知用户"
            except Exception as e:
                logger.warning(f"获取用户信息失败: {e}")
                self._my_username = None
                self._my_nickname = "未知用户"

            logger.info(f"微信登录成功！用户: {self._my_nickname}")

            if self._login_success_callback:
                self._login_success_callback({
                    "nickname": self._my_nickname,
                    "username": self._my_username
                })

            return {"success": True, "message": "登录成功", "nickname": self._my_nickname}

        except SystemExit as e:
            logger.error(f"itchat 网络连接失败（SystemExit）: {e}")
            self._notify_login_status("failed")
            return {"success": False, "message": "无法连接微信服务器，请检查网络或微信版本", "nickname": ""}
        except Exception as e:
            import traceback
            logger.error(f"登录失败: {e}")
            logger.error(traceback.format_exc())
            self._notify_login_status("failed")
            return {"success": False, "message": f"登录失败: {str(e)}", "nickname": ""}

    def _notify_login_status(self, status: str):
        """通知登录状态变更"""
        if self._login_status_callback:
            self._login_status_callback(status)

    def start_listening(self):
        """在后台线程启动消息监听（非阻塞）"""
        if not self._logged_in:
            logger.error("未登录，无法启动消息监听")
            return

        if self._running:
            logger.info("消息监听已在运行")
            return

        self._running = True

        def _run():
            try:
                itchat.run(blockThread=True)
            except Exception as e:
                logger.error(f"消息监听异常: {e}")
                self._running = False

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        logger.info("微信消息监听已在后台启动")

    def start(self):
        """启动微信消息监听（阻塞，兼容旧接口）"""
        if itchat is None:
            logger.error("itchat未安装，无法启动")
            return

        logger.info("正在启动微信消息监听...")

        if not self._msg_registered:
            @itchat.msg_register(TEXT)
            def text_reply(msg):
                self._handle_text_message(msg)
            self._msg_registered = True

        if self.hot_reload:
            itchat.auto_login(
                hotReload=True,
                statusStorageDir="config/itchat.pkl"
            )
        else:
            itchat.auto_login()

        logger.info("微信登录成功！")
        self._logged_in = True
        self._running = True

        try:
            self._my_username = itchat.search_friends().get("UserName")
            self._my_nickname = itchat.search_friends().get("NickName", "未知用户")
        except Exception as e:
            logger.warning(f"获取用户信息失败: {e}")

        itchat.run(blockThread=True)

    def logout(self):
        """退出微信登录"""
        self._running = False
        self._logged_in = False
        self._my_username = None
        self._my_nickname = None
        if itchat:
            try:
                itchat.logout()
            except Exception as e:
                logger.warning(f"退出登录异常: {e}")
        logger.info("已退出微信登录")

    def send_message(self, to_username: str, message: str) -> bool:
        """主动发送消息"""
        if itchat is None or not self._logged_in:
            return False
        try:
            itchat.send(message, toUserName=to_username)
            logger.info(f"发送消息到 {to_username}: {message}")
            return True
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            return False

    def send_to_groups(self, group_names: List[str], message: str):
        """向指定群发送消息"""
        if itchat is None or not self._logged_in:
            return

        for group_name in group_names:
            try:
                chatrooms = itchat.search_chatrooms(name=group_name)
                if chatrooms:
                    chatroom = chatrooms[0]
                    itchat.send(message, toUserName=chatroom["UserName"])
                    logger.info(f"发送群消息到 [{group_name}]: {message}")

                    if self._message_log_callback:
                        self._message_log_callback({
                            "type": "notify",
                            "nickname": group_name,
                            "content": message[:50] + "..." if len(message) > 50 else message,
                            "is_group": True,
                            "time": time.strftime("%H:%M:%S")
                        })
                else:
                    logger.warning(f"未找到群聊: {group_name}")
            except Exception as e:
                logger.error(f"发送群消息失败 [{group_name}]: {e}")

    def get_friend_list(self) -> list:
        """获取好友列表"""
        if itchat is None:
            return []
        return itchat.get_friends()

    def get_chatroom_list(self) -> list:
        """获取群聊列表"""
        if itchat is None:
            return []
        return itchat.get_chatrooms()
