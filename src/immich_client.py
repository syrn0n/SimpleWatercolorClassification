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
        self._asset_path_map = None

    def get_asset_id_from_path(self, file_path: str) -> Optional[str]:
        """
        Try to find an asset in Immich by its original file path.
        """
        # If we have a cached map, use it
        if self._asset_path_map is not None:
            # We need to translate the path first to match what Immich has
            translated_path = self.translate_path_to_immich(file_path)
            return self._asset_path_map.get(translated_path)

        # Fallback to metadata search
        # Normalize input path for matching
        normalized_path = os.path.normpath(file_path)
        translated_path = self.translate_path_to_immich(file_path)

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

    def translate_path_to_immich(self, local_path: str) -> str:
        """Translate a local file path to an Immich originalPath."""
        normalized_path = os.path.normpath(local_path)
        translated_path = local_path # Default

        for local_prefix, remote_prefix in self.path_mappings.items():
            # Handle case-insensitive path matching on Windows
            if os.name == 'nt':
                matches = normalized_path.lower().startswith(local_prefix.lower())
            else:
                matches = normalized_path.startswith(local_prefix)

            if matches:
                relative_path = normalized_path[len(local_prefix):]
                if relative_path.startswith(os.sep):
                    relative_path = relative_path[1:]

                remote_suffix = relative_path.replace(os.sep, '/')
                if remote_prefix.endswith('/'):
                    translated_path = remote_prefix + remote_suffix
                else:
                    translated_path = remote_prefix + '/' + remote_suffix
                break
        return translated_path

    def prefetch_asset_path_map(self):
        """Pre-fetch all assets from Immich and build a path -> ID map for performance."""
        print("Pre-fetching asset list from Immich for performance optimization...")
        self._asset_path_map = {}
        skip = 0
        take = self.PAGE_SIZE
        endpoint = "/api/assets"
        
        # Test which endpoint works (some versions use /api/asset, others /api/assets)
        try:
            test_resp = requests.get(f"{self.url}{endpoint}", headers=self.headers, params={"skip": 0, "take": 1})
            if test_resp.status_code == 404:
                endpoint = "/api/asset"
        except:
            endpoint = "/api/asset"

        while True:
            try:
                response = requests.get(
                    f"{self.url}{endpoint}",
                    headers=self.headers,
                    params={"skip": skip, "take": take}
                )
                if response.status_code != 200:
                    print(f"Error fetching assets: HTTP {response.status_code} from {endpoint}")
                    break
                
                assets = response.json()
                if not assets or not isinstance(assets, list):
                    if skip == 0:
                        print(f"No assets returned from {endpoint}.")
                    break
                
                # Debug: check keys of first asset to ensure originalPath exists
                if skip == 0 and assets:
                    first_asset = assets[0]
                    if 'originalPath' not in first_asset:
                        print(f"Warning: 'originalPath' not found in asset metadata. Available keys: {list(first_asset.keys())}")

                for asset in assets:
                    path = asset.get('originalPath')
                    if path:
                        self._asset_path_map[path] = asset.get('id')
                
                if len(assets) < take:
                    break
                skip += take
            except Exception as e:
                print(f"Error pre-fetching assets: {e}")
                break
        print(f"Loaded {len(self._asset_path_map)} assets into path map.")

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

    def add_tags_to_assets(self, asset_ids: list, tag_id: str, skip_existing: bool = True) -> bool:
        """
        Add a tag to multiple assets in a single API call.
        
        Args:
            asset_ids: List of asset IDs to tag
            tag_id: Tag ID to apply
            skip_existing: If True, only tag assets that don't already have this tag
            
        Returns:
            True if successful, False otherwise
        """
        if not asset_ids:
            return True
            
        try:
            # If skip_existing, get current assets with this tag and filter them out
            if skip_existing:
                existing_assets = self.get_assets_by_tag(tag_id)
                existing_ids = {asset['id'] for asset in existing_assets}
                asset_ids = [aid for aid in asset_ids if aid not in existing_ids]
                
                if not asset_ids:
                    # All assets already have this tag
                    return True
            
            # PUT /api/tags/{id}/assets with multiple IDs
            response = requests.put(
                f"{self.url}/api/tags/{tag_id}/assets",
                json={"ids": asset_ids},
                headers=self.headers
            )
            return response.status_code in (200, 201)
        except Exception as e:
            print(f"Error adding tag to assets: {e}")
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
        return self.delete_assets([asset_id])

    def empty_trash(self) -> bool:
        """
        Permanently delete all items in the trash.
        """
        try:
            response = requests.post(
                f"{self.url}/api/trash/empty",
                headers=self.headers
            )
            return response.status_code in (200, 201, 204)
        except Exception as e:
            print(f"Error emptying trash: {e}")
            return False

    def get_duplicate_assets(self) -> list:
        """
        Get all duplicate asset groups from Immich.
        """
        try:
            response = requests.get(
                f"{self.url}/api/duplicates",
                headers=self.headers
            )
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Failed to get duplicates: {response.text}")
                return []
        except Exception as e:
            print(f"Error getting duplicates: {e}")
            return []

    def delete_assets(self, asset_ids: list) -> bool:
        """
        Delete multiple assets from Immich in bulk.
        """
        if not asset_ids:
            return True
            
        try:
            # POST /api/assets (DELETE method with body containing IDs)
            # Actually Immich uses DELETE /api/assets with a body
            response = requests.delete(
                f"{self.url}/api/assets",
                json={"ids": asset_ids},
                headers=self.headers
            )
            return response.status_code in (200, 204)
        except Exception as e:
            print(f"Error deleting assets: {e}")
            return False
