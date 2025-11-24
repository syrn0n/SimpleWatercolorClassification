"""
Tests for AssetMover class
"""
import pytest
import os
import tempfile
from unittest.mock import Mock
from src.asset_mover import AssetMover
from src.immich_client import ImmichClient


@pytest.fixture
def mock_immich_client():
    """Create mock ImmichClient"""
    client = Mock(spec=ImmichClient)
    client.url = "http://test"
    client.api_key = "test-key"
    client.path_mappings = {
        r"E:\library\library\admin": "/data/library/admin"
    }
    return client


@pytest.fixture
def asset_mover(mock_immich_client):
    """Create AssetMover instance for testing"""
    return AssetMover(
        immich_client=mock_immich_client,
        destination_root=r"D:\archive",
        path_mappings={r"E:\library\library\admin": "/data/library/admin"},
        dry_run=False
    )


@pytest.fixture
def asset_mover_dry_run(mock_immich_client):
    """Create AssetMover instance in dry-run mode"""
    return AssetMover(
        immich_client=mock_immich_client,
        destination_root=r"D:\archive",
        path_mappings={r"E:\library\library\admin": "/data/library/admin"},
        dry_run=True
    )


class TestAssetMoverInit:
    """Test AssetMover initialization"""
    
    def test_init_normal_mode(self, mock_immich_client):
        """Test initialization in normal mode"""
        mover = AssetMover(mock_immich_client, r"D:\dest", {}, dry_run=False)
        assert mover.dry_run is False
        assert mover.transaction_log == []
    
    def test_init_dry_run_mode(self, mock_immich_client):
        """Test initialization in dry-run mode"""
        mover = AssetMover(mock_immich_client, r"D:\dest", {}, dry_run=True)
        assert mover.dry_run is True


class TestCalculateFileHash:
    """Test file hash calculation"""
    
    def test_calculate_hash_success(self, asset_mover):
        """Test successful hash calculation"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = f.name
        
        try:
            hash_result = asset_mover.calculate_file_hash(temp_path)
            assert hash_result is not None
            assert len(hash_result) == 64  # SHA-256 produces 64 hex characters
        finally:
            os.unlink(temp_path)
    
    def test_calculate_hash_nonexistent_file(self, asset_mover):
        """Test hash calculation for nonexistent file"""
        result = asset_mover.calculate_file_hash("nonexistent_file.txt")
        assert result is None
    
    def test_calculate_hash_consistent(self, asset_mover):
        """Test that same content produces same hash"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"consistent content")
            temp_path = f.name
        
        try:
            hash1 = asset_mover.calculate_file_hash(temp_path)
            hash2 = asset_mover.calculate_file_hash(temp_path)
            assert hash1 == hash2
        finally:
            os.unlink(temp_path)


class TestCalculateDestinationPath:
    """Test destination path calculation"""
    
    def test_calculate_destination_success(self, asset_mover):
        """Test successful destination path calculation"""
        immich_path = "/data/library/admin/2025/01/photo.jpg"
        result = asset_mover.calculate_destination_path(immich_path)
        
        assert result is not None
        assert "archive" in result
        assert "2025" in result
        assert "photo.jpg" in result
    
    def test_calculate_destination_no_mapping(self, asset_mover):
        """Test when no path mapping matches"""
        immich_path = "/other/path/photo.jpg"
        result = asset_mover.calculate_destination_path(immich_path)
        assert result is None
    
    def test_calculate_destination_normalizes_path(self, asset_mover):
        """Test that destination path is normalized"""
        immich_path = "/data/library/admin/folder/file.jpg"
        result = asset_mover.calculate_destination_path(immich_path)
        # Should use OS-appropriate separators
        assert os.sep in result


