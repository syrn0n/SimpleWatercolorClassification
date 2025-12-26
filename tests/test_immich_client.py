"""
Tests for ImmichClient class
"""
import pytest
import os
from unittest.mock import Mock, patch
from src.immich_client import ImmichClient


# Define OS-specific local prefix for testing
if os.name == 'nt':
    LOCAL_PREFIX = r"E:\library\library\admin"
else:
    LOCAL_PREFIX = "/tmp/library/admin"


@pytest.fixture
def immich_client():
    """Create ImmichClient instance for testing"""
    path_mappings = {
        LOCAL_PREFIX: "/data/library/admin"
    }
    return ImmichClient(
        url="http://test-server:2283",
        api_key="test-api-key",
        path_mappings=path_mappings
    )


class TestImmichClientInit:
    """Test ImmichClient initialization"""

    def test_init_with_path_mappings(self):
        """Test initialization with path mappings"""
        mappings = {"/local": "/remote"}
        client = ImmichClient("http://test", "key", mappings)
        assert client.url == "http://test"
        assert client.api_key == "key"
        expected_mappings = {os.path.normpath(k): v for k, v in mappings.items()}
        assert client.path_mappings == expected_mappings

    def test_init_without_path_mappings(self):
        """Test initialization without path mappings"""
        client = ImmichClient("http://test", "key")
        assert client.path_mappings == {}

    def test_url_trailing_slash_removed(self):
        """Test that trailing slash is removed from URL"""
        client = ImmichClient("http://test/", "key")
        assert client.url == "http://test"


class TestReversePathMapping:
    """Test reverse path mapping functionality"""

    def test_reverse_mapping_success(self, immich_client):
        """Test successful reverse path mapping"""
        immich_path = "/data/library/admin/2025/01/photo.jpg"
        # Construct expected path using OS-specific separator
        expected = os.path.join(LOCAL_PREFIX, "2025", "01", "photo.jpg")

        result = immich_client.reverse_path_mapping(immich_path)
        assert result == expected

    def test_reverse_mapping_no_match(self, immich_client):
        """Test reverse mapping with no matching prefix"""
        immich_path = "/other/path/photo.jpg"
        result = immich_client.reverse_path_mapping(immich_path)
        assert result is None

    def test_reverse_mapping_normalizes_separators(self, immich_client):
        """Test that path separators are normalized"""
        immich_path = "/data/library/admin/folder/file.jpg"
        result = immich_client.reverse_path_mapping(immich_path)
        # Should contain the OS separator
        assert os.sep in result


class TestGetAssetIdFromPath:
    """Test get_asset_id_from_path functionality"""

    @patch('src.immich_client.requests.post')
    def test_get_asset_id_success(self, mock_post, immich_client):
        """Test successful asset ID retrieval"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'assets': {
                'items': [
                    {'id': 'asset-123', 'originalPath': '/data/library/admin/photo.jpg'}
                ]
            }
        }
        mock_post.return_value = mock_response

        local_path = os.path.join(LOCAL_PREFIX, "photo.jpg")
        result = immich_client.get_asset_id_from_path(local_path)
        assert result == 'asset-123'

    @patch('src.immich_client.requests.post')
    def test_get_asset_id_no_results(self, mock_post, immich_client):
        """Test when no assets are found"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'assets': {'items': []}}
        mock_post.return_value = mock_response

        local_path = os.path.join(LOCAL_PREFIX, "photo.jpg")
        result = immich_client.get_asset_id_from_path(local_path)
        assert result is None

    @patch('src.immich_client.requests.post')
    def test_get_asset_id_request_error(self, mock_post, immich_client):
        """Test handling of request errors"""
        mock_post.side_effect = Exception("Network error")

        local_path = os.path.join(LOCAL_PREFIX, "photo.jpg")
        result = immich_client.get_asset_id_from_path(local_path)
        assert result is None


