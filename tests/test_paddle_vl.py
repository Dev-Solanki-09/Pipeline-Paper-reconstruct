"""Tests for Paddle-VL 1.6 OCR and layout engine adapter."""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from examforge.engines.paddle_vl import (
    DEFAULT_MODEL_NAME,
    DEFAULT_PIPELINE_VERSION,
    PaddleVLAdapter,
    PaddleVLConfig,
)
from examforge.ir.schema import (
    BBox,
    Block,
    BlockStatus,
    BlockType,
    EngineSource,
    ExamDocument,
    ExamMetadata,
    Lang,
    PageClassification,
    PageInfo,
    PageProcessingPath,
)
from examforge.stages.base import StageContext
from examforge.stages.s3_parse import S3Parse


class TestPaddleVLConfig:
    def test_default_config(self):
        cfg = PaddleVLConfig()
        assert cfg.model_name == DEFAULT_MODEL_NAME
        assert cfg.pipeline_version == DEFAULT_PIPELINE_VERSION
        assert cfg.api_url is None
        assert cfg.use_gpu is False

    def test_env_var_initialization(self, monkeypatch):
        monkeypatch.setenv("PADDLE_VL_ENDPOINT", "http://localhost:8000/v1")
        monkeypatch.setenv("PADDLE_VL_API_KEY", "test-token")
        adapter = PaddleVLAdapter()
        assert adapter.config.api_url == "http://localhost:8000/v1"
        assert adapter.config.api_key == "test-token"


class TestPaddleVLLayoutExtraction:
    def test_fallback_layout_analysis_headers(self):
        adapter = PaddleVLAdapter()
        raw_block = Block(
            id="b1",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=50, x2=400, y2=80),
            text="PART-1 : PHYSICS",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )
        res = adapter.extract_page(image_path=None, page_num=1, fallback_blocks=[raw_block])
        assert len(res) == 1
        assert res[0].type == BlockType.HEADER
        assert any(s.engine == "paddle_vl_1.6" for s in res[0].sources)

    def test_fallback_layout_analysis_formulas(self):
        adapter = PaddleVLAdapter()
        raw_block = Block(
            id="b2",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=100, x2=300, y2=150),
            text=r"E = \frac{1}{2} m v^2",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )
        res = adapter.extract_page(image_path=None, page_num=1, fallback_blocks=[raw_block])
        assert len(res) == 1
        assert res[0].type == BlockType.FORMULA
        assert res[0].latex == r"E = \frac{1}{2} m v^2"

    def test_fallback_layout_analysis_tables(self):
        adapter = PaddleVLAdapter()
        raw_block = Block(
            id="b3",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=200, x2=500, y2=250),
            text="Column-I                Column-II",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )
        res = adapter.extract_page(image_path=None, page_num=1, fallback_blocks=[raw_block])
        assert len(res) == 1
        assert res[0].type == BlockType.TABLE

    def test_fallback_plain_text_retains_text_type(self):
        adapter = PaddleVLAdapter()
        raw_block = Block(
            id="b4",
            page=1,
            type=BlockType.TEXT,
            bbox=BBox(x1=50, y1=300, x2=400, y2=350),
            text="A body moves in a straight line with uniform acceleration.",
            confidence=1.0,
            status=BlockStatus.TRUSTED,
        )
        res = adapter.extract_page(image_path=None, page_num=1, fallback_blocks=[raw_block])
        assert len(res) == 1
        assert res[0].type == BlockType.TEXT


class TestPaddleVLHttpAPI:
    def test_http_api_parses_elements(self, tmp_path):
        dummy_img = tmp_path / "page_1.png"
        dummy_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        api_response = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps([
                            {
                                "bbox": [50, 40, 300, 70],
                                "type": "header",
                                "text": "SECTION 1 : PHYSICS",
                                "lang": "en",
                                "confidence": 0.99,
                            },
                            {
                                "bbox": [50, 80, 500, 150],
                                "type": "text",
                                "text": "1. What is the value of gravitational potential at infinity?",
                                "lang": "en",
                                "confidence": 0.98,
                            },
                            {
                                "bbox": [60, 160, 200, 190],
                                "type": "formula",
                                "text": r"V(r) = -\frac{G M}{r}",
                                "lang": "en",
                                "confidence": 0.97,
                            },
                        ])
                    }
                }
            ]
        }

        cfg = PaddleVLConfig(api_url="http://mock-paddlevl:8000/v1")
        adapter = PaddleVLAdapter(config=cfg)

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(api_response).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp

        with patch("urllib.request.urlopen", return_value=mock_resp):
            blocks = adapter.extract_page(image_path=dummy_img, page_num=1)

        assert len(blocks) == 3
        assert blocks[0].type == BlockType.HEADER
        assert blocks[0].text == "SECTION 1 : PHYSICS"
        assert blocks[1].type == BlockType.TEXT
        assert blocks[2].type == BlockType.FORMULA
        assert blocks[2].sources[0].engine == "paddle_vl_1.6"

    def test_http_circuit_breaker_on_error(self, tmp_path):
        dummy_img = tmp_path / "page_1.png"
        dummy_img.write_bytes(b"test")

        cfg = PaddleVLConfig(api_url="http://failing-endpoint:8000/v1")
        adapter = PaddleVLAdapter(config=cfg)

        fallback = [
            Block(
                id="fb1",
                page=1,
                type=BlockType.TEXT,
                bbox=BBox(x1=10, y1=10, x2=100, y2=50),
                text="Fallback text",
                confidence=1.0,
            )
        ]

        with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
            blocks = adapter.extract_page(image_path=dummy_img, page_num=1, fallback_blocks=fallback)

        assert adapter._circuit_open is True
        assert len(blocks) == 1
        assert blocks[0].text == "Fallback text"
        assert any(s.engine == "paddle_vl_1.6" for s in blocks[0].sources)


class TestS3IntegrationWithPaddleVL:
    def test_s3_parse_attaches_paddlevl_provenance(self, sample_pdf_path, tmp_path):
        if sample_pdf_path is None:
            pytest.skip("Sample PDF not available")

        exam_doc = ExamDocument(
            source_path=str(sample_pdf_path),
            source_hash="test_hash",
            metadata=ExamMetadata(exam_name="Sample"),
            pages=[
                PageInfo(
                    page_number=2,
                    has_text_layer=True,
                    text_layer_valid=True,
                    classification=PageClassification.QUESTIONS,
                    processing_path=PageProcessingPath.PATH_B,
                    width_px=612,
                    height_px=792,
                )
            ],
        )

        ctx = StageContext(
            document=exam_doc,
            config=None,
            spec=None,
            stage_dir=tmp_path / "s3",
            run_dir=tmp_path,
        )

        stage = S3Parse()
        result = stage.run(ctx)

        assert len(result.document.blocks) > 0
        first_block = result.document.blocks[0]
        # Should have both pymupdf and paddle_vl_1.6 in sources
        engine_names = [s.engine for s in first_block.sources]
        assert "paddle_vl_1.6" in engine_names