class TestMoveFile:
    """Test file moving functionality"""
    
    def test_move_file_success(self, asset_mover):
        """Test successful file move"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source file
            source_path = os.path.join(temp_dir, "source.txt")
            with open(source_path, 'w') as f:
                f.write("test content")
            
            # Define destination
            dest_path = os.path.join(temp_dir, "dest", "source.txt")
            
            result = asset_mover.move_file(source_path, dest_path)
            
            assert result is True
            assert os.path.exists(dest_path)
            assert not os.path.exists(source_path)
    
    def test_move_file_source_not_exists(self, asset_mover):
        """Test moving nonexistent source file"""
        result = asset_mover.move_file("nonexistent.txt", "dest.txt")
        assert result is False
    
    def test_move_file_destination_exists_same_hash(self, asset_mover):
        """Test when destination exists with same content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source and destination with same content
            source_path = os.path.join(temp_dir, "source.txt")
            dest_path = os.path.join(temp_dir, "dest.txt")
            
            content = "identical content"
            with open(source_path, 'w') as f:
                f.write(content)
            with open(dest_path, 'w') as f:
                f.write(content)
            
            result = asset_mover.move_file(source_path, dest_path)
            
            assert result is True
            assert not os.path.exists(source_path)  # Source should be removed
            assert os.path.exists(dest_path)
    
    def test_move_file_destination_exists_different_hash(self, asset_mover):
        """Test when destination exists with different content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "source.txt")
            dest_path = os.path.join(temp_dir, "dest.txt")
            
            with open(source_path, 'w') as f:
                f.write("source content")
            with open(dest_path, 'w') as f:
                f.write("different content")
            
            result = asset_mover.move_file(source_path, dest_path)
            
            assert result is False
            assert os.path.exists(source_path)  # Source should still exist
    
    def test_move_file_dry_run(self, asset_mover_dry_run):
        """Test file move in dry-run mode"""
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "source.txt")
            with open(source_path, 'w') as f:
                f.write("test")
            
            dest_path = os.path.join(temp_dir, "dest.txt")
            
            result = asset_mover_dry_run.move_file(source_path, dest_path)
            
            assert result is True
            assert os.path.exists(source_path)  # Source should still exist in dry-run
            assert not os.path.exists(dest_path)  # Destination should not be created


class TestSaveTransactionLog:
    """Test transaction log saving"""
    
    def test_save_transaction_log(self, asset_mover):
        """Test saving transaction log to JSON"""
        asset_mover.transaction_log = [
            {'asset_id': 'test-1', 'move_success': True},
            {'asset_id': 'test-2', 'move_success': False}
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f:
            temp_path = f.name
        
        try:
            asset_mover.save_transaction_log(temp_path)
            assert os.path.exists(temp_path)
            
            import json
            with open(temp_path, 'r') as f:
                data = json.load(f)
            
            assert 'timestamp' in data
            assert 'dry_run' in data
            assert 'transactions' in data
            assert len(data['transactions']) == 2
        finally:
            os.unlink(temp_path)


class TestSaveCSVReport:
    """Test CSV report saving"""
    
    def test_save_csv_report(self, asset_mover):
        """Test saving CSV report"""
        asset_mover.transaction_log = [
            {
                'asset_id': 'test-1',
                'immich_path': '/path1',
                'source_path': 'source1',
                'dest_path': 'dest1',
                'move_success': True,
                'delete_success': True,
                'error': None
            }
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
            temp_path = f.name
        
        try:
            asset_mover.save_csv_report(temp_path)
            assert os.path.exists(temp_path)
            
            with open(temp_path, 'r') as f:
                content = f.read()
            
            assert 'asset_id' in content
            assert 'test-1' in content
        finally:
            os.unlink(temp_path)


class TestProcessTaggedAssets:
    """Test processing of tagged assets"""
    
    def test_process_tagged_assets_success(self, asset_mover, mock_immich_client):
        """Test successful processing of tagged assets"""
        # Mock tag creation
        mock_immich_client.create_tag_if_not_exists.return_value = 'tag-123'
        
        # Mock getting assets
        mock_immich_client.get_assets_by_tag.return_value = [
            {'id': 'asset-1', 'originalPath': '/data/library/admin/photo1.jpg'},
            {'id': 'asset-2', 'originalPath': '/data/library/admin/photo2.jpg'}
        ]
        
        # Mock reverse path mapping
        mock_immich_client.reverse_path_mapping.side_effect = [
            r"E:\library\library\admin\photo1.jpg",
            r"E:\library\library\admin\photo2.jpg"
        ]
        
        # Mock delete
        mock_immich_client.delete_asset.return_value = True
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create source files
            source1 = os.path.join(temp_dir, "photo1.jpg")
            source2 = os.path.join(temp_dir, "photo2.jpg")
            with open(source1, 'w') as f:
                f.write("photo1")
            with open(source2, 'w') as f:
                f.write("photo2")
            
            # Update mover to use temp directory
            asset_mover.destination_root = temp_dir
            
            # Mock reverse mapping to return temp files
            mock_immich_client.reverse_path_mapping.side_effect = [source1, source2]
            
            results = asset_mover.process_tagged_assets('TestTag')
            
            assert results['total'] == 2
            assert results['moved'] == 2
            assert results['deleted'] == 2
            assert results['failed'] == 0
    
    def test_process_tagged_assets_no_tag(self, asset_mover, mock_immich_client):
        """Test when tag doesn't exist"""
        mock_immich_client.create_tag_if_not_exists.return_value = None
        
        results = asset_mover.process_tagged_assets('NonexistentTag')
        
        assert results['total'] == 0
        assert results['moved'] == 0
    
    def test_process_tagged_assets_no_assets(self, asset_mover, mock_immich_client):
        """Test when no assets have the tag"""
        mock_immich_client.create_tag_if_not_exists.return_value = 'tag-123'
        mock_immich_client.get_assets_by_tag.return_value = []
        
        results = asset_mover.process_tagged_assets('EmptyTag')
        
        assert results['total'] == 0
        assert results['moved'] == 0
    
    def test_process_tagged_assets_dry_run(self, asset_mover_dry_run, mock_immich_client):
        """Test processing in dry-run mode"""
        mock_immich_client.create_tag_if_not_exists.return_value = 'tag-123'
        mock_immich_client.get_assets_by_tag.return_value = [
            {'id': 'asset-1', 'originalPath': '/data/library/admin/photo.jpg'}
        ]
        
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "photo.jpg")
            with open(source, 'w') as f:
                f.write("test")
            
            mock_immich_client.reverse_path_mapping.return_value = source
            asset_mover_dry_run.destination_root = temp_dir
            
            results = asset_mover_dry_run.process_tagged_assets('TestTag')
            
            # In dry-run, files should not actually be moved or deleted
            assert results['moved'] == 1
            assert results['deleted'] == 1  # Simulated
            assert os.path.exists(source)  # Source still exists
            mock_immich_client.delete_asset.assert_not_called()

    def test_process_tagged_assets_sorting(self, asset_mover, mock_immich_client):
        """Test that assets are processed in alphabetical order"""
        mock_immich_client.create_tag_if_not_exists.return_value = 'tag-123'
        
        # Return assets in random order
        mock_immich_client.get_assets_by_tag.return_value = [
            {'id': 'asset-2', 'originalPath': '/b.jpg'},
            {'id': 'asset-1', 'originalPath': '/a.jpg'},
            {'id': 'asset-3', 'originalPath': '/c.jpg'}
        ]
        
        # Mock reverse mapping to return valid paths so processing continues
        mock_immich_client.reverse_path_mapping.side_effect = lambda x: f"E:{x.replace('/', os.sep)}"
        
        # Mock calculate_destination_path
        with pytest.MonkeyPatch.context() as m:
            m.setattr(asset_mover, 'calculate_destination_path', lambda x: f"D:{x.replace('/', os.sep)}")
            m.setattr(asset_mover, 'move_file', lambda x, y: True)
            m.setattr(asset_mover, 'calculate_file_hash', lambda x: 'hash')
            
            # We want to verify the order of processing.
            # We can inspect the calls to delete_asset, which happens after move.
            mock_immich_client.delete_asset.return_value = True
            
            asset_mover.process_tagged_assets('TestTag')
            
            # Verify delete_asset was called in the order of sorted original paths: a.jpg (asset-1), b.jpg (asset-2), c.jpg (asset-3)
            assert mock_immich_client.delete_asset.call_count == 3
            
            calls = mock_immich_client.delete_asset.call_args_list
            assert calls[0][0][0] == 'asset-1'
            assert calls[1][0][0] == 'asset-2'
            assert calls[2][0][0] == 'asset-3'
