import os
import shutil
import csv
import json
import hashlib
from datetime import datetime
from typing import Dict, Optional, List
from tqdm import tqdm
from src.immich_client import ImmichClient


class AssetMover:
    def __init__(self, immich_client: ImmichClient, destination_root: str,
                 path_mappings: Dict[str, str], dry_run: bool = False):
        self.immich_client = immich_client
        self.destination_root = destination_root
        self.path_mappings = path_mappings
        self.dry_run = dry_run
        self.transaction_log: List[Dict] = []

    def calculate_file_hash(self, file_path: str, algorithm: str = 'sha256') -> Optional[str]:
        """
        Calculate hash of a file.

        Args:
            file_path: Path to the file
            algorithm: Hash algorithm to use (default: sha256)

        Returns:
            Hex digest of the file hash, or None if error
        """
        try:
            hash_obj = hashlib.new(algorithm)
            with open(file_path, 'rb') as f:
                # Read file in chunks to handle large files
                for chunk in iter(lambda: f.read(8192), b''):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except Exception:
            return None

    def calculate_destination_path(self, immich_path: str) -> Optional[str]:
        """
        Calculate destination path for an asset.

        Args:
            immich_path: Server path from Immich (e.g., /data/library/admin/2025/01/photo.jpg)

        Returns:
            Local destination path (e.g., E:\\watercolor_archive\\2025\\01\\photo.jpg)
        """
        # Find matching server prefix in path mappings
        for local_prefix, server_prefix in self.path_mappings.items():
            if immich_path.startswith(server_prefix):
                # Extract relative path from server root
                relative_path = immich_path[len(server_prefix):]
                # Remove leading slash if present
                if relative_path.startswith('/'):
                    relative_path = relative_path[1:]
                # Combine with destination root and normalize
                dest_path = os.path.join(self.destination_root, relative_path)
                return os.path.normpath(dest_path)

        return None

    def move_file(self, source_path: str, dest_path: str) -> bool:
        """
        Move file from source to destination.

        Args:
            source_path: Local source file path
            dest_path: Local destination file path

        Returns:
            True if move succeeded, False otherwise
        """
        try:
            # Check if source file exists
            if not os.path.exists(source_path):
                return False

            if self.dry_run:
                # In dry-run mode, just simulate success
                return True

            # Create destination directory if needed
            dest_dir = os.path.dirname(dest_path)
            os.makedirs(dest_dir, exist_ok=True)

            # Check if destination already exists
            if os.path.exists(dest_path):
                # Compare file hashes to see if it's the same file
                source_hash = self.calculate_file_hash(source_path)
                dest_hash = self.calculate_file_hash(dest_path)

                if source_hash and dest_hash and source_hash == dest_hash:
                    # Files are identical, just remove source
                    os.remove(source_path)
                    return True
                else:
                    # Different files at destination
                    return False

            # Move the file
            shutil.move(source_path, dest_path)
            return True

        except Exception:
            return False

    def save_transaction_log(self, filename: str):
        """
        Save transaction log to JSON file.
        """
        with open(filename, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'dry_run': self.dry_run,
                'transactions': self.transaction_log
            }, f, indent=2)

    def save_csv_report(self, filename: str):
        """
        Save CSV report of processed assets.
        """
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'asset_id', 'immich_path', 'source_path', 'dest_path',
                'move_success', 'delete_success', 'error'
            ])
            writer.writeheader()
            writer.writerows(self.transaction_log)

    def process_tagged_assets(self, tag_name: str) -> Dict[str, int]:
        """
        Process all assets with the specified tag: move files and delete from Immich.

        Args:
            tag_name: Name of the tag to process

        Returns:
            Statistics dictionary with counts
        """
        results = {
            "total": 0,
            "moved": 0,
            "failed": 0,
            "deleted": 0
        }

        # Get tag ID
        tag_id = self.immich_client.create_tag_if_not_exists(tag_name)
        if not tag_id:
            print(f"Error: Could not find or create tag '{tag_name}'")
            return results

        print(f"Found tag '{tag_name}' with ID: {tag_id}")

        # Get all assets with this tag
        assets = self.immich_client.get_assets_by_tag(tag_id)
        results["total"] = len(assets)

        if not assets:
            print(f"No assets found with tag '{tag_name}'")
            return results

        print(f"Found {len(assets)} assets with tag '{tag_name}'")
        if self.dry_run:
            print("\n*** DRY RUN MODE - No files will be moved or deleted ***\n")
        print()

        # Process each asset with progress bar
        for asset in tqdm(assets, desc="Processing assets", unit="asset"):
            self._process_single_asset(asset, results)

        return results

    def _process_single_asset(self, asset: Dict, results: Dict[str, int]):
        """
        Process a single asset: calculate paths, move, and delete.
        Updates results dict and transaction log in place.
        """
        asset_id = asset.get('id')
        immich_path = asset.get('originalPath')

        transaction = {
            'asset_id': asset_id,
            'immich_path': immich_path,
            'source_path': None,
            'dest_path': None,
            'move_success': False,
            'delete_success': False,
            'error': None
        }

        if not immich_path:
            transaction['error'] = 'No originalPath'
            results["failed"] += 1
            self.transaction_log.append(transaction)
            return

        # Reverse map to local source path
        source_path = self.immich_client.reverse_path_mapping(immich_path)
        transaction['source_path'] = source_path

        if not source_path:
            transaction['error'] = 'No path mapping found'
            results["failed"] += 1
            self.transaction_log.append(transaction)
            return

        # Calculate destination path
        dest_path = self.calculate_destination_path(immich_path)
        transaction['dest_path'] = dest_path

        if not dest_path:
            transaction['error'] = 'Could not calculate destination'
            results["failed"] += 1
            self.transaction_log.append(transaction)
            return

        # Attempt to move file
        move_success = self.move_file(source_path, dest_path)
        transaction['move_success'] = move_success

        if move_success:
            results["moved"] += 1

            # Only delete from Immich if move succeeded and not dry-run
            if not self.dry_run:
                delete_success = self.immich_client.delete_asset(asset_id)
                transaction['delete_success'] = delete_success

                if delete_success:
                    results["deleted"] += 1
            else:
                transaction['delete_success'] = True  # Would delete in real run
                results["deleted"] += 1
        else:
            transaction['error'] = 'Move failed'
            results["failed"] += 1

        self.transaction_log.append(transaction)
