"""Markdown → Atlassian Document Format (ADF) converter.

Jira Cloud REST v3 description + comment bodies require ADF JSON.
The prior implementation in jira_client._to_adf shipped raw markdown as a
single text node, causing every ticket to render as literal `#` / `**` / etc.

This module parses markdown via markdown-it-py and emits an ADF node tree.
Supported: headings (h1-h6), paragraphs, strong/em/inline-code marks, links,
bullet/ordered lists, code blocks (with language), blockquotes, horizontal
rule, tables.

ADF reference: https://developer.atlassian.com/cloud/jira/platform/apis/document/
"""

from __future__ import annotations

from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token


_ADF_DOC: dict[str, Any] = {"type": "doc", "version": 1}


def md_to_adf(text: str) -> dict[str, Any]:
    """Convert a markdown string into an ADF document node."""
    if not text:
        return {**_ADF_DOC, "content": [_empty_paragraph()]}

    md = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table").enable("strikethrough")
    tokens = md.parse(text)
    content = _render_block(iter(tokens))
    if not content:
        content = [_empty_paragraph()]
    return {**_ADF_DOC, "content": content}


def _empty_paragraph() -> dict[str, Any]:
    return {"type": "paragraph"}


def _render_block(tokens_iter) -> list[dict[str, Any]]:
    """Render a sequence of block-level tokens into ADF nodes."""
    out: list[dict[str, Any]] = []
    for tok in tokens_iter:
        node = _block_token(tok, tokens_iter)
        if node is not None:
            out.append(node)
    return out


def _block_token(tok: Token, it) -> dict[str, Any] | None:
    t = tok.type
    if t == "heading_open":
        level = int(tok.tag[1])
        inline = _consume_inline(it)
        _expect(it, "heading_close")
        return {"type": "heading", "attrs": {"level": level}, "content": _inline_nodes(inline)}
    if t == "paragraph_open":
        inline = _consume_inline(it)
        _expect(it, "paragraph_close")
        nodes = _inline_nodes(inline)
        return {"type": "paragraph", "content": nodes} if nodes else {"type": "paragraph"}
    if t == "bullet_list_open":
        items = _list_items(it, close="bullet_list_close")
        return {"type": "bulletList", "content": items}
    if t == "ordered_list_open":
        items = _list_items(it, close="ordered_list_close")
        node: dict[str, Any] = {"type": "orderedList", "content": items}
        start = tok.attrGet("start")
        if start and str(start).isdigit() and int(start) != 1:
            node["attrs"] = {"order": int(start)}
        return node
    if t == "fence" or t == "code_block":
        attrs: dict[str, Any] = {}
        if tok.info:
            lang = tok.info.strip().split()[0] if tok.info.strip() else ""
            if lang:
                attrs["language"] = lang
        node = {"type": "codeBlock", "content": [{"type": "text", "text": tok.content.rstrip("\n")}]}
        if attrs:
            node["attrs"] = attrs
        return node
    if t == "blockquote_open":
        inner = _render_until(it, "blockquote_close")
        return {"type": "blockquote", "content": inner or [_empty_paragraph()]}
    if t == "hr":
        return {"type": "rule"}
    if t == "table_open":
        return _render_table(it)
    # Unknown block — skip silently.
    return None


def _consume_inline(it) -> Token | None:
    for tok in it:
        if tok.type == "inline":
            return tok
        if tok.type.endswith("_close"):
            return None
    return None


def _expect(it, expected: str) -> None:
    for tok in it:
        if tok.type == expected:
            return


