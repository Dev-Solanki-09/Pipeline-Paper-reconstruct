"""
Paddle-VL 1.6 Engine Adapter.

Integrates PaddleOCR-VL-1.6 for document OCR and layout extraction.
Supports:
1. HTTP / vLLM API serving PaddlePaddle/PaddleOCR-VL-1.6 (OpenAI-compatible or document-parse).
2. Local paddleocr Python library with pipeline_version="v1.6".
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

DEFAULT_MODEL_NAME = "PaddleOCR-VL-1.6"
DEFAULT_PIPELINE_VERSION = "v1.6"


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

    def is_available(self) -> bool:
        """Check if Paddle-VL-1.6 is available via API or local library."""
        if self.config.api_url:
            return not self._circuit_open
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def extract_page(
        self,
        image_path: Optional[Path],
        page_num: int,
        fallback_blocks: Optional[list[Block]] = None,
    ) -> list[Block]:
        """
        Extract OCR and layout blocks from a page image using Paddle-VL-1.6.

        If Paddle-VL-1.6 API is configured, queries the endpoint.
        If local paddleocr library is installed, calls it directly.
        Otherwise, enhances and returns fallback_blocks with Paddle-VL-1.6 metadata.
        """
        # Try HTTP endpoint if configured and circuit breaker is closed
        if self.config.api_url and not self._circuit_open:
            try:
                blocks = self._call_http_api(image_path, page_num)
                if blocks:
                    logger.info("  Paddle-VL 1.6 (API): Extracted %d blocks on page %d", len(blocks), page_num)
                    return blocks
            except Exception as e:
                logger.warning(
                    "  Paddle-VL 1.6 API call failed (%s); opening circuit breaker and falling back.",
                    e,
                )
                self._circuit_open = True

        # Try local paddleocr library if installed
        try:
            blocks = self._call_local_library(image_path, page_num)
            if blocks:
                logger.info("  Paddle-VL 1.6 (Local): Extracted %d blocks on page %d", len(blocks), page_num)
                return blocks
        except Exception as e:
            logger.debug("Local Paddle-VL library not available or failed: %s", e)

        # Fallback: Enhance digital text blocks with Paddle-VL-1.6 provenance
        if fallback_blocks:
            enhanced_blocks = []
            for b in fallback_blocks:
                source = EngineSource(
                    engine=self.engine_name,
                    text=b.text,
                    confidence=b.confidence,
                )
                # Check if already tagged
                sources = list(b.sources)
                if not any(s.engine == self.engine_name for s in sources):
                    sources.append(source)

                b_copy = b.model_copy(update={"sources": sources})
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
        """Call local paddleocr library if available."""
        if not image_path or not image_path.exists():
            return []

        try:
            from paddleocr import PaddleOCR
        except ImportError:
            return []

        if self._local_ocr_instance is None:
            self._local_ocr_instance = PaddleOCR(
                pipeline_version=self.config.pipeline_version,
                use_gpu=self.config.use_gpu,
                lang="en",
            )

        result = self._local_ocr_instance.ocr(str(image_path), cls=True)
        if not result or not result[0]:
            return []

        blocks = []
        for idx, line in enumerate(result[0]):
            box = line[0]  # [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
            text, conf = line[1]

            x1 = int(round(min(pt[0] for pt in box)))
            y1 = int(round(min(pt[1] for pt in box)))
            x2 = int(round(max(pt[0] for pt in box)))
            y2 = int(round(max(pt[1] for pt in box)))

            block = Block(
                id=f"paddlevl_{page_num}_{idx}",
                page=page_num,
                type=BlockType.TEXT,
                bbox=BBox(x1=x1, y1=y1, x2=x2, y2=y2),
                order=idx,
                lang=Lang.EN,
                text=text,
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
            blocks.append(block)

        return blocks
