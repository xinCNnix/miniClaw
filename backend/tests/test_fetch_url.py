"""
Unit tests for fetch_url tool
"""

import pytest
from unittest.mock import Mock, patch
from app.tools.fetch_url import fetch_url_tool


class TestFetchURLTool:
    """Test cases for FetchURLTool"""

    def test_validate_url_valid_http(self):
        """Test validation of valid HTTP URL"""
        # Should not raise exception
        fetch_url_tool._validate_url("http://example.com")

    def test_validate_url_valid_https(self):
        """Test validation of valid HTTPS URL"""
        # Should not raise exception
        fetch_url_tool._validate_url("https://example.com")

    def test_validate_url_invalid_scheme(self):
        """Test validation of URL with invalid scheme"""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            fetch_url_tool._validate_url("ftp://example.com")

    def test_validate_url_localhost_blocked(self):
        """Test that localhost is blocked"""
        with pytest.raises(ValueError, match="localhost.*not allowed"):
            fetch_url_tool._validate_url("http://localhost:8000")

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_fetch_json_response(self, mock_head, mock_get):
        """Test fetching JSON response"""
        # Setup mock
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '{"temp": "20", "city": "Beijing"}'
        mock_response.status_code = 200

        mock_get.return_value = mock_response
        mock_head.return_value = mock_response

        # Test
        result = fetch_url_tool.run("https://api.example.com/weather")

        # Assertions
        assert "# JSON Response" in result
        assert '{"temp": "20", "city": "Beijing"}' in result
        mock_get.assert_called_once()

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_fetch_html_response(self, mock_head, mock_get):
        """Test fetching HTML response"""
        # Setup mock
        mock_head_response = Mock()
        mock_head_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_html_response = Mock()
        mock_html_response.headers = {"content-type": "text/html; charset=utf-8"}
        mock_html_response.text = "<html><body><h1>Hello World</h1></body></html>"
        mock_html_response.status_code = 200

        mock_head.return_value = mock_head_response
        mock_get.return_value = mock_html_response

        # Test
        result = fetch_url_tool.run("https://example.com")

        # Assertions
        assert "# Content from" in result
        assert "Hello World" in result
        mock_get.assert_called_once()

    @patch('app.tools.fetch_url.requests.get')
    def test_fetch_timeout(self, mock_get):
        """Test handling of timeout"""
        from requests import Timeout

        mock_get.side_effect = Timeout("Connection timed out")

        # Test
        result = fetch_url_tool.run("https://example.com", timeout=5)

        # Assertions
        assert "timed out" in result.lower()

    @patch('app.tools.fetch_url.requests.get')
    def test_fetch_http_error(self, mock_get):
        """Test handling of HTTP errors"""
        from requests import HTTPError

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.reason = "Not Found"

        error = HTTPError()
        error.response = mock_response

        mock_get.side_effect = error

        # Test
        result = fetch_url_tool.run("https://example.com/notfound")

        # Assertions
        assert "404" in result or "http error" in result.lower()

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_unsupported_content_type(self, mock_head, mock_get):
        """Test handling of unsupported content type"""
        # Setup mock for HEAD request
        mock_head_response = Mock()
        mock_head_response.headers = {"content-type": "application/pdf"}
        mock_head.return_value = mock_head_response

        # Test
        result = fetch_url_tool.run("https://example.com/file.pdf")

        # Assertions
        assert "Unsupported content type" in result or "application/pdf" in result

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_truncates_long_content(self, mock_head, mock_get):
        """Test that long content is truncated"""
        # Setup mock
        mock_response = Mock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.text = "<html><body>" + "A" * 15000 + "</body></html>"
        mock_response.status_code = 200

        mock_head.return_value = mock_response
        mock_get.return_value = mock_response

        # Test
        result = fetch_url_tool.run("https://example.com")

        # Assertions
        assert len(result) < 11000  # Should be truncated
        assert "truncated" in result.lower()

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_weather_api_json_format(self, mock_head, mock_get):
        """Test wttr.in JSON format (specific use case for weather skill)"""
        # Setup mock - wttr.in returns JSON
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.text = '''{
            "current_condition": [
                {
                    "temp_C": "15",
                    "weatherDesc": [{"value": "Sunny"}],
                    "humidity": "65"
                }
            ]
        }'''
        mock_response.status_code = 200

        mock_head.return_value = mock_response
        mock_get.return_value = mock_response

        # Test
        result = fetch_url_tool.run("https://wttr.in/Beijing?format=j1")

        # Assertions
        assert "# JSON Response" in result
        assert '"temp_C": "15"' in result
        assert '"weatherDesc"' in result

    @patch('app.tools.fetch_url.requests.get')
    @patch('app.tools.fetch_url.requests.head')
    def test_plain_text_response(self, mock_head, mock_get):
        """Test fetching plain text response"""
        # Setup mock
        mock_response = Mock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "This is plain text content."
        mock_response.status_code = 200

        mock_head.return_value = mock_response
        mock_get.return_value = mock_response

        # Test
        result = fetch_url_tool.run("https://example.com/data.txt")

        # Assertions
        assert "# Content from" in result
        assert "This is plain text content." in result
