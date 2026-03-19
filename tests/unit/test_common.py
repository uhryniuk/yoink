"""Unit tests for common.py."""

import json

import pytest

from yoink.common import clean_html, is_valid_html, is_valid_url, load_urls_from_json, load_urls_from_txt


class TestIsValidUrl:
    def test_https(self):
        assert is_valid_url("https://example.com")

    def test_http(self):
        assert is_valid_url("http://example.com/path?q=1#frag")

    def test_ftp(self):
        assert is_valid_url("ftp://files.example.com")

    def test_localhost_with_port(self):
        assert is_valid_url("http://localhost:8080")

    def test_ipv4(self):
        assert is_valid_url("http://192.168.1.1/path")

    def test_empty_fails(self):
        assert not is_valid_url("")

    def test_no_scheme_fails(self):
        assert not is_valid_url("example.com")

    def test_bare_word_fails(self):
        assert not is_valid_url("notaurl")

    def test_missing_host_fails(self):
        assert not is_valid_url("https://")


class TestIsValidHtml:
    def test_full_document(self):
        assert is_valid_html("<html><body><p>Hello</p></body></html>")

    def test_fragment(self):
        assert is_valid_html("<div>hi</div>")

    def test_empty_string(self):
        assert is_valid_html("")  # parseable, just empty


class TestCleanHtml:
    def test_removes_script(self):
        html = "<div>hi<script>alert(1)</script></div>"
        assert "<script>" not in clean_html(html)
        assert "hi" in clean_html(html)

    def test_removes_style(self):
        html = "<div><style>body{color:red}</style>text</div>"
        assert "<style>" not in clean_html(html)
        assert "text" in clean_html(html)

    def test_removes_svg(self):
        html = "<p>text</p><svg><path/></svg>"
        assert "<svg>" not in clean_html(html)

    def test_keeps_id_attribute(self):
        html = '<div id="main" class="foo">content</div>'
        result = clean_html(html)
        assert 'id="main"' in result

    def test_keeps_href_attribute(self):
        html = '<a href="https://x.com" class="link">click</a>'
        result = clean_html(html)
        assert 'href="https://x.com"' in result

    def test_custom_tags_to_remove(self):
        html = "<p>ok</p><nav>menu</nav>"
        result = clean_html(html, tags_to_remove=["nav"])
        assert "<nav>" not in result
        assert "ok" in result

    def test_custom_attributes_to_keep(self):
        html = '<input type="text" id="foo" name="bar">'
        result = clean_html(html, attributes_to_keep=["type"])
        assert 'type="text"' in result


class TestLoadUrlsFromTxt:
    def test_basic(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("https://a.com\nhttps://b.com\n")
        assert load_urls_from_txt(f) == ["https://a.com", "https://b.com"]

    def test_skips_blank_lines(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("https://a.com\n\n\nhttps://b.com\n")
        assert load_urls_from_txt(f) == ["https://a.com", "https://b.com"]

    def test_empty_file(self, tmp_path):
        f = tmp_path / "urls.txt"
        f.write_text("")
        assert load_urls_from_txt(f) == []


class TestLoadUrlsFromJson:
    def test_list_format(self, tmp_path):
        f = tmp_path / "urls.json"
        f.write_text(json.dumps(["https://a.com", "https://b.com"]))
        assert load_urls_from_json(f) == ["https://a.com", "https://b.com"]

    def test_object_format(self, tmp_path):
        f = tmp_path / "urls.json"
        f.write_text(json.dumps({"urls": ["https://a.com"]}))
        assert load_urls_from_json(f) == ["https://a.com"]

    def test_unsupported_format_raises(self, tmp_path):
        f = tmp_path / "urls.json"
        f.write_text(json.dumps({"other_key": ["https://a.com"]}))
        with pytest.raises(ValueError, match="Unsupported"):
            load_urls_from_json(f)

    def test_casts_non_strings(self, tmp_path):
        f = tmp_path / "urls.json"
        f.write_text(json.dumps([1, 2]))
        result = load_urls_from_json(f)
        assert result == ["1", "2"]
