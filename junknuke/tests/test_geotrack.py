from unittest.mock import patch
from junknuke.utils.geotrack import track_email

SAMPLE_MSG = {
    "subject": "Test spam",
    "from": {"emailAddress": {"address": "spammer@example.com"}},
    "internetMessageHeaders": [
        {"name": "Received", "value": "from mail.example.com (1.2.3.4) by server"}
    ]
}

def test_track_email_with_geo(mocker):
    mocker.patch(
        "junknuke.utils.geotrack.lookup_geo",
        return_value={"country": "United States", "city": "New York", "countryCode": "US"}
    )
    result = track_email(SAMPLE_MSG)
    assert result["country"] == "United States"
    assert result["ip"] is not None

def test_track_email_no_ip():
    msg = {**SAMPLE_MSG, "internetMessageHeaders": []}
    result = track_email(msg)
    assert result["country"] == "Unknown"
    assert result["ip"] is None
