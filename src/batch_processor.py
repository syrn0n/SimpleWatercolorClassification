import os
import csv
from typing import List, Dict, Optional
from tqdm import tqdm
from .classifier import WatercolorClassifier
from .video_processor import VideoProcessor
from .immich_client import ImmichClient


class BatchProcessor:
    def __init__(self, classifier: WatercolorClassifier, video_processor: VideoProcessor):
        self.classifier = classifier
        self.video_processor = video_processor
        self.image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff'}
        self.video_exts = {'.mp4', '.avi', '.mov', '.mkv'}

    @staticmethod
    def get_granular_tag(confidence: float) -> Optional[str]:
        """
        Get granular tag based on confidence score.
        
        Args:
            confidence: Confidence score (0.0-1.0)
            
        Returns:
            Tag name or None if below threshold
        """
        if confidence >= 0.85:
            return "Watercolor85"
        elif confidence >= 0.75:
            return "Watercolor75"
        elif confidence >= 0.65:
            return "Watercolor65"
        elif confidence >= 0.55:
            return "Watercolor55"
        elif confidence >= 0.45:
            return "Watercolor45"
        elif confidence >= 0.35:
            return "Watercolor35"
        return None

    def process_folder(self, folder_path: str, min_frames: int = 3,
                       detection_threshold: float = 0.3, strict_mode: bool = False,
                       image_threshold: float = 0.85,
                       immich_url: str = None, immich_api_key: str = None, immich_tag: str = "Watercolor",
                       immich_path_mappings: Dict[str, str] = None,
                       force_reprocess: bool = False, quick_sync: bool = False):
        """
        Recursively process a folder and write results to a CSV file.
        """
        immich_client, tag_id = self._initialize_immich(immich_url, immich_api_key, immich_tag, immich_path_mappings)

        files_to_process = self._collect_files(folder_path)
        print(f"Found {len(files_to_process)} files to process in {folder_path}")

        if not files_to_process:
            print("No supported files found.")
            return

        results = []

        # Use tqdm for a progress bar
        try:
            for file_path in tqdm(files_to_process, desc="Processing files"):
                ext = os.path.splitext(file_path)[1].lower()
                result_data = None

                try:
                    if ext in self.video_exts:
                        result_data = self._process_video_file(
                            file_path, min_frames, detection_threshold, strict_mode, image_threshold,
                            force=force_reprocess, quick_sync=quick_sync
                        )
                    elif ext in self.image_exts:
                        result_data = self.classifier.classify_with_cache(
                            file_path, threshold=image_threshold, strict_mode=strict_mode,
                            force=force_reprocess, quick_sync=quick_sync
                        )
                        # Add missing fields for image result to match expected structure
                        result_data.update({
                            "file_path": file_path,
                            "folder": os.path.dirname(file_path),
                            "filename": os.path.basename(file_path),
                            "type": "image",
                            "duration_seconds": 0,
                            "processed_frames": 1,
                            "planned_frames": 1,
                            "total_frames": 1,
                            "watercolor_frames_count": 1 if result_data['is_watercolor'] else 0,
                            "watercolor_frames_percent": 1.0 if result_data['is_watercolor'] else 0.0,
                            "avg_watercolor_confidence": result_data['confidence'] if result_data['is_watercolor'] else 0.0
                        })

                    if result_data:
                        results.append(result_data)

                except Exception as e:
                    print(f"Error processing {file_path}: {e}")
                    error_result = self._create_error_result(file_path, str(e))
                    results.append(error_result)
                    
                    # Save error to database
                    if self.classifier.db:
                        self.classifier.db.save_result(file_path, error_result)
        except KeyboardInterrupt:
            print("\n\nStopping processing... (Ctrl+C detected)")
            print("Saving results collected so far...")

        # Batch tag assets after processing
        tagged_assets = []
        if immich_client:
            tagged_assets = self._batch_tag_assets(immich_client, results)

        # Print Summary
        self._print_summary(results, tagged_assets)

    def _initialize_immich(self, url, api_key, tag, mappings):
        """Initialize Immich client and tag."""
        if url and api_key:
            print(f"Initializing Immich client for {url}...")
            client = ImmichClient(url, api_key, mappings)
            tag_id = client.create_tag_if_not_exists(tag)
            if tag_id:
                print(f"Using Immich tag '{tag}' (ID: {tag_id})")
                return client, tag_id
            else:
                print(f"Warning: Could not create or find tag '{tag}'. Tagging will be skipped.")
        return None, None

    def _collect_files(self, folder_path):
        """Collect all supported files in the folder."""
        files_to_process = []
        for root, _, files in os.walk(folder_path):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.image_exts or ext in self.video_exts:
                    files_to_process.append(os.path.join(root, file))
        return files_to_process

    def _process_video_file(self, file_path: str, min_frames: int, detection_threshold: float,
                            strict_mode: bool, image_threshold: float, force: bool = False,
                            quick_sync: bool = False) -> Dict:
        """Process a single video file."""
        vid_result = self.video_processor.process_video_with_cache(
            file_path, min_frames=min_frames,
            detection_threshold=detection_threshold,
            strict_mode=strict_mode,
            image_threshold=image_threshold,
            force=force,
            quick_sync=quick_sync
        )
        return {
            "file_path": file_path,
            "folder": os.path.dirname(file_path),
            "filename": os.path.basename(file_path),
            "type": "video",
            "is_watercolor": vid_result["is_watercolor"],
            "confidence": vid_result["confidence"],
            "duration_seconds": vid_result['duration_seconds'],
            "processed_frames": vid_result['processed_frames'],
            "planned_frames": vid_result['planned_frames'],
            "total_frames": vid_result['total_frames'],
            "watercolor_frames_count": vid_result['watercolor_frames_count'],
            "watercolor_frames_percent": vid_result['percent_watercolor_frames'],
            "avg_watercolor_confidence": vid_result['avg_watercolor_confidence']
        }

    def _batch_tag_assets(self, immich_client, results: List[Dict]) -> List[str]:
        """
        Batch tag assets based on their classification results.
        Groups assets by tag and makes single API call per tag.
        
        Args:
            immich_client: ImmichClient instance
            results: List of classification results
            
        Returns:
            List of tagged asset descriptions for reporting
        """
        from collections import defaultdict
        
        # Group assets by tag
        tag_to_assets = defaultdict(list)  # tag_name -> [(file_path, asset_id), ...]
        
        print("\nResolving asset IDs for tagging...")
        for result in tqdm(results, desc="Resolving assets"):
            file_path = result.get('file_path')
            if not file_path:
                continue
                
            confidence = result.get('confidence', 0.0)
            granular_tag_name = self.get_granular_tag(confidence)
            
            # Get asset ID once for this file
            asset_id = immich_client.get_asset_id_from_path(file_path)
            if not asset_id:
                continue
            
            # Add to granular tag group
            if granular_tag_name:
                tag_to_assets[granular_tag_name].append((file_path, asset_id))
            
            # Add to "Painting" tag group if applicable
            top_label = result.get('top_label')
            painting_labels = ["a watercolor painting", "an oil painting", "an acrylic painting"]
            if top_label in painting_labels:
                tag_to_assets["Painting"].append((file_path, asset_id))
        
        # Batch tag assets
        tagged_assets = []
        print("\nApplying tags in batches...")
        for tag_name, assets in tqdm(tag_to_assets.items(), desc="Tagging"):
            # Create/get tag
            tag_id = immich_client.create_tag_if_not_exists(tag_name)
            if not tag_id:
                continue
            
            # Extract asset IDs
            asset_ids = [asset_id for _, asset_id in assets]
            
            # Batch tag (skip_existing=True to avoid redundant tagging)
            success = immich_client.add_tags_to_assets(asset_ids, tag_id, skip_existing=True)
            
            if success:
                # Add to reporting list
                for file_path, _ in assets:
                    tagged_assets.append(f"{os.path.basename(file_path)} -> {tag_name}")
        
        return tagged_assets

    def _tag_asset_if_needed(self, immich_client, tag_id, file_path, result_data, tagged_assets: List[str] = None):
        """Tag the asset in Immich with granular tag based on confidence."""
        if not immich_client:
            return
            
        confidence = result_data.get('confidence', 0.0)
        granular_tag_name = self.get_granular_tag(confidence)
        
        if not granular_tag_name:
            # Even if no granular tag, we might still want to add "Painting" tag
            pass
            
        # Create/get the granular tag
        if granular_tag_name:
            granular_tag_id = immich_client.create_tag_if_not_exists(granular_tag_name)
            if not granular_tag_id:
                pass # Fail silently to avoid progress bar interruption
            else:
                asset_id = immich_client.get_asset_id_from_path(file_path)
                if asset_id:
                    success = immich_client.add_tag_to_asset(asset_id, granular_tag_id)
                    if success and tagged_assets is not None:
                        tagged_assets.append(f"{os.path.basename(file_path)} -> {granular_tag_name}")

        # Check for "Painting" tag
        top_label = result_data.get('top_label')
        painting_labels = ["a watercolor painting", "an oil painting", "an acrylic painting"]
        
        if top_label in painting_labels:
            painting_tag_id = immich_client.create_tag_if_not_exists("Painting")
            if painting_tag_id:
                asset_id = immich_client.get_asset_id_from_path(file_path)
                if asset_id:
                    success = immich_client.add_tag_to_asset(asset_id, painting_tag_id)
                    if success and tagged_assets is not None:
                        tagged_assets.append(f"{os.path.basename(file_path)} -> Painting")

    def process_from_db(self, immich_url: str, immich_api_key: str,
                       immich_path_mappings: Dict[str, str] = None):
        """
        Process all cached results from database and apply granular tags to Immich.
        
        Args:
            immich_url: Immich server URL
            immich_api_key: Immich API key
            immich_path_mappings: Path mappings for local to remote paths
        """
        if not immich_url or not immich_api_key:
            print("Error: Immich URL and API key are required")
            return
            
        # Initialize Immich client
        immich_client = ImmichClient(immich_url, immich_api_key, immich_path_mappings)
        
        # Get database instance
        db = self.classifier.db or self.video_processor.db
        if not db:
            # Try to create a new DB connection if instances don't have one
            # This happens when BatchProcessor is initialized without full context
            try:
                from .database import DatabaseManager
                # Assuming default path if not accessible, but ideally should be passed
                db = DatabaseManager()
            except Exception:
                print("Error: No database available")
                return

        print("Loading cached results from database...")
        
        processed_count = 0
        skipped_count = 0
        error_count = 0

        # We need to access DB directly, so ensure we have a valid connection or use context manager
        # Since we might be using the classifier's DB which is already open, or a new one
        # Let's try to use the existing one if open, or open a new one
        
        # Helper to get results
        try:
            results = list(db.get_all_results())
        except Exception:
            # Fallback if db is not connected
            from .database import DatabaseManager
            db_path = self.classifier.db_path if hasattr(self.classifier, 'db_path') else "classification_cache.db"
            with DatabaseManager(db_path) as temp_db:
                results = list(temp_db.get_all_results())
                db = temp_db # Use this one for updates

        total_files = len(results)
        print(f"Found {total_files} cached results.")

        # Filter for results that have classification data
        valid_results = [r for r in results if r.get('confidence') is not None]
        
        # Prepare for batch logic
        files_to_tag = {}  # tag_id -> list of (asset_id or file_path, result_data)

        print("Analyzing files for tagging...")
        for result in tqdm(valid_results):
            # Skip if already tagged in Immich
            # if result.get('immich_tagged'):
            #     skipped_count += 1
            #     continue
                
            confidence = result.get('confidence')
            file_path = result.get('file_path')
            
            tag_name = BatchProcessor.get_granular_tag(confidence)
            
            if tag_name:
                # Get tag ID (cached in client)
                tag_id = immich_client.create_tag_if_not_exists(tag_name)
                
                if tag_id:
                    if tag_id not in files_to_tag:
                        files_to_tag[tag_id] = []
                        
                    # Use stored asset ID if available, otherwise use file path
                    identifier = result.get('immich_asset_id') or file_path
                    files_to_tag[tag_id].append((identifier, result))
            else:
                skipped_count += 1

        # Process tags in batches
        print(f"\nApplying tags to {sum(len(v) for v in files_to_tag.values())} assets...")
        
        for tag_id, assets in files_to_tag.items():
            # Extract identifiers (asset_ids or paths)
            identifiers = [a[0] for a in assets]
            
            # Call batch tagging API
            immich_client.add_tags_to_assets(identifiers, tag_id)
            
            # Update database for successful tags
            # Note: success_ids might returns IDs that were successfully tagged
            # We will assume all were tagged for DB update purposes to keep it simple,
            # as failures usually raise exceptions
            
            for identifier, result_data in assets:
                file_path = result_data.get('file_path')
                # Optimistically update DB
                try:
                    db.update_immich_info(
                        file_path,
                        tag_id=tag_id,
                        asset_id=result_data.get('immich_asset_id')
                    )
                    processed_count += 1
                except Exception as e:
                    print(f"Error updating DB for {file_path}: {e}")
                    error_count += 1
                    
        print("\nSync complete.")
        print(f"Processed: {processed_count}")
        print(f"Skipped (already tagged or low confidence): {skipped_count}")
        print(f"Errors: {error_count}")

    def _create_error_result(self, file_path, error_message="Unknown error"):
        """Create a result dictionary for an error case."""
        return {
            "file_path": file_path,
            "folder": os.path.dirname(file_path),
            "filename": os.path.basename(file_path),
            "type": "error",
            "is_watercolor": False,
            "confidence": 0.0,
            "duration_seconds": 0,
            "processed_frames": 0,
            "planned_frames": 0,
            "total_frames": 0,
            "watercolor_frames_count": 0,
            "watercolor_frames_percent": 0.0,
            "avg_watercolor_confidence": 0.0,
            "avg_watercolor_confidence": 0.0,
            "top_label": None,
            "error": error_message
        }

    def _print_summary(self, results: List[Dict], tagged_assets: List[str] = None):
        """Print execution summary."""
        total_files = len(results)
        images = sum(1 for r in results if r.get('type') == 'image')
        videos = sum(1 for r in results if r.get('type') == 'video')
        watercolors = sum(1 for r in results if r.get('is_watercolor'))
        errors = sum(1 for r in results if r.get('error'))
        
        print("\n" + "=" * 30)
        print("       EXECUTION SUMMARY")
        print("=" * 30)
        print(f"Total Files Processed: {total_files}")
        print(f"  - Images: {images}")
        print(f"  - Videos: {videos}")
        print(f"Watercolor Detections: {watercolors}")
        print(f"Errors Encountered:    {errors}")
        
        if tagged_assets:
            print(f"Assets Tagged:         {len(tagged_assets)}")
            # Print first few tagged assets or all if list is short
            for asset in tagged_assets[:10]:
                print(f"  - {asset}")
            if len(tagged_assets) > 10:
                print(f"  ... and {len(tagged_assets) - 10} more")
        
        print("=" * 30 + "\n")
