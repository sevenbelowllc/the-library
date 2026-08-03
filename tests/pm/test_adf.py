"""Tests for the shared ADF -> plain text helper."""
from __future__ import annotations

from library_server.pm.adf import adf_to_text


ADF_DOC = {
    "type": "doc", "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 1},
         "content": [{"type": "text", "text": "Title"}]},
        {"type": "paragraph",
         "content": [
             {"type": "text", "text": "Hello "},
             {"type": "text", "text": "world", "marks": [{"type": "strong"}]},
         ]},
    ],
}


def test_flattens_document():
    assert adf_to_text(ADF_DOC) == "Title\nHello world\n"


def test_passes_through_plain_string():
    assert adf_to_text("already text") == "already text"


def test_none_and_non_dict_return_empty():
    assert adf_to_text(None) == ""
    assert adf_to_text(42) == ""
