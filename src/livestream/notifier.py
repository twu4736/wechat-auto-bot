"""
直播通知模块
实现定时直播提醒和活动通知功能
"""

import threading
import uuid
from datetime import datetime, timedelta
from typing import List, Callable, Optional, Dict
from loguru import logger

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:
    logger.warning("apscheduler未安装，请运行: pip install apscheduler")
    BackgroundScheduler = None


DAY_MAP = {
    "周一": 0, "周二": 1, "周三": 2, "周四": 3,
    "周五": 4, "周六": 5, "周日": 6,
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6
}


class LivestreamNotifier:
    """直播通知管理器"""

    def __init__(self, config: dict):
        self.config = config
        self.room_name = config.get("room_name", "直播间")
        self.room_url = config.get("room_url", "")
        self.notify_groups = config.get("notify_groups", [])
        self.notify_before = config.get("notify_before", 30)

        # 课表（带ID的动态列表）
        raw_schedule = config.get("schedule", [])
        self._schedule: List[Dict] = []
        for item in raw_schedule:
            self._schedule.append({
                "id": str(uuid.uuid4())[:8],
                "day": item.get("day", ""),
                "time": item.get("time", "20:00"),
                "content": item.get("content", "直播开始啦")
            })

        self._send_callback: Optional[Callable] = None
        self._scheduler = None
        self._is_live = False
        self._current_activity = ""
        self._running = False

    def set_send_callback(self, callback: Callable[[List[str], str], None]):
        """设置发送消息的回调"""
        self._send_callback = callback

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def schedule(self) -> List[Dict]:
        """返回当前课表（只读）"""
        return list(self._schedule)

    def start(self):
        """启动定时通知任务"""
        if BackgroundScheduler is None:
            logger.error("apscheduler未安装，无法启动定时任务")
            return

        if self._running:
            logger.info("直播通知已在运行")
            return

        self._scheduler = BackgroundScheduler()
        self._rebuild_jobs()
        self._scheduler.start()
        self._running = True
        logger.info("直播通知调度器已启动")

    def _rebuild_jobs(self):
        """重建所有定时任务"""
        if not self._scheduler:
            return

        # 移除所有现有任务
        for job in self._scheduler.get_jobs():
            self._scheduler.remove_job(job.id)

        # 根据当前课表创建任务
        for item in self._schedule:
            self._add_job(item)

    def _add_job(self, item: Dict):
        """添加单个定时任务"""
        if not self._scheduler:
            return

        day = item.get("day", "")
        time_str = item.get("time", "20:00")
        content = item.get("content", "直播开始啦")
        item_id = item.get("id", "")

        day_of_week = DAY_MAP.get(day.lower(), None)
        if day_of_week is None:
            logger.warning(f"无法解析星期: {day}")
            return

        try:
            hour, minute = map(int, time_str.split(":"))
        except ValueError:
            logger.warning(f"无法解析时间: {time_str}")
            return

        notify_hour = hour
        notify_minute = minute - self.notify_before
        if notify_minute < 0:
            notify_minute += 60
            notify_hour -= 1
        if notify_hour < 0:
            notify_hour += 24

        self._scheduler.add_job(
            self._send_notification,
            trigger=CronTrigger(
                day_of_week=day_of_week,
                hour=notify_hour,
                minute=notify_minute
            ),
            args=[content],
            id=f"livestream_{item_id}",
            name=f"直播通知: {content}",
            replace_existing=True
        )
        logger.info(f"已添加直播通知: {day} {time_str} - {content}")

    def stop(self):
        """停止定时通知任务"""
        if self._scheduler:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None
        self._running = False
        logger.info("直播通知调度器已停止")

    def add_schedule(self, day: str, time_str: str, content: str) -> Dict:
        """
        添加直播时间条目

        Returns:
            新增的课表条目
        """
        item = {
            "id": str(uuid.uuid4())[:8],
            "day": day,
            "time": time_str,
            "content": content
        }
        self._schedule.append(item)

        # 如果调度器在运行，直接添加任务
        if self._running and self._scheduler:
            self._add_job(item)

        logger.info(f"已添加直播时间: {day} {time_str} - {content}")
        return item

    def remove_schedule(self, item_id: str) -> bool:
        """
        删除直播时间条目

        Args:
            item_id: 条目ID

        Returns:
            是否删除成功
        """
        for i, item in enumerate(self._schedule):
            if item["id"] == item_id:
                self._schedule.pop(i)
                # 如果调度器在运行，移除任务
                if self._running and self._scheduler:
                    try:
                        self._scheduler.remove_job(f"livestream_{item_id}")
                    except Exception:
                        pass
                logger.info(f"已删除直播时间: {item['day']} {item['time']}")
                return True
        return False

    def update_schedule(self, item_id: str, day: str = None, time_str: str = None, content: str = None) -> bool:
        """更新直播时间条目"""
        for item in self._schedule:
            if item["id"] == item_id:
                if day is not None:
                    item["day"] = day
                if time_str is not None:
                    item["time"] = time_str
                if content is not None:
                    item["content"] = content

                # 重建该任务
                if self._running and self._scheduler:
                    try:
                        self._scheduler.remove_job(f"livestream_{item_id}")
                    except Exception:
                        pass
                    self._add_job(item)

                logger.info(f"已更新直播时间: {item_id}")
                return True
        return False

    def _send_notification(self, content: str):
        """发送直播通知"""
        if not self._send_callback:
            logger.warning("未设置发送回调，无法发送通知")
            return

        message = self._build_notification(content)
        self._send_callback(self.notify_groups, message)
        logger.info(f"已发送直播通知: {content}")

    def _build_notification(self, content: str) -> str:
        """构建通知消息"""
        import random
        templates = [
            f"🔔 叮咚！宝子们注意啦~\n\n"
            f"📺 {content}\n"
            f"⏰ 还有{self.notify_before}分钟就要开始啦！\n"
            f"🔗 直播间: {self.room_url}\n\n"
            f"快来占座吧~小七等你们哦~🥰✨",

            f"📢 家人们！家人们！\n\n"
            f"✨ {content} ✨\n"
            f"马上就要开播啦！还有{self.notify_before}分钟~\n"
            f"📺 直播间链接: {self.room_url}\n\n"
            f"不见不散哦~💕",

            f"🎵 滴滴滴~直播预告来啦！\n\n"
            f"🎬 今日直播: {content}\n"
            f"⏱️ {self.notify_before}分钟后开播\n"
            f"👉 {self.room_url}\n\n"
            f"宝子们快来呀~💖"
        ]
        return random.choice(templates)

    def send_custom_notification(self, content: str, activity: str = ""):
        """发送自定义通知"""
        if activity:
            message = f"🎉 活动通知 🎉\n\n{activity}\n\n{content}"
        else:
            message = f"📢 通知\n\n{content}"

        if self._send_callback:
            self._send_callback(self.notify_groups, message)

    def set_live_status(self, is_live: bool, activity: str = ""):
        """设置直播状态"""
        self._is_live = is_live
        self._current_activity = activity
        if is_live:
            logger.info(f"直播开始: {activity}")
        else:
            logger.info("直播结束")

    def get_live_info(self) -> dict:
        """获取当前直播信息"""
        return {
            "is_live": self._is_live,
            "room_name": self.room_name,
            "room_url": self.room_url,
            "current_activity": self._current_activity,
            "schedule": self._schedule
        }

    def get_schedule_text(self) -> str:
        """获取直播时间表文本"""
        if not self._schedule:
            return "暂无直播安排哦~"

        text = f"📺 {self.room_name} 直播时间表\n\n"
        for item in self._schedule:
            text += f"• {item['day']} {item['time']} - {item['content']}\n"
        text += f"\n🔗 直播间: {self.room_url}"
        return text

    def get_next_notification(self) -> Optional[Dict]:
        """获取下一次通知的时间"""
        if not self._running or not self._scheduler:
            return None

        jobs = self._scheduler.get_jobs()
        if not jobs:
            return None

        # 找到最近的一次触发
        next_run = None
        next_job = None
        for job in jobs:
            if job.next_run_time:
                if next_run is None or job.next_run_time < next_run:
                    next_run = job.next_run_time
                    next_job = job

        if next_job and next_run:
            return {
                "name": next_job.name,
                "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S"),
                "content": next_job.args[0] if next_job.args else ""
            }
        return None

    def get_status(self) -> dict:
        """获取通知器状态"""
        return {
            "running": self._running,
            "is_live": self._is_live,
            "current_activity": self._current_activity,
            "schedule_count": len(self._schedule),
            "notify_groups": self.notify_groups,
            "notify_before": self.notify_before,
            "next_notification": self.get_next_notification()
        }
