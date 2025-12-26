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
            translated_path = self.translate_path_to_immich(file_path)
            asset_id = self._find_asset_in_cache(translated_path)
            if asset_id:
                return asset_id

        # Fallback to metadata search
        return self._search_asset_by_metadata(file_path)

    def _find_asset_in_cache(self, translated_path: str) -> Optional[str]:
        """Look for translated path in the cached asset map."""
        asset_id = self._asset_path_map.get(translated_path)
        if asset_id:
            return asset_id
        
        # Try with/without leading slash
        if translated_path.startswith('/'):
            return self._asset_path_map.get(translated_path[1:])
        else:
            return self._asset_path_map.get('/' + translated_path)

    def _search_asset_by_metadata(self, file_path: str) -> Optional[str]:
        """Search for asset using API metadata search."""
        translated_path = self.translate_path_to_immich(file_path)
        
        # Paths to try (original, without leading slash, with leading slash)
        paths_to_try = [translated_path]
        if translated_path.startswith('/'):
            paths_to_try.append(translated_path[1:])
        else:
            paths_to_try.append('/' + translated_path)

        for path in paths_to_try:
            try:
                search_url = f"{self.url}/api/search/metadata"
                response = requests.post(
                    search_url,
                    json={"originalPath": path},
                    headers=self.headers
                )

                if response.status_code == 200:
                    results = response.json()
                    assets = results.get('assets', {}).get('items', [])
                    if assets and assets[0].get('originalPath') == path:
                        return assets[0]['id']
            except Exception as e:
                print(f"Error searching for asset {file_path} at path {path}: {e}")
        return None

    def translate_path_to_immich(self, local_path: str) -> str:
        """Translate a local file path to an Immich originalPath."""
        local_path_forward = local_path.replace('\\', '/')
        
        # Default: just ensure all slashes are forward
        translated_path = local_path_forward

        for local_prefix, remote_prefix in self.path_mappings.items():
            local_prefix_forward = local_prefix.replace('\\', '/')
            
            # Case-insensitive if it looks like a Windows path (drive letter or unc)
            is_windows_path = ':' in local_path_forward or local_path_forward.startswith('//')
            if os.name == 'nt' or is_windows_path:
                prefix_matches = local_path_forward.lower().startswith(local_prefix_forward.lower())
            else:
                prefix_matches = local_path_forward.startswith(local_prefix_forward)

            if prefix_matches:
                # Ensure it's a true prefix match by checking separator at boundary
                if len(local_path_forward) > len(local_prefix_forward):
                    if local_path_forward[len(local_prefix_forward)] != '/':
                        continue
                
                relative_path = local_path_forward[len(local_prefix_forward):].lstrip('/')
                remote_prefix_clean = remote_prefix.replace('\\', '/')
                
                if remote_prefix_clean.endswith('/'):
                    translated_path = remote_prefix_clean + relative_path
                else:
                    translated_path = remote_prefix_clean + '/' + relative_path
                break
        
        # Final cleanup: collapse multiple slashes
        is_abs = translated_path.startswith('/')
        parts = [p for p in translated_path.split('/') if p]
        translated_path = '/'.join(parts)
        if is_abs:
            translated_path = '/' + translated_path
            
        return translated_path

    def prefetch_asset_path_map(self):
        """Pre-fetch all assets from Immich and build a path -> ID map for performance."""
        print("Pre-fetching asset list from Immich for performance optimization...")
        self._asset_path_map = {}
        page = 1
        page_size = self.PAGE_SIZE
        
        while True:
            try:
                response = self._fetch_assets_page(page, page_size)
                if response is None or response.status_code != 200:
                    if response:
                        print(f"Error fetching assets (page {page}): HTTP {response.status_code}")
                    break
                
                results = response.json()
                assets = self._parse_assets_from_response(results)
                
                if not assets:
                    break
                
                for asset in assets:
                    path = asset.get('originalPath')
                    if path:
                        self._asset_path_map[path] = asset.get('id')
                
                if len(assets) < page_size:
                    break
                page += 1
                
            except Exception as e:
                print(f"Error pre-fetching assets: {e}")
                break
        print(f"Loaded {len(self._asset_path_map)} assets into path map.")

    def _fetch_assets_page(self, page: int, page_size: int):
        """Fetch a single page of assets from Immich, handles falling back to old endpoints."""
        try:
            # Try POST /api/search/metadata
            response = requests.post(
                f"{self.url}/api/search/metadata",
                headers=self.headers,
                json={"page": page, "size": page_size, "withExif": False}
            )
            
            if response.status_code in (404, 405):
                # Try GET /api/assets
                response = requests.get(
                    f"{self.url}/api/assets",
                    headers=self.headers,
                    params={"skip": (page - 1) * page_size, "take": page_size}
                )
                if response.status_code == 404:
                    # Try GET /api/asset
                    response = requests.get(
                        f"{self.url}/api/asset",
                        headers=self.headers,
                        params={"skip": (page - 1) * page_size, "take": page_size}
                    )
            return response
        except Exception:
            return None

    def _parse_assets_from_response(self, results) -> list:
        """Parse asset list from various response formats."""
        if isinstance(results, list):
            return results
        if isinstance(results, dict):
            if 'assets' in results and 'items' in results['assets']:
                return results['assets']['items']
            if 'items' in results:
                return results['items']
            if 'assets' in results and isinstance(results['assets'], list):
                return results['assets']
        return []

    def reverse_path_mapping(self, immich_path: str) -> Optional[str]:
        """Convert Immich server path to local file path."""
        # Immich paths always use forward slashes
        for local_prefix, remote_prefix in self.path_mappings.items():
            remote_prefix_forward = remote_prefix.replace('\\', '/')
            if immich_path.startswith(remote_prefix_forward):
                # Remove server prefix and leading slash
                relative_path = immich_path[len(remote_prefix_forward):].lstrip('/')

                # Choose local separator: use \ if local_prefix looks like Windows
                is_windows = os.name == 'nt' or ':' in local_prefix or local_prefix.startswith('\\\\')
                sep = '\\' if is_windows else '/'
                
                # Replace forward slashes with chosen separator
                relative_path = relative_path.replace('/', sep)

                # Combine using chosen separator
                if local_prefix.endswith(sep):
                    local_path = local_prefix + relative_path
                else:
                    local_path = local_prefix + sep + relative_path

                return os.path.normpath(local_path)
        return None

    def create_tag_if_not_exists(self, tag_name: str) -> Optional[str]:
        """
        Create a tag if it doesn't exist, return its ID.
        """
        try:
            # Check if exists
            tag_id = self._find_tag_by_name(tag_name)
            if tag_id:
                return tag_id

            # Create it
            response = requests.post(
                f"{self.url}/api/tags",
                json={"name": tag_name},
                headers=self.headers
            )
            if response.status_code in (200, 201):
                return response.json()['id']
            elif response.status_code == 409:
                return self.create_tag_if_not_exists(tag_name)
            else:
                print(f"Failed to create tag {tag_name}: {response.status_code} - {response.text}")

        except Exception as e:
            print(f"Error creating tag {tag_name}: {e}")

        return None

    def _find_tag_by_name(self, tag_name: str) -> Optional[str]:
        """List tags and find one by name."""
        page = 1
        while True:
            response = requests.get(
                f"{self.url}/api/tags",
                headers=self.headers,
                params={"page": page, "size": self.PAGE_SIZE}
            )
            
            if response.status_code != 200:
                break
                
            tags_data = response.json()
            tags = tags_data['items'] if isinstance(tags_data, dict) and 'items' in tags_data else tags_data
            
            if not tags:
                break
                
            for tag in tags:
                if tag['name'] == tag_name:
                    return tag['id']
            
            if len(tags) < self.PAGE_SIZE:
                break
            page += 1
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
            
            if response.status_code not in (200, 201):
                print(f"Error adding tag to assets: HTTP {response.status_code}")
                try:
                    print(f"Server response: {response.text}")
                except Exception:
                    pass
                return False
                
            return True
        except Exception as e:
            print(f"Exception adding tag to assets: {e}")
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
