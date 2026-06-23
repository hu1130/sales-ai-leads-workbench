from __future__ import annotations

import json
from urllib import request

from app.config import settings


SUMMARY_PROMPT = """你是销售管理系统助手。请根据下面的电话转写，生成结构化跟进摘要。

要求：
1. 只基于原文，不要编造。
2. 如果信息不存在，写“未提及”。
3. 输出中文。

格式：
客户意向：
关键需求：
报价/产品：
异议点：
承诺事项：
下次跟进时间：
销售待办：
风险提醒：

电话转写：
{transcript}
"""


def summarize_transcript(transcript: str) -> str:
    payload = json.dumps(
        {
            "model": settings.ollama_model,
            "prompt": SUMMARY_PROMPT.format(transcript=transcript),
            "stream": False,
        }
    ).encode("utf-8")
    req = request.Request(
        settings.ollama_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=180) as response:
        data = json.loads(response.read().decode("utf-8"))
    return str(data.get("response", "")).strip()
