import unittest
import os
from src.immich_client import ImmichClient

class TestPathTranslation(unittest.TestCase):
    def test_translate_path_with_mapping(self):
        mappings = {
            "C:\\Photos": "/usr/src/app/upload/library/admin",
            "D:\\Media": "/mnt/media"
        }
        client = ImmichClient("http://localhost:2283", "api-key", mappings)
        
        # Test Windows local path
        local_path = "C:\\Photos\\2025\\vacation.jpg"
        translated = client.translate_path_to_immich(local_path)
        self.assertEqual(translated, "/usr/src/app/upload/library/admin/2025/vacation.jpg")
        
        # Test path without mapping (should just normalize slashes)
        local_path = "E:\\Temp\\test.png"
        translated = client.translate_path_to_immich(local_path)
        self.assertEqual(translated, "E:/Temp/test.png")

    def test_path_normalization_cleanup(self):
        mappings = {
            "C:\\Photos": "/usr/src/app/upload/"
        }
        client = ImmichClient("http://localhost:2283", "api-key", mappings)
        
        # Test double slash prevention
        local_path = "C:\\Photos\\test.jpg"
        translated = client.translate_path_to_immich(local_path)
        self.assertEqual(translated, "/usr/src/app/upload/test.jpg")
        
    def test_reverse_mapping(self):
        mappings = {
            "C:\\Photos": "/usr/src/app/upload/library/admin"
        }
        client = ImmichClient("http://localhost:2283", "api-key", mappings)
        
        server_path = "/usr/src/app/upload/library/admin/2025/photo.jpg"
        local_path = client.reverse_path_mapping(server_path)
        
        expected = os.path.normpath("C:\\Photos\\2025\\photo.jpg")
        self.assertEqual(local_path, expected)

if __name__ == '__main__':
    unittest.main()
