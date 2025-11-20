import requests
import os
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

        Note: Immich doesn't have a direct "get by path" endpoint that is efficiently indexed for all versions.
        We will try to use the search API or metadata search if available.

        As a fallback/primary strategy for many setups, we can search by filename and filter by path.
        """
        filename = os.path.basename(file_path)

        # Strategy: Search by filename
        # Endpoint: /api/search/metadata (if available) or /api/asset/search (older) or /api/search/smart
        # Let's try the standard asset search/filtering if possible.
        # Actually, /api/asset/ has a check mechanism?

        # Let's try to search by originalFileName
        try:
            # Using the search endpoint which is quite general
            # Note: The API might change between versions.
            # We'll try a POST to /api/search/metadata if it exists, or just GET /api/asset with originalFileName?
            # GET /api/asset doesn't filter by name easily in all versions.

            # Let's try the 'search' endpoint.
            search_url = f"{self.url}/api/search/metadata"
            payload = {
                "originalFileName": filename
            }
            # Note: This endpoint might not exist in all versions.
            # Alternative: POST /api/asset/check (checks if assets exist, returns IDs?) - usually for upload.

            # Let's try a simpler approach: Search by text (filename)
            # GET /api/search?q=filename
            response = requests.get(
                f"{self.url}/api/search",
                params={"q": filename, "clip": "false"},
                headers=self.headers
            )

            if response.status_code == 200:
                results = response.json()
                # results['assets']['items'] usually
                assets = results.get('assets', {}).get('items', [])

                for asset in assets:
                    # Check if the path matches
                    # The asset object usually has 'originalPath'
                    original_path = asset.get('originalPath')

                    # Apply path mappings to local file_path for comparison
                    mapped_path = file_path
                    for local_prefix, immich_prefix in self.path_mappings.items():
                        if file_path.startswith(local_prefix):
                            mapped_path = file_path.replace(local_prefix, immich_prefix, 1)
                            break

                    if original_path and original_path == mapped_path:
                        return asset['id']

                    # If paths are slightly different (e.g. mount points), we might need loose matching.
                    # For now, strict match or filename match if unique?
                    # Let's stick to strict match if possible, or at least filename match if the user accepts it.
                    # But the user asked for "maps physical path".

                    # If originalPath is not exposed, we might be stuck.
                    # But usually it is for the admin/owner.
                    pass

                # Fallback: if we found assets with the exact filename and there's only one, maybe return it?
                # Risk of false positive.
                # Let's try to be safe. If we can't verify the path, we shouldn't tag.

        except Exception as e:
            print(f"Error searching for asset {filename}: {e}")

        return None

    def create_tag_if_not_exists(self, tag_name: str) -> Optional[str]:
        """
        Create a tag if it doesn't exist, return its ID.
        """
        try:
            # First, list tags to see if it exists
            response = requests.get(f"{self.url}/api/tag", headers=self.headers)
            if response.status_code == 200:
                tags = response.json()
                for tag in tags:
                    if tag['name'] == tag_name:
                        return tag['id']

            # Create it
            response = requests.post(
                f"{self.url}/api/tag",
                json={"name": tag_name, "type": "CUSTOM"}, # 'type' might not be needed or might be different
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
            # PUT /api/tag/{id}/assets
            response = requests.put(
                f"{self.url}/api/tag/{tag_id}/assets",
                json={"ids": [asset_id]},
                headers=self.headers
            )
            return response.status_code in (200, 201)
        except Exception as e:
            print(f"Error adding tag to asset {asset_id}: {e}")
            return False
