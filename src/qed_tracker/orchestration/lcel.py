"""LangChain adapter that preserves QED-Tracker's LlmClient boundary."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict


class LlmChatModel(BaseChatModel):
    """Thin LCEL model that delegates every completion to the existing client."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    client: Any

    def __init__(self, client: Any, **kwargs: Any) -> None:
        super().__init__(client=client, **kwargs)

    @property
    def _llm_type(self) -> str:
        return "qed-tracker-llm-client"

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        del stop, run_manager
        role_map = {"human": "user", "ai": "assistant", "system": "system"}
        payload = [
            {"role": role_map.get(message.type, message.type), "content": str(message.content)}
            for message in messages
        ]
        content = self.client.complete(payload, prompt_template=str(kwargs.get("prompt_template", "")))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])
