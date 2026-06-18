"""Test the WemPortal API."""
from unittest.mock import patch, MagicMock
import pytest
import requests

from custom_components.wemportal.wemportalapi import WemPortalApi
from custom_components.wemportal.exceptions import ForbiddenError


def test_api_login_success():
    """Test successful API login."""
    api = WemPortalApi("test", "test", "0000")
    
    with patch("custom_components.wemportal.wemportalapi.reqs.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"Status": 0, "Message": "OK"}
        mock_post.return_value = mock_response

        api.api_login()
        
        assert api.valid_login is True
        mock_post.assert_called_once()


def test_api_login_failure():
    """Test API login failure resulting in ForbiddenError."""
    api = WemPortalApi("test", "test", "0000")
    
    with patch("custom_components.wemportal.wemportalapi.reqs.Session.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"Status": 403, "Message": "Forbidden"}
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_response)
        mock_post.return_value = mock_response

        with pytest.raises(ForbiddenError):
            api.api_login()
            
        assert api.valid_login is False
