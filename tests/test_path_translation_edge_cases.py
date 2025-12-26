import pytest
import os
from src.immich_client import ImmichClient


class TestPathTranslationEdgeCases:
    def test_prefix_boundary_match(self):
        """Test that mapping only matches at directory boundaries."""
        mappings = {
            os.path.normpath("C:/Photos"): "/library"
        }
        client = ImmichClient("http://test", "key", mappings)
        
        # This should NOT match C:/Photos
        non_matching_path = os.path.normpath("C:/Photos-Extended/img.jpg")
        translated = client.translate_path_to_immich(non_matching_path)
        
        # If no mapping matched, it should just be normalized
        # On Windows, this would be C:/Photos-Extended/img.jpg
        # On Linux, this would be C:/Photos-Extended/img.jpg
        expected_default = non_matching_path.replace(os.sep, '/')
        assert translated == expected_default
        assert "/library" not in translated

    def test_trailing_slash_in_mapping(self):
        """Test that trailing slashes in mappings are handled correctly."""
        mappings = {
            os.path.normpath("C:/Photos/"): "/library/"
        }
        client = ImmichClient("http://test", "key", mappings)
        
        path = os.path.normpath("C:/Photos/vacation/img.jpg")
        translated = client.translate_path_to_immich(path)
        assert translated == "/library/vacation/img.jpg"

    def test_multiple_slashes_in_input(self):
        """Test that multiple slashes in input path are collapsed."""
        client = ImmichClient("http://test", "key", {})
        
        if os.name == 'nt':
            path = "C:\\\\Photos\\\\\\img.jpg"
        else:
            path = "//data///photos//img.jpg"
            
        translated = client.translate_path_to_immich(path)
        assert "//" not in translated[1:] # Allow leading // for UNC if necessary, but generally avoid

    def test_windows_drive_letter_no_mapping(self):
        """Test how Windows drive letters are handled when no mapping is present."""
        if os.name != 'nt':
            pytest.skip("Windows specific test")
            
        client = ImmichClient("http://test", "key", {})
        path = "C:\\Photos\\img.jpg"
        translated = client.translate_path_to_immich(path)
        
        # Current behavior: C:/Photos/img.jpg
        # Future might want: /C/Photos/img.jpg or similar if Immich expects absolute Linux paths
        # For now, let's just assert current behavior doesn't break horribly
        assert translated == "C:/Photos/img.jpg"
