import unittest
from src.batch_processor import BatchProcessor

class TestGranularLabels(unittest.TestCase):
    def test_get_granular_tag(self):
        # Test existing labels
        self.assertEqual(BatchProcessor.get_granular_tag(0.90), "Watercolor85")
        self.assertEqual(BatchProcessor.get_granular_tag(0.80), "Watercolor75")
        self.assertEqual(BatchProcessor.get_granular_tag(0.70), "Watercolor65")
        self.assertEqual(BatchProcessor.get_granular_tag(0.60), "Watercolor55")
        
        # Test new labels
        self.assertEqual(BatchProcessor.get_granular_tag(0.50), "Watercolor45")
        self.assertEqual(BatchProcessor.get_granular_tag(0.40), "Watercolor35")
        
        # Test below threshold
        self.assertIsNone(BatchProcessor.get_granular_tag(0.30))

if __name__ == '__main__':
    unittest.main()
