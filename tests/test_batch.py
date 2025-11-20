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

        self.output_csv = "test_output.csv"

        self.classifier = WatercolorClassifier()
        self.video_processor = VideoProcessor(self.classifier)
        self.batch_processor = BatchProcessor(self.classifier, self.video_processor)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.output_csv):
            os.remove(self.output_csv)

    def test_process_folder(self):
        self.batch_processor.process_folder(self.test_dir, self.output_csv)

        self.assertTrue(os.path.exists(self.output_csv))

        with open(self.output_csv, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertIn("file_path", rows[0])
        self.assertIn("is_watercolor", rows[0])

        # Check if paths are correct
        paths = [r["file_path"] for r in rows]
        self.assertIn(self.img1, paths)
        self.assertIn(self.img2, paths)

if __name__ == '__main__':
    unittest.main()
