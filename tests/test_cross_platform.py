"""
Tests for cross-platform path handling in ImmichClient
"""
import pytest
import os
from unittest.mock import patch, Mock
from src.immich_client import ImmichClient


class TestCrossPlatformPaths:
    """Test cross-platform path handling"""

    def test_init_normalizes_local_paths(self):
        """Test that local paths in mappings are normalized on init"""
        # Create a mapping with mixed slashes
        # We simulate a user providing a path with mixed separators
        # On Windows, this might look like "E:/library\admin"
        # On Linux, it's just a string, but we want to ensure it's normalized to os.sep

        mixed_path = f"data/library{os.sep}admin"
        if os.name == 'nt':
            # Force some mix if on Windows
            mixed_path = r"E:/library\admin"

        mappings = {mixed_path: "/remote/path"}
        client = ImmichClient("http://test", "key", mappings)

        # The key in path_mappings should be normalized
        expected_key = os.path.normpath(mixed_path)
        assert expected_key in client.path_mappings
        assert client.path_mappings[expected_key] == "/remote/path"

    @patch('src.immich_client.requests.post')
    def test_get_asset_id_normalizes_input(self, mock_post):
        """Test that get_asset_id_from_path normalizes input path"""
        # Setup client with a standard normalized path
        # Use a path that definitely exists on the current OS for normalization to make sense
        if os.name == 'nt':
            local_prefix = r"C:\data\library"
        else:
            local_prefix = "/data/library"

        mappings = {local_prefix: "/library"}
        client = ImmichClient("http://test", "key", mappings)

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'assets': {'items': []}}
        mock_post.return_value = mock_response

        # Input path with mixed/wrong separators for the current OS
        # We construct a path that should match local_prefix after normalization
        # e.g. /data/library/file.jpg
        input_path = os.path.join(local_prefix, "file.jpg")

        # Call the method
        client.get_asset_id_from_path(input_path)

        # Verify the call to requests.post used the correct translated path
        # It should be "/library/file.jpg"
        expected_translated_path = "/library/file.jpg"

        args, kwargs = mock_post.call_args
        assert kwargs['json']['originalPath'] == expected_translated_path

    def test_reverse_mapping_handles_mixed_input(self):
        """Test reverse mapping handles Immich paths correctly"""
        # Immich paths are always forward slashes
        if os.name == 'nt':
            local_prefix = r"C:\data\library"
        else:
            local_prefix = "/data/library"

        mappings = {local_prefix: "/library"}
        client = ImmichClient("http://test", "key", mappings)

        immich_path = "/library/folder/photo.jpg"
        result = client.reverse_path_mapping(immich_path)

        expected = os.path.join(local_prefix, "folder", "photo.jpg")
        assert result == expected
