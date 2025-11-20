import unittest
from unittest.mock import MagicMock, patch
from src.immich_client import ImmichClient

class TestImmichClientPathMapping(unittest.TestCase):
    def setUp(self):
        self.mappings = {
            "/mnt/photos": "/usr/src/app/photos",
            "/Volumes/External": "/library"
        }
        self.client = ImmichClient("http://localhost:2283", "test-key", self.mappings)

    @patch('requests.get')
    def test_get_asset_id_with_mapping(self, mock_get):
        # Mock search response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assets": {
                "items": [
                    {
                        "id": "asset-mapped",
                        "originalPath": "/usr/src/app/photos/vacation/img.jpg",
                        "originalFileName": "img.jpg"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        # Local path that should be mapped
        local_path = "/mnt/photos/vacation/img.jpg"

        asset_id = self.client.get_asset_id_from_path(local_path)
        self.assertEqual(asset_id, "asset-mapped")

    @patch('requests.get')
    def test_get_asset_id_without_mapping_match(self, mock_get):
        # Mock search response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assets": {
                "items": [
                    {
                        "id": "asset-direct",
                        "originalPath": "/other/path/img.jpg",
                        "originalFileName": "img.jpg"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        # Path that doesn't match any mapping prefix
        local_path = "/other/path/img.jpg"

        asset_id = self.client.get_asset_id_from_path(local_path)
        self.assertEqual(asset_id, "asset-direct")

    @patch('requests.get')
    def test_get_asset_id_mapping_mismatch(self, mock_get):
        # Mock search response where mapped path doesn't match originalPath
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assets": {
                "items": [
                    {
                        "id": "asset-wrong",
                        "originalPath": "/usr/src/app/photos/different/img.jpg",
                        "originalFileName": "img.jpg"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        local_path = "/mnt/photos/vacation/img.jpg"
        # Mapped: /usr/src/app/photos/vacation/img.jpg
        # Original: /usr/src/app/photos/different/img.jpg

        asset_id = self.client.get_asset_id_from_path(local_path)
        self.assertIsNone(asset_id)

if __name__ == '__main__':
    unittest.main()
