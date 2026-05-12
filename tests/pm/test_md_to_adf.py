"""Tests for markdown → ADF converter."""

from __future__ import annotations

from library_server.pm.md_to_adf import md_to_adf


def _doc(*content):
    return {"type": "doc", "version": 1, "content": list(content)}


def test_empty_string_returns_empty_paragraph():
    assert md_to_adf("") == _doc({"type": "paragraph"})


def test_plain_paragraph():
    result = md_to_adf("hello world")
    assert result == _doc({"type": "paragraph", "content": [{"type": "text", "text": "hello world"}]})


def test_heading_levels():
    result = md_to_adf("# H1\n\n## H2\n\n### H3")
    assert result["content"][0]["type"] == "heading"
    assert result["content"][0]["attrs"]["level"] == 1
    assert result["content"][1]["attrs"]["level"] == 2
    assert result["content"][2]["attrs"]["level"] == 3


def test_bold_and_italic_marks():
    result = md_to_adf("**bold** and *italic* and ***both***")
    para = result["content"][0]
    assert para["type"] == "paragraph"
    text_nodes = para["content"]
    bold = next(n for n in text_nodes if n["text"] == "bold")
    italic = next(n for n in text_nodes if n["text"] == "italic")
    assert {"type": "strong"} in bold["marks"]
    assert {"type": "em"} in italic["marks"]


def test_inline_code():
    result = md_to_adf("use `npm install` to setup")
    nodes = result["content"][0]["content"]
    code_node = next(n for n in nodes if n["text"] == "npm install")
    assert {"type": "code"} in code_node["marks"]


def test_fenced_code_block_with_language():
    md = "```python\ndef hi():\n    pass\n```"
    result = md_to_adf(md)
    block = result["content"][0]
    assert block["type"] == "codeBlock"
    assert block["attrs"] == {"language": "python"}
    assert block["content"][0]["text"] == "def hi():\n    pass"


def test_fenced_code_block_no_language():
    result = md_to_adf("```\nplain\n```")
    block = result["content"][0]
    assert block["type"] == "codeBlock"
    assert "attrs" not in block or "language" not in block.get("attrs", {})


def test_bullet_list():
    result = md_to_adf("- one\n- two\n- three")
    bl = result["content"][0]
    assert bl["type"] == "bulletList"
    assert len(bl["content"]) == 3
    assert bl["content"][0]["type"] == "listItem"
    inner = bl["content"][0]["content"][0]
    assert inner["type"] == "paragraph"
    assert inner["content"][0]["text"] == "one"


def test_ordered_list():
    result = md_to_adf("1. first\n2. second")
    ol = result["content"][0]
    assert ol["type"] == "orderedList"
    assert len(ol["content"]) == 2


def test_link():
    result = md_to_adf("see [docs](https://example.com)")
    nodes = result["content"][0]["content"]
    link_node = next(n for n in nodes if n["text"] == "docs")
    link_mark = next(m for m in link_node["marks"] if m["type"] == "link")
    assert link_mark["attrs"]["href"] == "https://example.com"


def test_blockquote():
    result = md_to_adf("> quoted text")
    bq = result["content"][0]
    assert bq["type"] == "blockquote"
    assert bq["content"][0]["type"] == "paragraph"


def test_horizontal_rule():
    result = md_to_adf("before\n\n---\n\nafter")
    types = [n["type"] for n in result["content"]]
    assert "rule" in types


def test_table_with_header():
    md = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    result = md_to_adf(md)
    table = result["content"][0]
    assert table["type"] == "table"
    assert table["attrs"]["isNumberColumnEnabled"] is False
    # 2 rows: header + body
    assert len(table["content"]) == 2
    header_row = table["content"][0]
    assert header_row["content"][0]["type"] == "tableHeader"
    body_row = table["content"][1]
    assert body_row["content"][0]["type"] == "tableCell"


def test_mixed_document():
    md = """# Title

Some **intro** paragraph with `code` and [link](https://x.io).

## Section

- bullet one
- bullet two

```sql
SELECT 1;
```

> note: be careful

| col | val |
|---|---|
| a | 1 |
"""
    result = md_to_adf(md)
    types = [n["type"] for n in result["content"]]
    assert types == ["heading", "paragraph", "heading", "bulletList", "codeBlock", "blockquote", "table"]


def test_strikethrough():
    result = md_to_adf("~~gone~~ remains")
    nodes = result["content"][0]["content"]
    strike = next(n for n in nodes if n["text"] == "gone")
    assert {"type": "strike"} in strike["marks"]


def test_softbreak_becomes_space():
    result = md_to_adf("line one\nline two")
    nodes = result["content"][0]["content"]
    # Soft break is folded into adjacent text as a space.
    joined = "".join(n["text"] for n in nodes if n["type"] == "text")
    assert "line one" in joined and "line two" in joined


def test_blockquote_inside_list_item_flattened():
    # ADF: listItem cannot contain blockquote. Flatten to inline paragraphs.
    md = '- outer line\n\n  > nested quote'
    result = md_to_adf(md)
    bl = result["content"][0]
    assert bl["type"] == "bulletList"
    item_children = bl["content"][0]["content"]
    types = [n["type"] for n in item_children]
    assert "blockquote" not in types
    assert all(t in {"paragraph", "bulletList", "orderedList", "codeBlock"} for t in types)


def test_code_mark_is_exclusive():
    # ADF: code mark cannot combine with strong/em/link/strike.
    # Markdown `**`code`**` should emit code-only mark, not [strong, code].
    result = md_to_adf("**bold `code` more**")
    nodes = result["content"][0]["content"]
    code_node = next(n for n in nodes if n["text"] == "code")
    assert code_node["marks"] == [{"type": "code"}], f"got {code_node['marks']}"


def test_idempotent_plain_text():
    plain = "no markdown here just words"
    result = md_to_adf(plain)
    assert result["content"][0]["content"][0]["text"] == plain
