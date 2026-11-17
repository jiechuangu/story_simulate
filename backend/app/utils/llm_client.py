"""
LLM 客户端封装（OpenAI 兼容接口）。
"""

import json
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from ..config import Config
from .logger import get_logger

logger = get_logger("story.llm")

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>", re.IGNORECASE)
_FENCE_START = re.compile(r"^```(?:json)?\s*\n?", re.IGNORECASE)
_FENCE_END = re.compile(r"\n?```\s*$")


class LLMClient:
    def __init__(self, model: Optional[str] = None):
        if not Config.LLM_API_KEY:
            raise ValueError("LLM_API_KEY 未配置")
        self.model = model or Config.LLM_MODEL_NAME
        self.client = OpenAI(
            api_key=Config.LLM_API_KEY,
            base_url=Config.LLM_BASE_URL,
            timeout=Config.LLM_TIMEOUT,
        )
        # 部分兼容接口不支持 response_format，失败一次后自动关闭
        self._json_mode_supported = True

    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        json_mode: bool = False,
        retries: int = 2,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and self._json_mode_supported:
            kwargs["response_format"] = {"type": "json_object"}

        last_exc: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                choice = response.choices[0]
                content = choice.message.content or ""
                # 输出被 max_tokens 截断（推理模型的思考过程也占额度）：加大额度重试，而不是返回半截内容
                while choice.finish_reason == "length" and kwargs["max_tokens"] < Config.LLM_MAX_TOKENS_CAP:
                    kwargs["max_tokens"] = min(kwargs["max_tokens"] * 2, Config.LLM_MAX_TOKENS_CAP)
                    logger.warning("输出被截断，加大 max_tokens 到 %s 后重试", kwargs["max_tokens"])
                    response = self.client.chat.completions.create(**kwargs)
                    choice = response.choices[0]
                    content = choice.message.content or ""
                if choice.finish_reason == "length":
                    logger.warning("输出在 max_tokens=%s 时仍被截断", kwargs["max_tokens"])
                return _THINK_RE.sub("", content).strip()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                text = str(exc).lower()
                if "response_format" in kwargs and ("response_format" in text or "json_object" in text):
                    logger.warning("接口不支持 response_format，改为普通模式")
                    self._json_mode_supported = False
                    kwargs.pop("response_format", None)
                    continue
                if attempt < retries:
                    wait = 2 * (attempt + 1)
                    logger.warning("LLM 调用失败（%s），%s 秒后重试", exc, wait)
                    time.sleep(wait)
        raise RuntimeError(f"LLM 调用失败: {last_exc}")

    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        raw = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)
        parsed = self._parse(raw)
        if parsed is not None:
            return parsed
        # 让模型修一次
        repaired = self.chat(
            [
                {"role": "system", "content": "把用户给出的内容转成一个合法 JSON 对象，保留字段结构。只输出 JSON。"},
                {"role": "user", "content": raw},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
            json_mode=True,
        )
        parsed = self._parse(repaired)
        if parsed is None:
            raise ValueError(f"LLM 返回的 JSON 无法解析: {raw[:500]}")
        return parsed

    @staticmethod
    def _parse(text: str) -> Optional[Dict[str, Any]]:
        cleaned = _FENCE_END.sub("", _FENCE_START.sub("", text.strip())).strip()
        try:
            data = json.loads(cleaned)
            return data if isinstance(data, dict) else {"items": data}
        except json.JSONDecodeError:
            pass
        start = cleaned.find("{")
        if start == -1:
            return None
        depth, in_str, esc = 0, False, False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(cleaned[start : i + 1])
                    except json.JSONDecodeError:
                        return None
        return None
