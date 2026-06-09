"""
LLM客户端模块
支持自定义API（兼容OpenAI格式）
"""

import requests
from loguru import logger
from typing import Optional, List, Dict, Callable


class LLMClient:
    """LLM API客户端"""

    def __init__(self, config: dict):
        """
        初始化LLM客户端

        Args:
            config: LLM配置字典，包含base_url, api_key, model等
        """
        self.base_url = config.get("base_url", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "default")
        self.temperature = config.get("temperature", 0.8)
        self.max_tokens = config.get("max_tokens", 500)
        self.system_prompt = config.get("system_prompt", "")

        # 会话历史（按用户ID存储）
        self._conversations: Dict[str, List[dict]] = {}
        # 每个会话保留的最大历史轮数
        self.max_history = 10
        # 动态信息回调（用于注入直播课表等实时信息到 system prompt）
        self._dynamic_info_callback: Optional[Callable] = None

    def set_dynamic_info_callback(self, callback: Callable[[], str]):
        """
        设置动态信息回调，用于在 system prompt 末尾注入实时信息（如直播课表）

        Args:
            callback: 返回要追加的文本的无参函数
        """
        self._dynamic_info_callback = callback

    def _build_system_prompt(self) -> str:
        """构建完整的 system prompt（基础人设 + 动态信息）"""
        prompt = self.system_prompt
        if self._dynamic_info_callback:
            try:
                extra = self._dynamic_info_callback()
                if extra:
                    prompt += f"\n\n{extra}"
            except Exception as e:
                logger.warning(f"获取动态信息失败: {e}")
        return prompt

    def chat(self, user_id: str, message: str) -> str:
        """
        与LLM对话

        Args:
            user_id: 用户唯一标识（微信用户名）
            message: 用户消息

        Returns:
            LLM回复内容
        """
        # 获取或创建会话历史
        if user_id not in self._conversations:
            self._conversations[user_id] = []

        # 添加用户消息到历史
        self._conversations[user_id].append({
            "role": "user",
            "content": message
        })

        # 截断历史，保留最近N轮
        if len(self._conversations[user_id]) > self.max_history * 2:
            self._conversations[user_id] = self._conversations[user_id][-self.max_history * 2:]

        # 构建请求消息
        messages = [{"role": "system", "content": self._build_system_prompt()}]
        messages.extend(self._conversations[user_id])

        # 调用API
        reply = self._call_api(messages)

        if reply:
            # 添加助手回复到历史
            self._conversations[user_id].append({
                "role": "assistant",
                "content": reply
            })
        else:
            # 调用失败，移除刚才添加的用户消息
            self._conversations[user_id].pop()

        return reply

    def _call_api(self, messages: List[dict]) -> Optional[str]:
        """
        调用LLM API

        Args:
            messages: 消息列表

        Returns:
            回复内容，失败返回None
        """
        # 确保base_url末尾没有斜杠，避免双斜杠
        base_url = self.base_url.rstrip("/")
        url = f"{base_url}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }

        try:
            logger.debug(f"请求URL: {url}")
            logger.debug(f"请求参数: model={self.model}, temperature={self.temperature}")

            response = requests.post(url, json=payload, headers=headers, timeout=120)

            # 记录详细错误信息
            if response.status_code != 200:
                logger.error(f"API返回错误: {response.status_code}")
                logger.error(f"响应内容: {response.text[:500]}")

            response.raise_for_status()

            data = response.json()
            reply = data["choices"][0]["message"]["content"].strip()

            logger.debug(f"LLM回复: {reply}")
            return reply

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API调用失败: {e}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"LLM响应解析失败: {e}")
            return None

    def clear_history(self, user_id: str):
        """
        清空用户会话历史

        Args:
            user_id: 用户唯一标识
        """
        if user_id in self._conversations:
            del self._conversations[user_id]
            logger.info(f"已清空用户 {user_id} 的会话历史")

    def get_history(self, user_id: str) -> List[dict]:
        """
        获取用户会话历史

        Args:
            user_id: 用户唯一标识

        Returns:
            消息列表
        """
        return self._conversations.get(user_id, [])
