import pytest
from src.batch_processor import BatchProcessor


class TestGranularLabels:
    """Test granular tag logic."""

    def test_get_granular_tag_watercolor85(self):
        """Test tag for confidence >= 0.85."""
        assert BatchProcessor.get_granular_tag(0.85) == "Watercolor85"
        assert BatchProcessor.get_granular_tag(0.90) == "Watercolor85"
        assert BatchProcessor.get_granular_tag(1.0) == "Watercolor85"

    def test_get_granular_tag_watercolor75(self):
        """Test tag for 0.75 <= confidence < 0.85."""
        assert BatchProcessor.get_granular_tag(0.75) == "Watercolor75"
        assert BatchProcessor.get_granular_tag(0.80) == "Watercolor75"
        assert BatchProcessor.get_granular_tag(0.8499) == "Watercolor75"

    def test_get_granular_tag_watercolor65(self):
        """Test tag for 0.65 <= confidence < 0.75."""
        assert BatchProcessor.get_granular_tag(0.65) == "Watercolor65"
        assert BatchProcessor.get_granular_tag(0.70) == "Watercolor65"
        assert BatchProcessor.get_granular_tag(0.7499) == "Watercolor65"

    def test_get_granular_tag_watercolor55(self):
        """Test tag for 0.55 <= confidence < 0.65."""
        assert BatchProcessor.get_granular_tag(0.55) == "Watercolor55"
        assert BatchProcessor.get_granular_tag(0.60) == "Watercolor55"
        assert BatchProcessor.get_granular_tag(0.6499) == "Watercolor55"

    def test_get_granular_tag_below_threshold(self):
        """Test that confidence below 0.55 returns None."""
        assert BatchProcessor.get_granular_tag(0.54) is None
        assert BatchProcessor.get_granular_tag(0.50) is None
        assert BatchProcessor.get_granular_tag(0.0) is None

    def test_get_granular_tag_boundary_values(self):
        """Test exact boundary values."""
        # Test exact boundaries
        assert BatchProcessor.get_granular_tag(0.85) == "Watercolor85"
        assert BatchProcessor.get_granular_tag(0.75) == "Watercolor75"
        assert BatchProcessor.get_granular_tag(0.65) == "Watercolor65"
        assert BatchProcessor.get_granular_tag(0.55) == "Watercolor55"
        
        # Test just below boundaries
        assert BatchProcessor.get_granular_tag(0.8499999) == "Watercolor75"
        assert BatchProcessor.get_granular_tag(0.7499999) == "Watercolor65"
        assert BatchProcessor.get_granular_tag(0.6499999) == "Watercolor55"
        assert BatchProcessor.get_granular_tag(0.5499999) is None