def _render_until(it, close_type: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tok in it:
        if tok.type == close_type:
            return out
        node = _block_token(tok, it)
        if node is not None:
            out.append(node)
    return out


def _list_items(it, close: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for tok in it:
        if tok.type == close:
            return items
        if tok.type == "list_item_open":
            children = _render_until(it, "list_item_close")
            children = _flatten_for_list_item(children)
            if not children:
                children = [_empty_paragraph()]
            items.append({"type": "listItem", "content": children})
    return items


def _flatten_for_list_item(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """ADF listItem cannot contain blockquote/heading/rule/table — flatten them.

    Allowed listItem children: paragraph, bulletList, orderedList, codeBlock.
    Anything else gets demoted to its paragraph contents.
    """
    allowed = {"paragraph", "bulletList", "orderedList", "codeBlock"}
    out: list[dict[str, Any]] = []
    for node in nodes:
        t = node.get("type")
        if t in allowed:
            out.append(node)
        elif t == "blockquote":
            # flatten blockquote children (which are paragraphs/lists)
            out.extend(_flatten_for_list_item(node.get("content", [])))
        elif t == "heading":
            # demote heading to paragraph with bold marks
            content = node.get("content", [])
            for child in content:
                if child.get("type") == "text":
                    marks = child.setdefault("marks", [])
                    if {"type": "strong"} not in marks:
                        marks.append({"type": "strong"})
            out.append({"type": "paragraph", "content": content})
        elif t == "rule" or t == "table":
            # drop silently (no good in-list representation)
            continue
        else:
            out.append(node)
    return out


def _render_table(it) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    in_header = False
    current_row: list[dict[str, Any]] | None = None
    current_cell_inline: Token | None = None
    cell_type: str | None = None

    for tok in it:
        t = tok.type
        if t == "table_close":
            break
        if t == "thead_open":
            in_header = True
        elif t == "thead_close":
            in_header = False
        elif t == "tr_open":
            current_row = []
        elif t == "tr_close":
            if current_row is not None:
                rows.append({"type": "tableRow", "content": current_row})
            current_row = None
        elif t in ("th_open", "td_open"):
            cell_type = "tableHeader" if t == "th_open" else "tableCell"
            current_cell_inline = None
        elif t == "inline":
            current_cell_inline = tok
        elif t in ("th_close", "td_close"):
            if current_row is not None and cell_type is not None:
                content_nodes = _inline_nodes(current_cell_inline) if current_cell_inline else []
                paragraph = {"type": "paragraph", "content": content_nodes} if content_nodes else {"type": "paragraph"}
                current_row.append({"type": cell_type, "content": [paragraph]})
            cell_type = None
            current_cell_inline = None
    _ = in_header  # informational; ADF table doesn't need explicit thead flag
    return {"type": "table", "attrs": {"isNumberColumnEnabled": False, "layout": "default"}, "content": rows}


def _inline_nodes(inline_tok: Token | None) -> list[dict[str, Any]]:
    if inline_tok is None or not inline_tok.children:
        return []
    out: list[dict[str, Any]] = []
    marks: list[dict[str, Any]] = []
    for child in inline_tok.children:
        t = child.type
        if t == "text":
            if child.content:
                node = {"type": "text", "text": child.content}
                if marks:
                    node["marks"] = list(marks)
                out.append(node)
        elif t == "softbreak":
            # Treat soft line breaks as spaces; ADF paragraph reflows naturally.
            if out and out[-1].get("type") == "text" and not out[-1].get("marks"):
                out[-1]["text"] += " "
            else:
                out.append({"type": "text", "text": " "})
        elif t == "hardbreak":
            out.append({"type": "hardBreak"})
        elif t == "code_inline":
            # ADF: `code` is an exclusive mark — cannot combine with strong/em/link/strike.
            node = {"type": "text", "text": child.content, "marks": [{"type": "code"}]}
            out.append(node)
        elif t == "strong_open":
            marks.append({"type": "strong"})
        elif t == "strong_close":
            _pop_mark(marks, "strong")
        elif t == "em_open":
            marks.append({"type": "em"})
        elif t == "em_close":
            _pop_mark(marks, "em")
        elif t == "s_open":
            marks.append({"type": "strike"})
        elif t == "s_close":
            _pop_mark(marks, "strike")
        elif t == "link_open":
            href = child.attrGet("href") or ""
            marks.append({"type": "link", "attrs": {"href": href}})
        elif t == "link_close":
            _pop_mark(marks, "link")
        # Ignore image tokens for now; could be added later.
    return out


def _pop_mark(marks: list[dict[str, Any]], mark_type: str) -> None:
    for i in range(len(marks) - 1, -1, -1):
        if marks[i].get("type") == mark_type:
            marks.pop(i)
            return
