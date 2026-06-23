from dataclasses import dataclass
import base64
import json
import mimetypes
import re
from pathlib import Path
import zipfile
from xml.etree import ElementTree
import logging
import subprocess
import tempfile

import httpx

from app.core.config import get_settings
from app.models.analysis import AIAnalysisResult
from app.models.upload import UploadRecord


UNKNOWN = "未提及"
UNSURE = "无法判断"
logger = logging.getLogger(__name__)


@dataclass
class AnalysisPayload:
    raw_text: str
    summary: str
    customer_name: str
    customer_phone: str
    customer_address: str
    customer_needs: str
    customer_questions: str
    customer_objections: str
    product_interest: str
    budget: str
    purchase_time: str
    intent_level: str
    intent_score: int
    intent_reason: str
    evidence: str
    next_action: str
    sales_script: str
    model_name: str


class AIService:
    """AI access layer.

    Current behavior:
    - txt/md/csv/docx: extract text locally.
    - DeepSeek: used when DEEPSEEK_API_KEY exists.
    - Rule engine: fallback when no model key exists, so local testing can classify obvious high-intent data.
    - image: use DashScope Qwen-VL OCR when DASHSCOPE_API_KEY exists.
    - audio: use local Docker FunASR when ASR_PROVIDER=local_docker.
    - pdf: keep placeholder text until PDF parsing is connected.
    """

    def analyze_upload(self, upload: UploadRecord) -> AnalysisPayload:
        raw_text = self._extract_text(upload)
        return self.analyze_text(raw_text, upload.file_type)

    def analyze_text(self, raw_text: str, file_type: str = "document") -> AnalysisPayload:
        return self._analyze_text(self._clean_text(raw_text), file_type)

    def deepseek_status(self) -> dict:
        settings = get_settings()
        return {
            "configured": bool(settings.deepseek_api_key),
            "base_url": settings.deepseek_base_url,
            "model": settings.deepseek_model,
        }

    def recognition_status(self) -> dict:
        settings = get_settings()
        return {
            "ocr": {
                "configured": bool(settings.dashscope_api_key),
                "provider": "dashscope",
                "model": settings.dashscope_ocr_model,
                "base_url": settings.dashscope_base_url,
            },
            "asr": {
                "configured": settings.asr_provider == "local_docker" or bool(
                    settings.dashscope_api_key or settings.asr_api_key
                ),
                "provider": settings.asr_provider or "dashscope",
                "model": settings.dashscope_asr_model,
                "needs_audio_url": settings.asr_provider != "local_docker",
                "audio_base_url_configured": bool(settings.asr_audio_base_url),
            },
        }

    def test_deepseek(self) -> dict:
        settings = get_settings()
        if not settings.deepseek_api_key:
            return {
                "ok": False,
                "message": "DEEPSEEK_API_KEY 未配置，请先在 .env 文件中填写。",
                "model": settings.deepseek_model,
                "base_url": settings.deepseek_base_url,
            }

        sample_text = (
            "客户姓名：测试客户\n"
            "客户电话：13800000000\n"
            "客户询问报价、合同、付款方式和下周部署时间，希望今天发正式报价。"
        )
        try:
            payload = self._analyze_text_with_deepseek(sample_text)
        except Exception as exc:
            return {
                "ok": False,
                "message": str(exc),
                "model": settings.deepseek_model,
                "base_url": settings.deepseek_base_url,
            }

        return {
            "ok": True,
            "message": "DeepSeek 连接成功",
            "model": payload.model_name,
            "intent_level": payload.intent_level,
            "intent_score": payload.intent_score,
            "summary": payload.summary,
        }

    def _extract_text(self, upload: UploadRecord) -> str:
        file_path = Path(upload.file_path)
        suffix = file_path.suffix.lower()

        if upload.file_type == "document":
            if suffix in {".txt", ".md", ".csv"}:
                return self._read_plain_text(file_path)
            if suffix == ".docx":
                return self._read_docx_text(file_path)
            if suffix == ".pdf":
                return "PDF 文件已上传，但 PDF 文本解析暂未接入。请先用 txt/docx 测试意向判断。"
            return "文档已上传，但该文档格式暂未接入文本解析。"

        if upload.file_type == "audio":
            return self._extract_audio_text(file_path)

        if upload.file_type == "image":
            return self._extract_image_text(file_path)

        return "文件已上传，但文件类型暂不支持自动识别。"

    def _read_plain_text(self, file_path: Path) -> str:
        for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                text = file_path.read_text(encoding=encoding)
                return self._clean_text(text)
            except UnicodeDecodeError:
                continue
        return "文本文件编码无法识别，请转成 UTF-8 后重新上传。"

    def _read_docx_text(self, file_path: Path) -> str:
        try:
            with zipfile.ZipFile(file_path) as docx:
                xml = docx.read("word/document.xml")
        except Exception:
            return "Word 文档读取失败，请确认文件不是损坏或加密文档。"

        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs: list[str] = []

        for paragraph in root.findall(".//w:p", namespace):
            parts = [node.text for node in paragraph.findall(".//w:t", namespace) if node.text]
            line = "".join(parts).strip()
            if line:
                paragraphs.append(line)

        text = "\n".join(paragraphs)
        return self._clean_text(text) if text else "Word 文档中没有读取到可分析文字。"

    def _clean_text(self, text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()[:12000]

    def _extract_image_text(self, file_path: Path) -> str:
        settings = get_settings()
        if not settings.dashscope_api_key:
            return "图片已上传，但 DASHSCOPE_API_KEY 未配置。当前无法读取图片内容。"
        try:
            return self._ocr_image_with_dashscope(file_path)
        except Exception as exc:
            return f"图片识别失败：{exc}"

    def _ocr_image_with_dashscope(self, file_path: Path) -> str:
        settings = get_settings()
        mime_type = mimetypes.guess_type(file_path.name)[0] or "image/png"
        image_base64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
        data_url = f"data:{mime_type};base64,{image_base64}"
        response = httpx.post(
            f"{settings.dashscope_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.dashscope_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.dashscope_ocr_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是图片文字识别助手。只提取图片中真实出现的文字，保持原文，不要编造。",
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "请识别这张图片里的所有文字。如果是微信聊天截图，请按聊天顺序输出。"
                                    "只输出图片中能看到的文字，不要分析购买意向。"
                                ),
                            },
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                "temperature": 0,
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        text = self._clean_text(str(content))
        if not text:
            return "图片识别完成，但没有读取到文字。"
        return text

    def _extract_audio_text(self, file_path: Path) -> str:
        settings = get_settings()
        if settings.asr_provider == "local_docker":
            try:
                return self._transcribe_audio_with_docker(file_path)
            except Exception as exc:
                logger.exception("Local Docker FunASR transcription failed")
                return f"录音识别失败：{exc}"
        if not settings.dashscope_api_key and not settings.asr_api_key:
            return "录音已上传，但语音识别 Key 未配置。当前无法读取录音内容。"
        if not settings.asr_audio_base_url:
            return (
                "录音已上传，但当前语音识别还缺少可访问的音频地址配置。"
                "本地录音需要先上传到可访问地址或 OSS 后再调用录音文件识别。"
            )
        return f"录音已上传，等待语音识别接入音频地址：{file_path.name}"

    def _transcribe_audio_with_docker(self, file_path: Path) -> str:
        settings = get_settings()
        audio_path = file_path.resolve()
        if not audio_path.is_file():
            raise RuntimeError("录音文件不存在")

        with tempfile.TemporaryDirectory(prefix="sales-ai-funasr-") as output_dir:
            transcript_path = Path(output_dir) / "transcript.txt"
            command = [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{audio_path.parent}:/audio:ro",
                "-v",
                f"{output_dir}:/output",
                "-v",
                "sales_ai_funasr_cache:/root/.cache",
                settings.funasr_docker_image,
                f"/audio/{audio_path.name}",
                "/output/transcript.txt",
            ]
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=settings.funasr_docker_timeout,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                raise RuntimeError(detail or "Docker FunASR 执行失败")
            if not transcript_path.is_file():
                raise RuntimeError("FunASR 未生成转写文件")
            transcript = self._clean_text(transcript_path.read_text(encoding="utf-8"))
            if not transcript:
                raise RuntimeError("录音中没有识别到有效文字")
            return transcript

    def _analyze_text(self, raw_text: str, file_type: str) -> AnalysisPayload:
        settings = get_settings()
        if settings.deepseek_api_key and self._has_meaningful_text(raw_text):
            try:
                return self._analyze_text_with_deepseek(raw_text)
            except Exception:
                logger.exception("DeepSeek analysis failed; falling back to local rules")
        return self._analyze_text_with_rules(raw_text, file_type)

    def _has_meaningful_text(self, raw_text: str) -> bool:
        blocked = (
            "尚未接入", "无法读取", "暂未接入", "暂不支持", "读取失败", "编码无法识别",
            "识别失败", "未配置", "缺少可访问", "等待语音识别",
        )
        return bool(raw_text and len(raw_text.strip()) >= 20 and not any(word in raw_text for word in blocked))

    def _analyze_text_with_rules(self, raw_text: str, file_type: str) -> AnalysisPayload:
        if not self._has_meaningful_text(raw_text):
            return AnalysisPayload(
                raw_text=raw_text,
                summary="资料已接收，但当前没有可用于判断的真实文本内容。",
                customer_name=UNKNOWN,
                customer_phone=UNKNOWN,
                customer_address=UNKNOWN,
                customer_needs=UNKNOWN,
                customer_questions=UNKNOWN,
                customer_objections=UNKNOWN,
                product_interest=UNKNOWN,
                budget=UNKNOWN,
                purchase_time=UNKNOWN,
                intent_level=UNSURE,
                intent_score=0,
                intent_reason="当前文件内容无法被读取，或对应识别服务尚未接入。",
                evidence=UNKNOWN,
                next_action="请上传 txt/docx 测试文档，或接入图片识别、语音识别后重新分析。",
                sales_script="暂无推荐话术。",
                model_name=f"rule-fallback-{file_type}",
            )

        phone = self._extract_phone(raw_text)
        name = self._extract_name(raw_text)
        budget = self._extract_budget(raw_text)
        purchase_time = self._extract_purchase_time(raw_text)
        product = self._extract_product(raw_text)
        score, signals = self._score_intent(raw_text)
        intent_level = self._intent_level(score, raw_text)

        needs = self._infer_needs(raw_text)
        questions = self._infer_questions(raw_text)
        objections = self._infer_objections(raw_text)
        evidence = "；".join(signals[:6]) if signals else UNKNOWN
        next_action = self._next_action(intent_level, purchase_time)

        return AnalysisPayload(
            raw_text=raw_text,
            summary=self._summary(intent_level, needs, budget, purchase_time),
            customer_name=name or UNKNOWN,
            customer_phone=phone or UNKNOWN,
            customer_address=UNKNOWN,
            customer_needs=needs,
            customer_questions=questions,
            customer_objections=objections,
            product_interest=product,
            budget=budget or UNKNOWN,
            purchase_time=purchase_time or UNKNOWN,
            intent_level=intent_level,
            intent_score=score,
            intent_reason=self._intent_reason(intent_level, signals),
            evidence=evidence,
            next_action=next_action,
            sales_script=self._sales_script(intent_level, budget, purchase_time),
            model_name=f"rule-fallback-{file_type}",
        )

    def _extract_phone(self, text: str) -> str | None:
        match = re.search(r"(?<!\d)1[3-9]\d{9}(?!\d)", text)
        return match.group(0) if match else None

    def _extract_name(self, text: str) -> str | None:
        patterns = [
            r"客户姓名[：:\s]*([\u4e00-\u9fa5A-Za-z]{2,12})",
            r"客户[：:\s]*([\u4e00-\u9fa5A-Za-z]{2,12})",
            r"([\u4e00-\u9fa5]{1,4}(?:先生|女士|总|经理))",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()
        return None

    def _extract_budget(self, text: str) -> str | None:
        match = re.search(r"预算[^。\n，,：:]*[：:\s]*([^。\n]+)", text)
        if match:
            return match.group(1).strip()[:80]
        match = re.search(r"(\d+\s*[万千元][^。\n，,]*到\s*\d+\s*[万千元]|\d+\s*[-~—]\s*\d+\s*[万千元])", text)
        return match.group(1).strip() if match else None

    def _extract_purchase_time(self, text: str) -> str | None:
        keywords = ["今天", "明天", "本周", "周五", "下周", "月底", "尽快", "马上", "近期"]
        for line in text.splitlines():
            if any(word in line for word in keywords) and any(word in line for word in ["确认", "购买", "部署", "安装", "上线", "合同", "电话"]):
                return line.strip()[:100]
        return None

    def _extract_product(self, text: str) -> str:
        patterns = [
            r"关注产品[：:\s]*([^。\n]+)",
            r"产品[：:\s]*([^。\n]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1).strip()[:120]
        if "AI" in text or "意向分析" in text:
            return "AI 销售线索分析系统"
        return UNKNOWN

    def _score_intent(self, text: str) -> tuple[int, list[str]]:
        signal_groups = [
            (20, ["报价", "价格", "费用", "多少钱", "优惠"], "客户询问价格/报价"),
            (20, ["合同", "合同模板", "服务内容", "条款"], "客户要求合同或条款"),
            (18, ["付款", "尾款", "一次性付款", "分阶段付款"], "客户询问付款方式"),
            (18, ["部署", "安装", "上线", "交付"], "客户询问部署/交付时间"),
            (16, ["今天", "明天", "本周", "下周", "尽快", "马上"], "客户提到明确时间"),
            (12, ["老板确认", "给老板", "确认方案", "确定方案"], "客户进入内部确认阶段"),
            (12, ["想了解", "了解一下", "安排演示", "先演示", "演示"], "客户希望了解或演示产品"),
            (12, ["对比", "比较", "价格合适", "再考虑"], "客户正在比较方案"),
            (10, ["预算", "8 万", "12 万", "可以接受"], "客户提到预算或可接受范围"),
            (8, ["电话确认", "回访", "跟进"], "客户约定下一次沟通"),
        ]
        score = 0
        signals: list[str] = []
        for points, words, label in signal_groups:
            if any(word in text for word in words):
                score += points
                signals.append(label)

        if any(word in text for word in ["不需要", "不用了", "没预算", "暂不考虑", "拒绝"]):
            score -= 45
            signals.append("客户出现拒绝或暂不考虑信号")

        return max(0, min(score, 95)), signals

    def _intent_level(self, score: int, text: str) -> str:
        if any(word in text for word in ["不需要", "不用了", "没预算", "暂不考虑", "拒绝"]) and score < 50:
            return "暂无意向"
        if score >= 75:
            return "高意向"
        if score >= 45:
            return "中意向"
        if score >= 20:
            return "低意向"
        return UNSURE

    def _infer_needs(self, text: str) -> str:
        if "意向" in text and ("录音" in text or "图片" in text or "聊天截图" in text):
            return "希望通过系统自动识别图片、录音或聊天截图，并判断客户购买意向。"
        if "部署" in text or "上线" in text:
            return "希望尽快确认方案并完成系统部署。"
        return UNKNOWN

    def _infer_questions(self, text: str) -> str:
        questions = []
        if any(word in text for word in ["报价", "价格", "费用", "多少钱", "优惠"]):
            questions.append("报价/优惠")
        if any(word in text for word in ["付款", "尾款", "一次性付款"]):
            questions.append("付款方式")
        if any(word in text for word in ["部署", "安装", "上线", "交付"]):
            questions.append("部署交付时间")
        if "合同" in text:
            questions.append("合同内容")
        return "、".join(questions) if questions else UNKNOWN

    def _infer_objections(self, text: str) -> str:
        objections = []
        if "担心" in text and "价格" in text:
            objections.append("担心价格")
        if "老板确认" in text or "给老板" in text:
            objections.append("需要老板确认")
        if "上线速度" in text or "尽快" in text:
            objections.append("关注上线速度")
        return "、".join(objections) if objections else UNKNOWN

    def _summary(self, intent_level: str, needs: str, budget: str | None, purchase_time: str | None) -> str:
        parts = [f"客户当前被判断为{intent_level}。"]
        if needs != UNKNOWN:
            parts.append(needs)
        if budget:
            parts.append(f"预算信息：{budget}。")
        if purchase_time:
            parts.append(f"购买/跟进时间：{purchase_time}。")
        return "".join(parts)

    def _intent_reason(self, intent_level: str, signals: list[str]) -> str:
        if not signals:
            return "资料中缺少明确购买信号。"
        return f"判断为{intent_level}，因为：" + "；".join(signals[:6]) + "。"

    def _next_action(self, intent_level: str, purchase_time: str | None) -> str:
        if intent_level == "高意向":
            return "建议当天电话跟进，发送正式报价单和合同模板，并确认付款与部署时间。"
        if intent_level == "中意向":
            return "建议补充方案、案例和报价说明，约定下一次沟通时间。"
        if intent_level == "低意向":
            return "建议先保留线索，发送基础资料，后续再回访。"
        return "建议补充更多客户资料后重新分析。"

    def _sales_script(self, intent_level: str, budget: str | None, purchase_time: str | None) -> str:
        if intent_level == "高意向":
            budget_text = f"我看到您预算大概是{budget}，" if budget else ""
            time_text = f"也提到{purchase_time}，" if purchase_time else ""
            return f"您好，{budget_text}{time_text}我这边可以先把正式报价和合同模板发您，方便您今天确认。"
        return "您好，我这边根据您的需求整理了一份方案，您看我什么时候方便和您确认下一步？"

    def _analyze_text_with_deepseek(self, raw_text: str) -> AnalysisPayload:
        settings = get_settings()
        prompt = self._build_analysis_prompt(raw_text)
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.deepseek_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是销售线索分析助手。必须严格根据输入内容输出 JSON，不确定就写未提及或无法判断，禁止编造。",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        data = self._parse_deepseek_json(content)
        return AnalysisPayload(
            raw_text=raw_text,
            summary=data.get("summary", UNKNOWN),
            customer_name=data.get("customer_name", UNKNOWN),
            customer_phone=data.get("customer_phone", UNKNOWN),
            customer_address=data.get("customer_address", UNKNOWN),
            customer_needs=data.get("customer_needs", UNKNOWN),
            customer_questions=data.get("customer_questions", UNKNOWN),
            customer_objections=data.get("customer_objections", UNKNOWN),
            product_interest=data.get("product_interest", UNKNOWN),
            budget=data.get("budget", UNKNOWN),
            purchase_time=data.get("purchase_time", UNKNOWN),
            intent_level=self._normalize_intent_level(data.get("intent_level", UNSURE)),
            intent_score=self._normalize_score(data.get("intent_score", 0)),
            intent_reason=data.get("intent_reason", UNSURE),
            evidence=data.get("evidence", UNKNOWN),
            next_action=data.get("next_action", UNKNOWN),
            sales_script=data.get("sales_script", UNKNOWN),
            model_name=settings.deepseek_model,
        )

    def _build_analysis_prompt(self, raw_text: str) -> str:
        return f"""
请分析下面的客户资料，输出合法 JSON。

规则：
1. 只能根据输入内容判断，不能猜测。
2. 没有出现的信息统一写“未提及”。
3. 证据不足时，intent_level 写“无法判断”，intent_score 写 0。
4. 不允许编造手机号、姓名、价格、地址、购买时间。
5. intent_level 只能是：高意向、中意向、低意向、暂无意向、无法判断。
6. intent_score 必须是 0-100 的整数。
7. evidence 必须写出判断依据；没有依据写“未提及”。

输出字段：
summary, customer_name, customer_phone, customer_address, customer_needs,
customer_questions, customer_objections, product_interest, budget, purchase_time,
intent_level, intent_score, intent_reason, evidence, next_action, sales_script

JSON 示例：
{{
  "summary": "客户询问报价、合同和部署时间，购买意向较强。",
  "customer_name": "王先生",
  "customer_phone": "13800000000",
  "customer_address": "未提及",
  "customer_needs": "希望购买 AI 销售线索分析系统",
  "customer_questions": "报价、合同、部署时间",
  "customer_objections": "需要老板确认",
  "product_interest": "AI 销售线索分析系统",
  "budget": "未提及",
  "purchase_time": "下周部署",
  "intent_level": "高意向",
  "intent_score": 88,
  "intent_reason": "客户询问报价、合同和部署时间。",
  "evidence": "客户提到报价、合同、下周部署。",
  "next_action": "尽快发送正式报价和合同模板。",
  "sales_script": "您好，我这边先把正式报价和合同模板发您。"
}}

客户资料：
{raw_text}
""".strip()

    def _parse_deepseek_json(self, content: str) -> dict:
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?", "", content).strip()
            content = re.sub(r"```$", "", content).strip()
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.S)
            if not match:
                raise
            data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise ValueError("DeepSeek 返回结果不是 JSON 对象")
        return data

    def _normalize_intent_level(self, value: object) -> str:
        allowed = {"高意向", "中意向", "低意向", "暂无意向", "无法判断"}
        text = str(value or "").strip()
        return text if text in allowed else UNSURE

    def _normalize_score(self, value: object) -> int:
        try:
            score = int(float(value))
        except (TypeError, ValueError):
            return 0
        return max(0, min(score, 100))


def build_analysis_result(upload: UploadRecord, payload: AnalysisPayload) -> AIAnalysisResult:
    return AIAnalysisResult(
        upload_record_id=upload.id,
        customer_id=upload.customer_id,
        raw_text=payload.raw_text,
        summary=payload.summary,
        customer_name=payload.customer_name,
        customer_phone=payload.customer_phone,
        customer_address=payload.customer_address,
        customer_needs=payload.customer_needs,
        customer_questions=payload.customer_questions,
        customer_objections=payload.customer_objections,
        product_interest=payload.product_interest,
        budget=payload.budget,
        purchase_time=payload.purchase_time,
        intent_level=payload.intent_level,
        intent_score=payload.intent_score,
        intent_reason=payload.intent_reason,
        evidence=payload.evidence,
        next_action=payload.next_action,
        sales_script=payload.sales_script,
        model_name=payload.model_name,
    )
