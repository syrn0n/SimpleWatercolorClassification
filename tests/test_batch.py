import os
import sys
import shutil
import csv
from PIL import Image
import unittest
from src.classifier import WatercolorClassifier
from src.video_processor import VideoProcessor
from src.batch_processor import BatchProcessor

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


class TestBatchProcessor(unittest.TestCase):
    def setUp(self):
        self.test_dir = "test_batch_folder"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

        # Create dummy images
        self.img1 = os.path.join(self.test_dir, "img1.jpg")
        self.img2 = os.path.join(self.test_dir, "img2.png")

        Image.new('RGB', (100, 100), color='red').save(self.img1)
        Image.new('RGB', (100, 100), color='blue').save(self.img2)

        self.db_path = "test_batch.db"
        self.classifier = WatercolorClassifier(db_path=self.db_path, use_cache=True)
        self.video_processor = VideoProcessor(self.classifier, db_path=self.db_path, use_cache=True)
        self.batch_processor = BatchProcessor(self.classifier, self.video_processor)

    def tearDown(self):
        if self.classifier.db:
            self.classifier.db.close()
        if self.video_processor.db:
            self.video_processor.db.close()
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_process_folder(self):
        self.batch_processor.process_folder(self.test_dir)

        # Verify results in database
        db = self.classifier.db
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM classification_results")
        rows = cursor.fetchall()

        self.assertEqual(len(rows), 2)
        
        paths = [r['file_path'] for r in rows]
        # Normalize paths for comparison
        paths = [os.path.normpath(p) for p in paths]
        self.assertIn(os.path.normpath(self.img1), paths)
        self.assertIn(os.path.normpath(self.img2), paths)


if __name__ == '__main__':
    unittest.main()