class TestCreateTagIfNotExists:
    """Test create_tag_if_not_exists functionality"""

    @patch('src.immich_client.requests.get')
    def test_tag_already_exists(self, mock_get, immich_client):
        """Test when tag already exists"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {'id': 'tag-123', 'name': 'Watercolor'},
            {'id': 'tag-456', 'name': 'Other'}
        ]
        mock_get.return_value = mock_response

        result = immich_client.create_tag_if_not_exists('Watercolor')
        assert result == 'tag-123'
        # Verify pagination params were used
        mock_get.assert_called_with(
            f"{immich_client.url}/api/tags",
            headers=immich_client.headers,
            params={"page": 1, "size": ImmichClient.PAGE_SIZE}
        )

    @patch('src.immich_client.requests.post')
    @patch('src.immich_client.requests.get')
    def test_create_new_tag(self, mock_get, mock_post, immich_client):
        """Test creating a new tag"""
        mock_get_response = Mock()
        mock_get_response.status_code = 200
        mock_get_response.json.return_value = []
        mock_get.return_value = mock_get_response

        mock_post_response = Mock()
        mock_post_response.status_code = 201
        mock_post_response.json.return_value = {'id': 'new-tag-123'}
        mock_post.return_value = mock_post_response

        result = immich_client.create_tag_if_not_exists('NewTag')
        assert result == 'new-tag-123'

    @patch('src.immich_client.requests.get')
    def test_create_tag_error(self, mock_get, immich_client):
        """Test error handling in tag creation"""
        mock_get.side_effect = Exception("API error")

        result = immich_client.create_tag_if_not_exists('Tag')
        assert result is None


class TestAddTagToAsset:
    """Test add_tag_to_asset functionality"""

    @patch('src.immich_client.requests.put')
    def test_add_tag_success(self, mock_put, immich_client):
        """Test successful tag addition"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_put.return_value = mock_response

        result = immich_client.add_tag_to_asset('asset-123', 'tag-456')
        assert result is True

    @patch('src.immich_client.requests.put')
    def test_add_tag_failure(self, mock_put, immich_client):
        """Test failed tag addition"""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_put.return_value = mock_response

        result = immich_client.add_tag_to_asset('asset-123', 'tag-456')
        assert result is False


class TestGetAssetsByTag:
    """Test get_assets_by_tag functionality"""

    @patch('src.immich_client.requests.post')
    def test_get_assets_success(self, mock_post, immich_client):
        """Test successful retrieval of tagged assets"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'assets': {
                'items': [
                    {'id': 'asset-1', 'originalPath': '/path1'},
                    {'id': 'asset-2', 'originalPath': '/path2'}
                ]
            }
        }
        mock_post.return_value = mock_response

        result = immich_client.get_assets_by_tag('tag-123')
        assert len(result) == 2
        assert result[0]['id'] == 'asset-1'
        
        # Verify pagination params
        mock_post.assert_called_with(
            f"{immich_client.url}/api/search/metadata",
            json={"tagIds": ['tag-123'], "page": 1, "size": ImmichClient.PAGE_SIZE},
            headers=immich_client.headers
        )

    @patch('src.immich_client.requests.post')
    def test_get_assets_pagination(self, mock_post, immich_client):
        """Test pagination for assets"""
        # Page 1 response (full page, implying more pages might exist)
        page1_items = [{'id': f'asset-{i}', 'originalPath': f'/path{i}'} for i in range(ImmichClient.PAGE_SIZE)]
        response1 = Mock()
        response1.status_code = 200
        response1.json.return_value = {'assets': {'items': page1_items}}
        
        # Page 2 response (partial page, end of list)
        page2_items = [{'id': f'asset-{ImmichClient.PAGE_SIZE + 1}', 'originalPath': f'/path{ImmichClient.PAGE_SIZE + 1}'}]
        response2 = Mock()
        response2.status_code = 200
        response2.json.return_value = {'assets': {'items': page2_items}}
        
        mock_post.side_effect = [response1, response2]

        result = immich_client.get_assets_by_tag('tag-123')
        
        assert len(result) == ImmichClient.PAGE_SIZE + 1
        assert result[0]['id'] == 'asset-0'
        assert result[-1]['id'] == f'asset-{ImmichClient.PAGE_SIZE + 1}'
        
        assert mock_post.call_count == 2
        # Check calls
        mock_post.assert_any_call(
            f"{immich_client.url}/api/search/metadata",
            json={"tagIds": ['tag-123'], "page": 1, "size": ImmichClient.PAGE_SIZE},
            headers=immich_client.headers
        )
        mock_post.assert_any_call(
            f"{immich_client.url}/api/search/metadata",
            json={"tagIds": ['tag-123'], "page": 2, "size": ImmichClient.PAGE_SIZE},
            headers=immich_client.headers
        )

    @patch('src.immich_client.requests.post')
    def test_get_assets_empty(self, mock_post, immich_client):
        """Test when no assets have the tag"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'assets': {'items': []}}
        mock_post.return_value = mock_response

        result = immich_client.get_assets_by_tag('tag-123')
        assert result == []


class TestDeleteAsset:
    """Test delete_asset functionality"""

    @patch('src.immich_client.requests.delete')
    def test_delete_asset_success(self, mock_delete, immich_client):
        """Test successful asset deletion"""
        mock_response = Mock()
        mock_response.status_code = 204
        mock_delete.return_value = mock_response

        result = immich_client.delete_asset('asset-123')
        assert result is True

    @patch('src.immich_client.requests.delete')
    def test_delete_asset_failure(self, mock_delete, immich_client):
        """Test failed asset deletion"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_delete.return_value = mock_response

        result = immich_client.delete_asset('asset-123')
        assert result is False

    @patch('src.immich_client.requests.delete')
    def test_delete_asset_exception(self, mock_delete, immich_client):
        """Test exception handling in asset deletion"""
        mock_delete.side_effect = Exception("Network error")

        result = immich_client.delete_asset('asset-123')
        assert result is False
