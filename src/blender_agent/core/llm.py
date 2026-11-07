import base64
import time

from openai import OpenAI

from blender_agent.config import ModelProvider
from blender_agent.core.types import ChatMessage


class LLMClient:
    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self._client = OpenAI(base_url=provider.base_url, api_key=provider.api_key)

    def chat(self, messages: list[ChatMessage], tools: list[dict] | None = None,
             max_retries: int = 3, response_format: dict | None = None) -> ChatMessage:
        payload = [self._to_oai(m) for m in messages]
        last_err = None
        for attempt in range(max_retries):
            try:
                kwargs = dict(model=self.provider.model,
                              messages=payload,
                              max_tokens=self.provider.max_tokens,
                              temperature=self.provider.temperature)
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                if response_format:
                    kwargs["response_format"] = response_format
                resp = self._client.chat.completions.create(**kwargs)
                return self._from_oai(resp)
            except Exception as e:  # noqa: 限速/网络抖动退避重试；退避上限压短，避免单调用挂几分钟
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(min(3 * 2 ** attempt, 15))  # 3/6/12 秒
        raise RuntimeError(f"LLM 调用失败（重试 {max_retries} 次）: {last_err}")

    def _to_oai(self, m: ChatMessage) -> dict:
        from blender_agent.core.images import shrink_image
        if m.images:  # 多模态：压缩后再传（大 PNG 是视觉调用延迟与限速的主因）
            content = [{"type": "text", "text": m.content or ""}]
            for img in m.images:
                small = shrink_image(img)
                mime = "image/jpeg" if small is not img else "image/png"
                b64 = base64.b64encode(small).decode()
                content.append({"type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{b64}"}})
        else:
            content = m.content or ""
        d = {"role": m.role, "content": content}
        if m.tool_calls:
            d["tool_calls"] = m.tool_calls
        if m.tool_call_id:
            d["tool_call_id"] = m.tool_call_id
        return d

    def _from_oai(self, resp) -> ChatMessage:
        c = resp.choices[0].message
        return ChatMessage(
            role="assistant",
            content=c.content or "",
            tool_calls=[tc.model_dump() for tc in c.tool_calls] if c.tool_calls else [],
        )


class FakeLLM:
    """测试用：按队列返回预设消息，耗尽后回退到空消息。"""

    def __init__(self, responses: list[ChatMessage]):
        self._q = list(responses)
        self.calls = []

    def chat(self, messages, tools=None, max_retries=3, response_format=None) -> ChatMessage:
        self.calls.append(messages)
        if self._q:
            return self._q.pop(0)
        return ChatMessage(role="assistant", content="")
