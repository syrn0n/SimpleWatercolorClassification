import unittest
import os
import shutil
import tempfile
import sqlite3
from pathlib import Path
from src.database import DatabaseManager

class TestDatabaseManager(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_cache.db")
        self.db = DatabaseManager(self.db_path)
        
        # Create some dummy files
        self.file1 = os.path.join(self.test_dir, "file1.jpg")
        with open(self.file1, "wb") as f:
            f.write(b"content1")
            
        self.file2 = os.path.join(self.test_dir, "file2.jpg")
        with open(self.file2, "wb") as f:
            f.write(b"content2")

    def tearDown(self):
        # Close database connection
        if hasattr(self.db, 'conn'):
            self.db.conn.close()
        # Remove temporary directory
        shutil.rmtree(self.test_dir)

    def test_init_creates_schema(self):
        """Test that initialization creates the table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='classification_results'")
        result = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(result)

    def test_hashing(self):
        """Test file hashing."""
        hash1 = self.db._get_file_hash(self.file1)
        hash2 = self.db._get_file_hash(self.file2)
        self.assertNotEqual(hash1, hash2)
        
        # Same content should have same hash
        file1_copy = os.path.join(self.test_dir, "file1_copy.jpg")
        with open(file1_copy, "wb") as f:
            f.write(b"content1")
        hash1_copy = self.db._get_file_hash(file1_copy)
        self.assertEqual(hash1, hash1_copy)

    def test_save_and_retrieve(self):
        """Test saving and retrieving results."""
        result_data = {
            "is_watercolor": True,
            "confidence": 0.95,
            "extra_field": "value",
            "file_type": "image"
        }
        
        # Save
        self.db.save_result(self.file1, result_data)
        
        # Check if processed
        needs_processing, cached_result = self.db.check_if_processed(self.file1)
        self.assertFalse(needs_processing)
        self.assertIsNotNone(cached_result)
        self.assertTrue(cached_result["is_watercolor"])
        self.assertEqual(cached_result["confidence"], 0.95)
        self.assertEqual(cached_result["file_path"], self.file1)

    def test_cache_miss(self):
        """Test cache miss for new file."""
        needs_processing, cached_result = self.db.check_if_processed(self.file2)
        self.assertTrue(needs_processing)
        self.assertIsNone(cached_result)

    def test_moved_file_detection(self):
        """Test detecting a moved file."""
        result_data = {"is_watercolor": True, "confidence": 0.9, "file_type": "image"}
        self.db.save_result(self.file1, result_data)
        
        # Move file1 to new location
        new_path = os.path.join(self.test_dir, "file1_moved.jpg")
        os.rename(self.file1, new_path)
        
        # Check if processed at new path
        needs_processing, cached_result = self.db.check_if_processed(new_path)
        
        # Should be found via hash
        self.assertFalse(needs_processing)
        self.assertIsNotNone(cached_result)
        self.assertEqual(cached_result["file_path"], new_path)
        
        # Verify database was updated
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM classification_results WHERE file_path = ?", (new_path,))
        row = cursor.fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_modified_file(self):
        """Test that modified file triggers reprocessing."""
        result_data = {"is_watercolor": True, "confidence": 0.9, "file_type": "image"}
        self.db.save_result(self.file1, result_data)
        
        # Modify file content
        with open(self.file1, "wb") as f:
            f.write(b"modified_content")
            
        # Check if processed
        needs_processing, cached_result = self.db.check_if_processed(self.file1)
        self.assertTrue(needs_processing)

    def test_clear_cache(self):
        """Test clearing the cache."""
        self.db.save_result(self.file1, {"file_type": "image"})
        self.db.clear_cache()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM classification_results")
        count = cursor.fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_statistics(self):
        """Test getting statistics."""
        self.db.save_result(self.file1, {"is_watercolor": True, "file_type": "image"})
        self.db.save_result(self.file2, {"is_watercolor": False, "file_type": "video"})
        
        stats = self.db.get_statistics()
        self.assertEqual(stats["total_files"], 2)
        self.assertEqual(stats["images"], 1)
        self.assertEqual(stats["videos"], 1)
        self.assertEqual(stats["watercolors"], 1)

if __name__ == '__main__':
    unittest.main()
