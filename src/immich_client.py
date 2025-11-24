import requests
import os
from typing import Optional, Dict


class ImmichClient:
    PAGE_SIZE = 1000

    def __init__(self, url: str, api_key: str, path_mappings: Dict[str, str] = None):
        self.url = url.rstrip('/')
        self.api_key = api_key
        # Normalize local paths in mappings to ensure OS-agnostic matching
        self.path_mappings = {}
        if path_mappings:
            for local, remote in path_mappings.items():
                self.path_mappings[os.path.normpath(local)] = remote

        self.headers = {
            'x-api-key': api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def get_asset_id_from_path(self, file_path: str) -> Optional[str]:
        """
        Try to find an asset in Immich by its original file path.
        """
        # Normalize input path for matching
        normalized_path = os.path.normpath(file_path)

        # Translate path
        translated_path = file_path # Default to original if no mapping found

        for local_prefix, remote_prefix in self.path_mappings.items():
            if normalized_path.startswith(local_prefix):
                # Replace prefix
                # Get the relative part of the path
                relative_path = normalized_path[len(local_prefix):]
                # If relative path starts with a separator, remove it
                if relative_path.startswith(os.sep):
                    relative_path = relative_path[1:]

                # Convert to forward slashes for Immich/Remote
                remote_suffix = relative_path.replace(os.sep, '/')

                # Join with remote prefix, ensuring single slash
                if remote_prefix.endswith('/'):
                    translated_path = remote_prefix + remote_suffix
                else:
                    translated_path = remote_prefix + '/' + remote_suffix
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
                    # Verify that the returned asset's path matches what we requested
                    asset = assets[0]
                    if asset.get('originalPath') == translated_path:
                        return asset['id']

        except Exception as e:
            print(f"Error searching for asset {file_path}: {e}")

        return None

    def reverse_path_mapping(self, immich_path: str) -> Optional[str]:
        """
        Convert Immich server path to local file path.
        """
        # Immich paths are always forward slashes
        for local_prefix, server_prefix in self.path_mappings.items():
            if immich_path.startswith(server_prefix):
                # Remove server prefix
                relative_path = immich_path[len(server_prefix):]

                # Remove leading slash if present
                if relative_path.startswith('/'):
                    relative_path = relative_path[1:]

                # Replace forward slashes with OS-appropriate separators
                relative_path = relative_path.replace('/', os.sep)

                # Join with local prefix using os.path.join for correct separator handling
                local_path = os.path.join(local_prefix, relative_path)

                # Normalize path separators for local OS
                return os.path.normpath(local_path)
        return None

    def create_tag_if_not_exists(self, tag_name: str) -> Optional[str]:
        """
        Create a tag if it doesn't exist, return its ID.
        """
        try:
            # First, list tags to see if it exists
            # First, list tags to see if it exists
            page = 1
            while True:
                response = requests.get(
                    f"{self.url}/api/tags",
                    headers=self.headers,
                    params={"page": page, "size": self.PAGE_SIZE}
                )
                
                if response.status_code != 200:
                    break
                    
                tags = response.json()
                # Handle potential different response formats (list vs dict with items)
                if isinstance(tags, dict) and 'items' in tags:
                    tags = tags['items']
                
                if not tags:
                    break
                    
                for tag in tags:
                    if tag['name'] == tag_name:
                        return tag['id']
                
                # If we got fewer items than limit, we're done
                if len(tags) < self.PAGE_SIZE:
                    break
                    
                page += 1

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
            # Use search/metadata endpoint with tag filter and pagination
            all_assets = []
            page = 1
            
            while True:
                response = requests.post(
                    f"{self.url}/api/search/metadata",
                    json={
                        "tagIds": [tag_id],
                        "page": page,
                        "size": self.PAGE_SIZE
                    },
                    headers=self.headers
                )
                
                if response.status_code == 200:
                    results = response.json()
                    assets = results.get('assets', {}).get('items', [])
                    
                    if not assets:
                        break
                        
                    all_assets.extend(assets)
                    
                    if len(assets) < self.PAGE_SIZE:
                        break
                        
                    page += 1
                else:
                    print(f"Failed to get assets for tag {tag_id} (page {page}): {response.text}")
                    break
                    
            return all_assets
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
