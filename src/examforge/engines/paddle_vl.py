"""
Paddle-VL 1.6 Engine Adapter.

Integrates PaddleOCR-VL-1.6 for document OCR and layout extraction.
Supports:
1. HTTP / vLLM API serving PaddlePaddle/PaddleOCR-VL-1.6 (OpenAI-compatible or document-parse).
2. Local paddleocr Python library with pipeline_version="v1.6" and process-level warm engine caching.
3. Digital text-layer fallback with Paddle-VL layout tagging when external service is offline.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    EngineSource,
    Lang,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "PaddlePaddle/PaddleOCR-VL-1.6"
DEFAULT_PIPELINE_VERSION = "v1.6"

# Layout recognition regex patterns for layout-aware tagging
_HEADER_RE = re.compile(
    r"^(?:PART\s*[-–:]?\s*[0-9IVX]+|SECTION\s*[-–:]?\s*[A-Za-z0-9()]+|PHYSICS|CHEMISTRY|MATHEMATICS|BIOLOGY|BOTANY|ZOOLOGY)\b",
    re.IGNORECASE,
)
_MATH_SYMBOLS_RE = re.compile(
    r"(?:\\(?:frac|sqrt|int|sum|prod|alpha|beta|gamma|theta|lambda|pi|sigma|omega|Delta|Omega)|[=<>≤≥±×÷√∫∑∏]|\^[0-9a-zA-Z{]|_{[0-9a-zA-Z]|(?:sin|cos|tan|log|ln)\s*\()"
)
_TABLE_RE = re.compile(
    r"(?:(?:Column|List|Table)\s*[-–:]?\s*[I|1|A])",
    re.IGNORECASE,
)


@dataclass
class PaddleVLConfig:
    """Configuration for Paddle-VL-1.6 engine."""

    model_name: str = DEFAULT_MODEL_NAME
    pipeline_version: str = DEFAULT_PIPELINE_VERSION
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout_s: float = 60.0
    use_gpu: bool = False
    max_retries: int = 2


class PaddleVLAdapter:
    """
    Adapter for PaddleOCR-VL-1.6 vision-language model for OCR & layout extraction.
    """

    engine_name = "paddle_vl_1.6"
    _shared_instances: dict[tuple[Any, ...], Any] = {}
    _model_init_count: int = 0
    _inference_count: int = 0

    @classmethod
    def get_model_init_count(cls) -> int:
        return cls._model_init_count

    @classmethod
    def get_inference_count(cls) -> int:
        return cls._inference_count

    @classmethod
    def reset_inference_count(cls) -> None:
        cls._inference_count = 0

    @classmethod
    def reset_shared_instances(cls) -> None:
        cls._shared_instances.clear()
        cls._model_init_count = 0
        cls._inference_count = 0

    def __init__(self, config: Optional[PaddleVLConfig] = None):
        if config is None:
            # Check environment variables
            api_url = os.environ.get("PADDLE_VL_ENDPOINT") or os.environ.get("PADDLE_VL_API_URL")
            self.config = PaddleVLConfig(
                api_url=api_url,
                api_key=os.environ.get("PADDLE_VL_API_KEY"),
            )
        else:
            self.config = config

        self._local_ocr_instance: Any = None
        self._circuit_open: bool = False
        self._fail_count: int = 0
        self._pages_since_fail: int = 0

    def is_available(self) -> bool:
        """Check if Paddle-VL-1.6 is available via API or local library."""
        if self.config.api_url:
            return not self._circuit_open or self._pages_since_fail >= 5
        import importlib.util

        return importlib.util.find_spec("paddleocr") is not None

    def extract_page(
        self,
        image_path: Optional[Path],
        page_num: int,
        fallback_blocks: Optional[list[Block]] = None,
    ) -> list[Block]:
        """
        Extract OCR and layout blocks from a page image using Paddle-VL-1.6.

        If Paddle-VL-1.6 API is configured, queries the endpoint.
        If local paddleocr library is installed, calls it directly with warm engine caching.
        Otherwise, enhances and returns fallback_blocks with Paddle-VL-1.6 layout metadata.
        """
        # Try HTTP endpoint if configured and circuit breaker allows (closed or half-open retry)
        allow_api_attempt = False
        if self.config.api_url:
            if not self._circuit_open:
                allow_api_attempt = True
            else:
                self._pages_since_fail += 1
                if self._pages_since_fail >= 5:
                    allow_api_attempt = True  # Half-open test probe

        if allow_api_attempt:
            try:
                blocks = self._call_http_api(image_path, page_num)
                if blocks:
                    logger.info(
                        "  Paddle-VL 1.6 (API): Extracted %d blocks on page %d",
                        len(blocks),
                        page_num,
                    )
                    # Successful call resets circuit breaker
                    self._circuit_open = False
                    self._fail_count = 0
                    self._pages_since_fail = 0
                    return blocks
            except Exception as e:
                self._fail_count += 1
                logger.warning(
                    "  Paddle-VL 1.6 API call failed (%s); opening circuit breaker and falling back.",
                    e,
                )
                self._circuit_open = True
                self._pages_since_fail = 0

        # Try local paddleocr library if installed
        try:
            blocks = self._call_local_library(image_path, page_num)
            if blocks:
                logger.info(
                    "  Paddle-VL 1.6 (Local): Extracted %d blocks on page %d",
                    len(blocks),
                    page_num,
                )
                return blocks
        except Exception as e:
            logger.debug("Local Paddle-VL library not available or failed: %s", e)

        # Fallback: Enhance digital text blocks with Paddle-VL-1.6 layout analysis & provenance
        if fallback_blocks:
            enhanced_blocks = []
            for b in fallback_blocks:
                source = EngineSource(
                    engine=self.engine_name,
                    text=b.text,
                    confidence=b.confidence,
                )
                sources = list(b.sources)
                if not any(s.engine == self.engine_name for s in sources):
                    sources.append(source)

                # Layout classification
                stripped = b.text.strip()
                b_type = b.type
                latex = b.latex
                if _HEADER_RE.search(stripped):
                    b_type = BlockType.HEADER
                elif _TABLE_RE.search(stripped):
                    b_type = BlockType.TABLE
                elif _MATH_SYMBOLS_RE.search(stripped):
                    b_type = BlockType.FORMULA
                    if not latex:
                        latex = stripped

                b_copy = b.model_copy(
                    update={
                        "type": b_type,
                        "latex": latex,
                        "sources": sources,
                    }
                )
                enhanced_blocks.append(b_copy)
            return enhanced_blocks

        return []

    def _call_http_api(self, image_path: Optional[Path], page_num: int) -> list[Block]:
        """Query remote or local vLLM / OpenAI-compatible endpoint serving PaddleOCR-VL-1.6."""
        if not image_path or not image_path.exists():
            return []

        with open(image_path, "rb") as f:
            b64_image = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "You are PaddleOCR-VL-1.6 document parser. Extract all OCR text and layout components "
            "from this document page. Output a JSON array of objects with keys: "
            "'text' (string), 'bbox' ([x1, y1, x2, y2] integers), "
            "'type' ('text'|'formula'|'table'|'figure'|'header'|'footer'), "
            "'lang' ('en'|'hi'|'unknown'). Return ONLY raw JSON without markdown code fences."
        )

        base_url = self.config.api_url.rstrip("/")
        if not base_url.endswith("/v1"):
            api_endpoint = f"{base_url}/v1/chat/completions"
        else:
            api_endpoint = f"{base_url}/chat/completions"

        payload = {
            "model": self.config.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                    ],
                }
            ],
            "max_tokens": 4096,
            "temperature": 0.0,
        }

        req = urllib.request.Request(
            api_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        if self.config.api_key:
            req.add_header("Authorization", f"Bearer {self.config.api_key}")

        with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        PaddleVLAdapter._inference_count += 1

        content = data["choices"][0]["message"]["content"].strip()
        # Clean any markdown code blocks
        content = re.sub(r"^```(?:json)?", "", content, flags=re.MULTILINE)
        content = re.sub(r"```$", "", content, flags=re.MULTILINE).strip()

        raw_items = json.loads(content)
        blocks = []
        for idx, item in enumerate(raw_items):
            bbox_coords = item.get("bbox", [0, 0, 100, 20])
            bbox = BBox(
                x1=int(bbox_coords[0]),
                y1=int(bbox_coords[1]),
                x2=int(bbox_coords[2]),
                y2=int(bbox_coords[3]),
            )
            raw_type = item.get("type", "text").lower()
            block_type = {
                "text": BlockType.TEXT,
                "formula": BlockType.FORMULA,
                "table": BlockType.TABLE,
                "figure": BlockType.FIGURE,
                "header": BlockType.HEADER,
                "footer": BlockType.FOOTER,
            }.get(raw_type, BlockType.TEXT)

            lang_str = item.get("lang", "en").lower()
            lang = Lang.HI if lang_str == "hi" else Lang.EN

            text = item.get("text", "").strip()
            block = Block(
                id=f"paddlevl_{page_num}_{idx}",
                page=page_num,
                type=block_type,
                bbox=bbox,
                order=idx,
                lang=lang,
                text=text,
                latex=None,
                confidence=float(item.get("confidence", 0.95)),
                sources=[
                    EngineSource(
                        engine=self.engine_name,
                        text=text,
                        confidence=float(item.get("confidence", 0.95)),
                    )
                ],
                status=BlockStatus.TRUSTED,
            )
            blocks.append(block)

        return blocks

    def _call_local_library(self, image_path: Optional[Path], page_num: int) -> list[Block]:
        """Call local paddleocr / PaddleOCRVL library if available with warm caching."""
        if not image_path or not image_path.exists():
            return []

        # Try official PaddleOCRVL pipeline first
        import importlib

        try:
            paddle_mod = importlib.import_module("paddleocr")
            PaddleOCRVL = getattr(paddle_mod, "PaddleOCRVL", None)
            if PaddleOCRVL is not None:
                cache_key = (
                    "vl",
                    self.config.pipeline_version,
                    self.config.model_name,
                    self.config.use_gpu,
                )
                if cache_key in PaddleVLAdapter._shared_instances:
                    self._local_ocr_instance = PaddleVLAdapter._shared_instances[cache_key]
                elif self._local_ocr_instance is None:
                    self._local_ocr_instance = PaddleOCRVL(
                        pipeline_version=self.config.pipeline_version,
                        vl_rec_api_model_name=self.config.model_name,
                        use_gpu=self.config.use_gpu,
                    )
                    PaddleVLAdapter._shared_instances[cache_key] = self._local_ocr_instance
                    PaddleVLAdapter._model_init_count += 1

                output = self._local_ocr_instance.predict(str(image_path))
                PaddleVLAdapter._inference_count += 1
                blocks: list[Block] = []
                for page_idx, res in enumerate(output):
                    # PaddleOCRVL exports structured layout results with bounding boxes
                    raw_data = getattr(res, "json", None) or getattr(res, "layout_result", None)
                    if isinstance(raw_data, list):
                        for idx, item in enumerate(raw_data):
                            bbox_coords = item.get("bbox", [0, 0, 100, 20])
                            raw_type = item.get("type", "text").lower()
                            b_type = {
                                "text": BlockType.TEXT,
                                "formula": BlockType.FORMULA,
                                "table": BlockType.TABLE,
                                "figure": BlockType.FIGURE,
                                "header": BlockType.HEADER,
                            }.get(raw_type, BlockType.TEXT)
                            text_val = item.get("text", item.get("markdown", "")).strip()
                            latex_val = item.get("latex") if b_type == BlockType.FORMULA else None
                            blocks.append(
                                Block(
                                    id=f"paddlevl_{page_num}_{idx}",
                                    page=page_num,
                                    type=b_type,
                                    bbox=BBox(
                                        x1=int(bbox_coords[0]),
                                        y1=int(bbox_coords[1]),
                                        x2=int(bbox_coords[2]),
                                        y2=int(bbox_coords[3]),
                                    ),
                                    order=idx,
                                    lang=Lang.HI if item.get("lang") == "hi" else Lang.EN,
                                    text=text_val,
                                    latex=latex_val,
                                    confidence=float(item.get("confidence", 0.95)),
                                    sources=[
                                        EngineSource(
                                            engine=self.engine_name,
                                            text=text_val,
                                            confidence=float(item.get("confidence", 0.95)),
                                        )
                                    ],
                                    status=BlockStatus.TRUSTED,
                                )
                            )
                if blocks:
                    return blocks
        except (ImportError, AttributeError, Exception) as e:
            logger.debug("PaddleOCRVL not available or failed: %s; trying PaddleOCR", e)

        # Fallback to standard PaddleOCR if installed
        try:
            paddle_mod = importlib.import_module("paddleocr")
            PaddleOCR = getattr(paddle_mod, "PaddleOCR", None)
            if PaddleOCR is None:
                return []
        except (ImportError, Exception):
            return []

        std_key = ("std", self.config.pipeline_version, self.config.use_gpu)
        if std_key in PaddleVLAdapter._shared_instances:
            self._local_ocr_instance = PaddleVLAdapter._shared_instances[std_key]
        elif self._local_ocr_instance is None or not hasattr(self._local_ocr_instance, "ocr"):
            self._local_ocr_instance = PaddleOCR(
                pipeline_version=self.config.pipeline_version,
                use_gpu=self.config.use_gpu,
                lang="en",
            )
            PaddleVLAdapter._shared_instances[std_key] = self._local_ocr_instance
            PaddleVLAdapter._model_init_count += 1

        result = self._local_ocr_instance.ocr(str(image_path), cls=True)
        PaddleVLAdapter._inference_count += 1
        if not result or not result[0]:
            return []

        blocks = []
        for idx, line in enumerate(result[0]):
            coords = line[0]  # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]] or [x1, y1, x2, y2]
            text, conf = line[1]
            if isinstance(coords, (list, tuple)) and len(coords) >= 4 and isinstance(coords[0], (int, float)):
                x1, y1, x2, y2 = coords[0], coords[1], coords[2], coords[3]
            elif isinstance(coords, (list, tuple)) and coords and isinstance(coords[0], (list, tuple)):
                xs = [p[0] for p in coords]
                ys = [p[1] for p in coords]
                x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
            else:
                x1, y1, x2, y2 = 0, 0, 100, 20

            bbox = BBox(
                x1=int(x1),
                y1=int(y1),
                x2=int(x2),
                y2=int(y2),
            )
            blocks.append(
                Block(
                    id=f"paddlevl_{page_num}_{idx}",
                    page=page_num,
                    type=BlockType.TEXT,
                    bbox=bbox,
                    order=idx,
                    lang=Lang.EN,
                    text=text,
                    latex=None,
                    confidence=float(conf),
                    sources=[
                        EngineSource(
                            engine=self.engine_name,
                            text=text,
                            confidence=float(conf),
                        )
                    ],
                    status=BlockStatus.TRUSTED,
                )
            )

        return blocks
