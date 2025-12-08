import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.batch_processor import BatchProcessor  # noqa: E402


class TestPaintingTag(unittest.TestCase):
    def setUp(self):
        self.classifier = MagicMock()
        self.video_processor = MagicMock()
        self.batch_processor = BatchProcessor(self.classifier, self.video_processor)
        self.immich_client = MagicMock()

    def test_tag_painting(self):
        # Setup mock result for a watercolor painting
        result_data = {
            'file_path': 'test.jpg',
            'confidence': 0.9,
            'top_label': 'a watercolor painting'
        }
        
        # Setup mock Immich client
        self.immich_client.create_tag_if_not_exists.return_value = 'tag_id_123'
        self.immich_client.get_asset_id_from_path.return_value = 'asset_id_456'
        self.immich_client.add_tag_to_asset.return_value = True

        # Call the method
        self.batch_processor._tag_asset_if_needed(self.immich_client, 'base_tag_id', 'test.jpg', result_data)

        # Verify "Painting" tag was created/retrieved
        self.immich_client.create_tag_if_not_exists.assert_any_call('Painting')
        
        # Verify asset was tagged with "Painting" tag
        # We expect add_tag_to_asset to be called for granular tag AND Painting tag
        # But since we mocked create_tag_if_not_exists to always return 'tag_id_123',
        # both calls will use 'tag_id_123'.
        # To be more precise, we can check call count or arguments.
        self.assertEqual(self.immich_client.add_tag_to_asset.call_count, 2)

    def test_tag_painting_oil(self):
        # Setup mock result for an oil painting
        result_data = {
            'file_path': 'test_oil.jpg',
            'confidence': 0.3, # Low confidence for watercolor, but high for oil (implied by top_label)
            'top_label': 'an oil painting'
        }
        
        self.immich_client.create_tag_if_not_exists.return_value = 'tag_id_painting'
        self.immich_client.get_asset_id_from_path.return_value = 'asset_id_789'
        self.immich_client.add_tag_to_asset.return_value = True

        self.batch_processor._tag_asset_if_needed(self.immich_client, 'base_tag_id', 'test_oil.jpg', result_data)

        self.immich_client.create_tag_if_not_exists.assert_any_call('Painting')
        # Should be called once for Painting (no granular tag because confidence is low)
        self.assertEqual(self.immich_client.add_tag_to_asset.call_count, 1)

    def test_no_painting_tag_for_photo(self):
        # Setup mock result for a photograph
        result_data = {
            'file_path': 'test_photo.jpg',
            'confidence': 0.1,
            'top_label': 'a photograph'
        }
        
        self.batch_processor._tag_asset_if_needed(self.immich_client, 'base_tag_id', 'test_photo.jpg', result_data)

        # Should NOT create Painting tag
        # Check that create_tag_if_not_exists was NOT called with 'Painting'
        calls = [args[0] for args, _ in self.immich_client.create_tag_if_not_exists.call_args_list]
        self.assertNotIn('Painting', calls)


if __name__ == '__main__':
    unittest.main()
