from __future__ import annotations

from examforge.ir.schema import (
    BlankNode,
    CodeNode,
    DocumentPart,
    ExamDocument,
    FigureNode,
    LanguageInfo,
    Marks,
    MatchColumnsNode,
    MathNode,
    Option,
    Provenance,
    Question,
    QuestionKind,
    RawCropNode,
    StatementsNode,
    TextNode,
    migrate_v1_to_v2,
)


def test_schema_version_defaults_to_v2():
    doc = ExamDocument(source_path="test.pdf")
    assert doc.schema_version == 2


def test_content_node_discriminated_union():
    # 1. TextNode
    t_node = TextNode(texts={"en": "Hello", "hi": "नमस्ते"})
    assert t_node.kind == "text"
    assert t_node.texts["en"] == "Hello"

    # 2. MathNode
    m_node = MathNode(notation="latex", code="E=mc^2", display=True)
    assert m_node.kind == "math"

    # 3. FigureNode
    f_node = FigureNode(figure_ref="fig_1")
    assert f_node.kind == "figure"

    # 4. StatementsNode
    s_node = StatementsNode(items=[{"label": "I", "text": "Statement 1"}])
    assert s_node.kind == "statements"

    # 5. MatchColumnsNode
    match_node = MatchColumnsNode(
        left=[{"id": "A", "text": "Item A"}],
        right=[{"id": "1", "text": "Item 1"}],
    )
    assert match_node.kind == "match_columns"

    # 6. CodeNode
    c_node = CodeNode(language="python", text="print('test')")
    assert c_node.kind == "code"

    # 7. BlankNode
    b_node = BlankNode(index=1)
    assert b_node.kind == "blank"

    # 8. RawCropNode
    r_node = RawCropNode(figure_ref="crop_1", reason="Unparsed diagram")
    assert r_node.kind == "raw_crop"


def test_question_v2_with_content_nodes_and_compat():
    q = Question(
        id="q1",
        number=1,
        kind=QuestionKind.SINGLE_CORRECT,
        stem=[
            TextNode(texts={"en": "Find the velocity:", "hi": "वेग ज्ञात कीजिए:"}),
            MathNode(code=r"v = u + at"),
        ],
        options=[
            Option(
                label="A",
                content=[TextNode(texts={"en": "10 m/s", "hi": "10 m/s"})],
            ),
            Option(
                label="B",
                content=[TextNode(texts={"en": "20 m/s", "hi": "20 m/s"})],
            ),
        ],
        marks=Marks(positive=4.0, negative=1.0),
        provenance=Provenance.EXTRACTED,
    )

    assert q.stem_text_en == "Find the velocity: v = u + at"
    assert q.stem_text_hi == "वेग ज्ञात कीजिए: v = u + at"
    assert q.options[0].text_str_en == "10 m/s"
    assert q.options[1].text_str_en == "20 m/s"


def test_migration_v1_to_v2_idempotence():
    v1_dict = {
        "source_path": "legacy.pdf",
        "source_hash": "abc",
        "questions": [
            {
                "id": "q1",
                "number": 1,
                "kind": "mcq1",
                "stem_text_en": "Legacy English stem",
                "stem_text_hi": "Legacy Hindi stem",
                "options": [
                    {
                        "label": "A",
                        "text_str_en": "Option A text",
                        "text_str_hi": "विकल्प A",
                    }
                ],
            }
        ],
    }

    doc_v2 = migrate_v1_to_v2(v1_dict)
    assert doc_v2.schema_version == 2
    assert len(doc_v2.questions) == 1
    q = doc_v2.questions[0]
    assert len(q.stem) > 0
    assert q.stem_text_en == "Legacy English stem"
    assert q.options[0].text_str_en == "Option A text"

    # Test idempotence: migrate(migrate(x)) == migrate(x)
    doc_v2_reloaded = migrate_v1_to_v2(doc_v2)
    assert doc_v2_reloaded.model_dump() == doc_v2.model_dump()


def test_document_parts_and_languages():
    doc = ExamDocument(
        source_path="paper.pdf",
        languages=[
            LanguageInfo(code="en", script="Latin", direction="ltr"),
            LanguageInfo(code="hi", script="Devanagari", direction="ltr"),
        ],
        parts=[
            DocumentPart(kind="instructions", pages=[1]),
            DocumentPart(kind="answer_key", pages=[10]),
        ],
    )
    assert len(doc.languages) == 2
    assert doc.parts[0].kind == "instructions"
    assert doc.parts[1].kind == "answer_key"


def test_schema_json_file_is_up_to_date():
    import json
    from pathlib import Path

    schema_file = Path(__file__).parent.parent / "schemas" / "examdocument.v2.json"
    assert schema_file.exists(), "schemas/examdocument.v2.json must exist."

    committed_schema = json.loads(schema_file.read_text(encoding="utf-8"))
    current_schema = ExamDocument.model_json_schema()
    assert committed_schema == current_schema, (
        "schemas/examdocument.v2.json is stale. Run 'examforge schema export' to update it."
    )

