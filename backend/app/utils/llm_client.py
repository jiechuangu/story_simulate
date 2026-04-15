"""
LLM客户端封装
统一使用OpenAI格式调用
"""

import json
import re
from typing import Optional, Dict, Any, List
from openai import OpenAI

from ..config import Config


class LLMClient:
    """LLM客户端"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or Config.LLM_API_KEY
        self.base_url = base_url or Config.LLM_BASE_URL
        self.model = model or Config.LLM_MODEL_NAME
        
        if not self.api_key:
            raise ValueError("LLM_API_KEY 未配置")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: Optional[Dict] = None
    ) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            response_format: 响应格式（如JSON模式）
            
        Returns:
            模型响应文本
        """
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if response_format:
            kwargs["response_format"] = response_format
        
        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        # 部分模型（如MiniMax M2.5）会在content中包含<think>思考内容，需要移除
        content = re.sub(r'<think>[\s\S]*?</think>', '', content).strip()
        return content
    
    def chat_json(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        """
        发送聊天请求并返回JSON
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            解析后的JSON对象
        """
        response = self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"}
        )
        # 清理markdown代码块标记
        cleaned_response = response.strip()
        cleaned_response = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_response, flags=re.IGNORECASE)
        cleaned_response = re.sub(r'\n?```\s*$', '', cleaned_response)
        cleaned_response = cleaned_response.strip()

        try:
            return json.loads(cleaned_response)
        except json.JSONDecodeError:
            extracted = self._extract_json_object(cleaned_response)
            if extracted is not None:
                return extracted

            repaired = self._repair_json_response(cleaned_response)
            if repaired is not None:
                return repaired

            raise ValueError(f"LLM返回的JSON格式无效: {cleaned_response}")

    def _extract_json_object(self, text: str) -> Optional[Dict[str, Any]]:
        """
        尝试从混合文本中提取第一个完整 JSON 对象
        """
        start = text.find('{')
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = False
                continue

            if ch == '"':
                in_string = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    candidate = text[start:idx + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
        return None

    def _repair_json_response(self, bad_response: str) -> Optional[Dict[str, Any]]:
        """
        当模型没有按要求返回 JSON 时，发起一次轻量修复请求
        """
        repair_messages = [
            {
                "role": "system",
                "content": (
                    "你是 JSON 修复器。"
                    "你会把用户提供的文本转换为单个有效 JSON 对象。"
                    "只输出 JSON，不要解释，不要 markdown。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "请把下面的内容改写为一个合法 JSON 对象。"
                    "如果原文是结构化设计说明，请尽量保留字段层次。原文如下：\n\n"
                    f"{bad_response}"
                ),
            },
        ]

        repaired_text = self.chat(
            messages=repair_messages,
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"}
        )
        repaired_text = repaired_text.strip()
        repaired_text = re.sub(r'^```(?:json)?\s*\n?', '', repaired_text, flags=re.IGNORECASE)
        repaired_text = re.sub(r'\n?```\s*$', '', repaired_text).strip()

        try:
            return json.loads(repaired_text)
        except json.JSONDecodeError:
            return self._extract_json_object(repaired_text)
