import os
import sys
from PIL import Image
import unittest
from src.classifier import WatercolorClassifier

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestWatercolorClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = WatercolorClassifier()
        # Create a dummy image
        self.test_image_path = "test_image.jpg"
        img = Image.new('RGB', (224, 224), color = 'red')
        img.save(self.test_image_path)

    def tearDown(self):
        if os.path.exists(self.test_image_path):
            os.remove(self.test_image_path)

    def test_predict_structure(self):
        """Test that predict returns a dictionary with expected keys and values."""
        probs = self.classifier.predict(self.test_image_path)

        self.assertIsInstance(probs, dict)
        self.assertIn("a watercolor painting", probs)
        self.assertIn("a photograph", probs)

        # Sum of probs should be roughly 1.0 (softmax)
        total_prob = sum(probs.values())
        self.assertAlmostEqual(total_prob, 1.0, places=4)

    def test_is_watercolor_logic(self):
        """Test the boolean logic (even if result is not meaningful for a red square)."""
        is_wc = self.classifier.is_watercolor(self.test_image_path)
        self.assertIsInstance(is_wc, bool)

if __name__ == '__main__':
    unittest.main()
