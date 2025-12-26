import unittest
from unittest.mock import MagicMock
from src.dedup_processor import DedupProcessor
from src.immich_client import ImmichClient


class TestDedupProcessor(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=ImmichClient)
        self.internal_path = "/upload"
        self.picture_library_path = "/pictures"
        self.processor = DedupProcessor(self.mock_client, self.internal_path, self.picture_library_path)

    def test_priority_logic(self):
        # Case 1: Picture Library > Internal > External
        # Group with all types
        group = [
            {'id': 'ext1', 'originalPath': '/external/file1.jpg', 'exifInfo': {'fileSizeInByte': 1000}},
            {'id': 'int1', 'originalPath': '/upload/file1.jpg', 'exifInfo': {'fileSizeInByte': 2000}},
            {'id': 'pic1', 'originalPath': '/pictures/file1.jpg', 'exifInfo': {'fileSizeInByte': 500}},
        ]
        self.mock_client.get_duplicate_assets.return_value = [{'assets': group}]
        
        to_del_count = self.processor.execute(dry_run=True)
        
        # 'pic1' is in picture library, so it should win even if smaller.
        # 'int1' and 'ext1' should be deleted.
        self.assertEqual(to_del_count, 2)
        
        # Case 2: Internal > External
        group2 = [
            {'id': 'ext2', 'originalPath': '/external/file2.jpg', 'exifInfo': {'fileSizeInByte': 3000}},
            {'id': 'int2', 'originalPath': '/upload/file2.jpg', 'exifInfo': {'fileSizeInByte': 1000}},
        ]
        self.mock_client.get_duplicate_assets.return_value = [{'assets': group2}]
        
        to_del_count = self.processor.execute(dry_run=True)
        # 'int2' wins. 'ext2' deleted.
        self.assertEqual(to_del_count, 1)

    def test_size_logic_within_priority(self):
        # Two internal assets, biggest wins
        group = [
            {'id': 'int1', 'originalPath': '/upload/small.jpg', 'exifInfo': {'fileSizeInByte': 1000}},
            {'id': 'int2', 'originalPath': '/upload/big.jpg', 'exifInfo': {'fileSizeInByte': 5000}},
        ]
        self.mock_client.get_duplicate_assets.return_value = [{'assets': group}]
        
        to_del_count = self.processor.execute(dry_run=True)
        # 'int2' wins. 'int1' deleted.
        self.assertEqual(to_del_count, 1)

    def test_no_duplicates(self):
        self.mock_client.get_duplicate_assets.return_value = []
        to_del_count = self.processor.execute(dry_run=True)
        self.assertEqual(to_del_count, 0)


if __name__ == '__main__':
    unittest.main()
