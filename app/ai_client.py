import json
import requests
from typing import Dict, Any


class AIClient:
    def __init__(self, api_url: str, api_key: str, model: str, temperature: float, max_tokens: int):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def _endpoint(self) -> str:
        if self.api_url.endswith("/v1"):
            return f"{self.api_url}/chat/completions"
        return f"{self.api_url}/v1/chat/completions"

    def analyze(self, system_prompt: str, filter_prompt: str, style_prompt: str, content: str) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"筛选规则：\n{filter_prompt}\n\n"
                        f"文案风格：\n{style_prompt}\n\n"
                        "请输出JSON：{\n"
                        "  \"keep\": true/false,\n"
                        "  \"importance\": \"高\"|\"中\"|\"低\",\n"
                        "  \"type\": \"新作\"|\"发售\"|\"更新\"|\"行业\",\n"
                        "  \"summary\": \"一句话摘要\"\n"
                        "}\n\n"
                        f"内容：\n{content}"
                    ),
                },
            ],
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        r = requests.post(self._endpoint(), headers=headers, data=json.dumps(payload), timeout=60)
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]["content"]
        try:
            return json.loads(msg)
        except Exception:
            return {"keep": False, "importance": "低", "type": "行业", "summary": "(解析失败)"}
