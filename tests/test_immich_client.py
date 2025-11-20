import unittest
from unittest.mock import MagicMock, patch
from src.immich_client import ImmichClient

class TestImmichClient(unittest.TestCase):
    def setUp(self):
        self.client = ImmichClient("http://localhost:2283", "test-key")

    @patch('requests.get')
    def test_get_asset_id_from_path_success(self, mock_get):
        # Mock search response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assets": {
                "items": [
                    {
                        "id": "asset-123",
                        "originalPath": "/path/to/image.jpg",
                        "originalFileName": "image.jpg"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        asset_id = self.client.get_asset_id_from_path("/path/to/image.jpg")
        self.assertEqual(asset_id, "asset-123")

    @patch('requests.get')
    def test_get_asset_id_from_path_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"assets": {"items": []}}
        mock_get.return_value = mock_response

        asset_id = self.client.get_asset_id_from_path("/path/to/image.jpg")
        self.assertIsNone(asset_id)

    @patch('requests.get')
    @patch('requests.post')
    def test_create_tag_if_not_exists_creates_new(self, mock_post, mock_get):
        # Mock list tags (empty)
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []

        # Mock create tag
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"id": "tag-123", "name": "Watercolor"}

        tag_id = self.client.create_tag_if_not_exists("Watercolor")
        self.assertEqual(tag_id, "tag-123")

    @patch('requests.put')
    def test_add_tag_to_asset(self, mock_put):
        mock_put.return_value.status_code = 200
        success = self.client.add_tag_to_asset("asset-123", "tag-123")
        self.assertTrue(success)

if __name__ == '__main__':
    unittest.main()
