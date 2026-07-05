import pytest
from unittest.mock import patch
from junknuke.settings import parse_accounts

def test_single_account():
    with patch.dict("os.environ", {"MAIL_ACCOUNTS": "test@hotmail.com:microsoft"}):
        result = parse_accounts()
    assert result == {"test@hotmail.com": "microsoft"}

def test_multiple_accounts():
    with patch.dict("os.environ", {"MAIL_ACCOUNTS": "a@hotmail.com:microsoft,b@gmail.com:google"}):
        result = parse_accounts()
    assert result == {"a@hotmail.com": "microsoft", "b@gmail.com": "google"}

def test_empty_accounts():
    with patch.dict("os.environ", {"MAIL_ACCOUNTS": ""}):
        result = parse_accounts()
    assert result == {}

def test_strips_quotes():
    with patch.dict("os.environ", {"MAIL_ACCOUNTS": '"test@hotmail.com:microsoft"'}):
        result = parse_accounts()
    assert result == {"test@hotmail.com": "microsoft"}

def test_invalid_entry_skipped():
    with patch.dict("os.environ", {"MAIL_ACCOUNTS": "test@hotmail.com:microsoft,badeentry"}):
        result = parse_accounts()
    assert result == {"test@hotmail.com": "microsoft"}
