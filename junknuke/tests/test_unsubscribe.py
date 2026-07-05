from junknuke.providers.microsoft.unsubscribe import extract_list_unsubscribe

def test_http_unsubscribe():
    msg = {
        "internetMessageHeaders": [
            {"name": "List-Unsubscribe", "value": "<https://example.com/unsub>"}
        ]
    }
    result = extract_list_unsubscribe(msg)
    assert result["http"] == "https://example.com/unsub"
    assert result["mailto"] is None

def test_mailto_unsubscribe():
    msg = {
        "internetMessageHeaders": [
            {"name": "List-Unsubscribe", "value": "<mailto:unsub@example.com>"}
        ]
    }
    result = extract_list_unsubscribe(msg)
    assert result["mailto"] == "unsub@example.com"
    assert result["http"] is None

def test_no_unsubscribe_header():
    msg = {"internetMessageHeaders": []}
    result = extract_list_unsubscribe(msg)
    assert result["http"] is None
    assert result["mailto"] is None
