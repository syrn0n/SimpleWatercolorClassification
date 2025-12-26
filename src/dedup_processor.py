"""
Dedup Processor Module

This module contains the DedupProcessor class responsible for processing
and managing duplicate detection and removal in the Immich system.
"""

from typing import List, Dict, Optional
from src.immich_client import ImmichClient
import logging

# Configure logging
logger = logging.getLogger(__name__)

class DedupProcessor:
    """
    Processor for handling duplicate detection and removal operations.
    """

    def __init__(self, immich_client: ImmichClient, internal_path: str, picture_library_path: Optional[str] = None) -> None:
        """
        Initialize the DedupProcessor with ImmichClient and paths.

        Args:
            immich_client: ImmichClient instance
            internal_path: Prefix path for internal Immich storage
            picture_library_path: Prefix path for the picture library (optional)
        """
        self.immich_client = immich_client
        self.internal_path = internal_path
        self.picture_library_path = picture_library_path

    def _get_file_size(self, asset: Dict) -> int:
        """Helper to get file size from asset metadata."""
        try:
            # Exif info might be in 'exifInfo' or 'exif' depending on API version/endpoint
            exif = asset.get('exifInfo') or asset.get('exif') or {}
            return int(exif.get('fileSizeInByte', 0))
        except (ValueError, TypeError):
            return 0

    def execute(self, dry_run: bool = False) -> int:
        """
        Execute duplicate detection and removal operations.

        Args:
            dry_run: Whether to perform a dry run without making changes
        
        Returns:
            int: Number of assets processed for deletion
        """
        duplicates = self.immich_client.get_duplicate_assets()
        if not duplicates:
            print("No duplicates found.")
            return 0

        to_del_ids: List[str] = []
        total_groups = len(duplicates)
        
        print(f"Analyzing {total_groups} duplicate groups...")

        for group_data in duplicates:
            if not isinstance(group_data, dict):
                continue
            
            assets_in_group = group_data.get('assets', [])
            if len(assets_in_group) < 2:
                continue

            external: List[Dict] = []
            picture_library_assets: List[Dict] = []
            internal: List[Dict] = []
            
            for asset in assets_in_group:
                path = asset.get('originalPath', '')
                
                if self.picture_library_path and path.startswith(self.picture_library_path):
                    picture_library_assets.append(asset)
                elif path.startswith(self.internal_path):
                    internal.append(asset)
                else:
                    external.append(asset)

            winner = None
            group_to_del: List[Dict] = []

            # Priority Logic:
            # 1. Picture Library
            if picture_library_assets:
                winner = max(picture_library_assets, key=self._get_file_size)
                # Keep winner, delete others in picture library + all internal + all external
                group_to_del.extend([a for a in picture_library_assets if a['id'] != winner['id']])
                group_to_del.extend(internal)
                group_to_del.extend(external)
            
            # 2. Internal
            elif internal:
                winner = max(internal, key=self._get_file_size)
                # Keep winner, delete others in internal + all external
                group_to_del.extend([a for a in internal if a['id'] != winner['id']])
                group_to_del.extend(external)
                
            # 3. External
            elif external:
                winner = max(external, key=self._get_file_size)
                # Keep winner, delete others in external
                group_to_del.extend([a for a in external if a['id'] != winner['id']])

            if winner:
                to_del_ids.extend([a['id'] for a in group_to_del])

        if not dry_run and to_del_ids:
            print(f"Deleting {len(to_del_ids)} duplicate assets...")
            success = self.immich_client.delete_assets(to_del_ids)
            if success:
                print(f"Successfully deleted {len(to_del_ids)} assets.")
                print("Emptying Immich trash...")
                if self.immich_client.empty_trash():
                    print("Trash emptied successfully.")
                else:
                    print("Failed to empty trash.")
            else:
                print("Failed to delete some or all duplicate assets.")
        else:
            if to_del_ids:
                print(f"[DRY RUN] Would delete {len(to_del_ids)} assets.")
            else:
                print("No duplicate assets identified for deletion.")

        return len(to_del_ids)
