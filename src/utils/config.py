"""
配置加载模块
"""

import os
import yaml
from pathlib import Path
from loguru import logger


def load_config(config_path: str = "config/config.yaml") -> dict:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典
    """
    path = Path(config_path)

    if not path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        logger.info(f"已加载配置文件: {config_path}")
        return config or {}

    except yaml.YAMLError as e:
        logger.error(f"配置文件解析失败: {e}")
        raise


def setup_logging(config: dict):
    """
    配置日志

    Args:
        config: 日志配置
    """
    log_config = config.get("logging", {})
    level = log_config.get("level", "INFO")
    log_file = log_config.get("file", "logs/bot.log")
    rotation = log_config.get("rotation", "10 MB")

    # 确保日志目录存在
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 配置loguru
    logger.remove()  # 移除默认处理器
    logger.add(
        log_file,
        rotation=rotation,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{function}:{line} - {message}",
        encoding="utf-8"
    )
    logger.add(
        lambda msg: print(msg, end=""),
        level=level,
        format="{time:HH:mm:ss} | {level: <8} | {message}"
    )

    logger.info(f"日志已配置: level={level}, file={log_file}")
