"""
Tests for junknuke/utils/influxdb.py
Covers write_msgs_to_influxdb() and write_stats_to_influxdb().
InfluxDB client is mocked so no real DB connection is needed.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from junknuke.utils.influxdb import write_msgs_to_influxdb, write_stats_to_influxdb


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_GEO = {
    "country":     "United States",
    "countryCode": "US",
    "city":        "New York",
    "lat":         40.7128,
    "lon":         -74.0060,
    "isp":         "Some ISP",
    "org":         "Some Org",
    "as":          "AS12345",
    "ip":          "203.0.113.42",
    "sender":      "spammer@example.com",
    "sender_domain": "example.com",
    "subject":     "Buy now!",
    "timestamp":   1234567890.0,
}

SAMPLE_STATS = {
    "total":              10,
    "seen":               10,
    "already_processed":  2,
    "allowlisted":        1,
    "no_unsub_found":     5,
    "unsubscribed_ok":    1,
    "failed":             4,
}


def mock_influx_client():
    """Returns a mock InfluxDB client context manager."""
    mock_client = MagicMock()
    mock_write_api = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.write_api.return_value = mock_write_api
    return mock_client, mock_write_api


# ── write_msgs_to_influxdb ────────────────────────────────────────────────────

class TestWriteMsgsToInfluxdb:

    def test_writes_point_successfully(self):
        mock_client, mock_write_api = mock_influx_client()
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_msgs_to_influxdb(SAMPLE_GEO, email="test@hotmail.com", provider="microsoft")
        assert mock_write_api.write.called

    def test_skips_write_when_no_token(self):
        mock_client, mock_write_api = mock_influx_client()
        with patch("junknuke.utils.influxdb._get_influx_token", return_value=None), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_msgs_to_influxdb(SAMPLE_GEO, email="test@hotmail.com", provider="microsoft")
        assert not mock_write_api.write.called

    def test_handles_missing_fields_gracefully(self):
        mock_client, mock_write_api = mock_influx_client()
        sparse_data = {"ip": "1.2.3.4"}
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_msgs_to_influxdb(sparse_data, email="test@hotmail.com", provider="microsoft")
        assert mock_write_api.write.called

    def test_handles_write_exception(self):
        mock_client, mock_write_api = mock_influx_client()
        mock_write_api.write.side_effect = Exception("Connection refused")
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            # Should not raise — exception is caught and logged
            write_msgs_to_influxdb(SAMPLE_GEO, email="test@hotmail.com", provider="microsoft")


# ── write_stats_to_influxdb ───────────────────────────────────────────────────

class TestWriteStatsToInfluxdb:

    def test_writes_point_successfully(self):
        mock_client, mock_write_api = mock_influx_client()
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_stats_to_influxdb(SAMPLE_STATS, email="test@hotmail.com", provider="microsoft")
        assert mock_write_api.write.called

    def test_skips_write_when_no_token(self):
        mock_client, mock_write_api = mock_influx_client()
        with patch("junknuke.utils.influxdb._get_influx_token", return_value=None), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_stats_to_influxdb(SAMPLE_STATS, email="test@hotmail.com", provider="microsoft")
        assert not mock_write_api.write.called

    def test_handles_missing_stat_fields(self):
        mock_client, mock_write_api = mock_influx_client()
        sparse_stats = {"seen": 5}
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            write_stats_to_influxdb(sparse_stats, email="test@hotmail.com", provider="microsoft")
        assert mock_write_api.write.called

    def test_handles_write_exception(self):
        mock_client, mock_write_api = mock_influx_client()
        mock_write_api.write.side_effect = Exception("Timeout")
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
             patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client):
            # Should not raise
            write_stats_to_influxdb(SAMPLE_STATS, email="test@hotmail.com", provider="microsoft")

    def test_passes_string_data_raises(self, caplog):
        """Passing a string instead of dict should log an error, not raise."""
        import logging
        mock_client, mock_write_api = mock_influx_client()
        with patch("junknuke.utils.influxdb._get_influx_token", return_value="test-token"), \
            patch("junknuke.utils.influxdb.InfluxDBClient", return_value=mock_client), \
            caplog.at_level(logging.ERROR):
            write_stats_to_influxdb("stats", email="test@hotmail.com", provider="microsoft")
        assert "InfluxDB write failed" in caplog.text
