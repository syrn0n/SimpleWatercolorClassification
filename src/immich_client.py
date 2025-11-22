import requests
import os
from typing import Optional, Dict

class ImmichClient:
    def __init__(self, url: str, api_key: str, path_mappings: Dict[str, str] = None):
        self.url = url.rstrip('/')
        self.api_key = api_key
        self.path_mappings = path_mappings or {}
        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def get_asset_id_from_path(self, file_path: str) -> Optional[str]:
        """
        Try to find an asset in Immich by its original file path.
        """
        # Translate path
        translated_path = file_path
        for local_prefix, remote_prefix in self.path_mappings.items():
            if file_path.startswith(local_prefix):
                # Replace prefix
                remote_suffix = file_path[len(local_prefix):]
                translated_path = remote_prefix + remote_suffix
                # Normalize slashes for remote (assuming Linux/Docker target)
                translated_path = translated_path.replace('\\', '/')
                break
        
        try:
            # Use the metadata search endpoint with originalPath
            search_url = f"{self.url}/api/search/metadata"
            payload = {
                "originalPath": translated_path
            }

            response = requests.post(
                search_url,
                json=payload,
                headers=self.headers
            )

            if response.status_code == 200:
                results = response.json()
                assets = results.get('assets', {}).get('items', [])

                if assets:
                    # Return the first match. 
                    # Since we searched by exact path, it should be the correct one.
                    return assets[0]['id']

        except Exception as e:
            print(f"Error searching for asset {file_path}: {e}")

        return None

    def reverse_path_mapping(self, immich_path: str) -> Optional[str]:
        """
        Convert Immich server path to local file path.
        """
        for local_prefix, server_prefix in self.path_mappings.items():
            if immich_path.startswith(server_prefix):
                # Remove server prefix
                relative_path = immich_path[len(server_prefix):]
                # Add local prefix
                local_path = local_prefix + relative_path
                # Normalize path separators for local OS
                return os.path.normpath(local_path)
        return None

    def create_tag_if_not_exists(self, tag_name: str) -> Optional[str]:
        """
        Create a tag if it doesn't exist, return its ID.
        """
        try:
            # First, list tags to see if it exists
            response = requests.get(f"{self.url}/api/tags", headers=self.headers)
            if response.status_code == 200:
                tags = response.json()
                for tag in tags:
                    if tag['name'] == tag_name:
                        return tag['id']

            # Create it
            response = requests.post(
                f"{self.url}/api/tags",
                json={"name": tag_name},
                headers=self.headers
            )
            if response.status_code in (200, 201):
                return response.json()['id']
            else:
                print(f"Failed to create tag {tag_name}: {response.text}")

        except Exception as e:
            print(f"Error creating tag {tag_name}: {e}")

        return None

    def add_tag_to_asset(self, asset_id: str, tag_id: str) -> bool:
        """
        Add a tag to an asset.
        """
        try:
            # PUT /api/tags/{id}/assets
            response = requests.put(
                f"{self.url}/api/tags/{tag_id}/assets",
                json={"ids": [asset_id]},
                headers=self.headers
            )
            return response.status_code in (200, 201)
        except Exception as e:
            print(f"Error adding tag to asset {asset_id}: {e}")
            return False

    def get_assets_by_tag(self, tag_id: str) -> list:
        """
        Get all assets with the specified tag.
        Uses search/metadata endpoint since there's no direct tag assets endpoint.
        """
        try:
            # Use search/metadata endpoint with tag filter
            response = requests.post(
                f"{self.url}/api/search/metadata",
                json={"tagIds": [tag_id]},
                headers=self.headers
            )
            if response.status_code == 200:
                results = response.json()
                assets = results.get('assets', {}).get('items', [])
                return assets
            else:
                print(f"Failed to get assets for tag {tag_id}: {response.text}")
                return []
        except Exception as e:
            print(f"Error getting assets for tag {tag_id}: {e}")
            return []

    def delete_asset(self, asset_id: str) -> bool:
        """
        Delete an asset from Immich.
        """
        try:
            response = requests.delete(
                f"{self.url}/api/assets",
                json={"ids": [asset_id]},
                headers=self.headers
            )
            return response.status_code in (200, 204)
        except Exception as e:
            print(f"Error deleting asset {asset_id}: {e}")
            return False
