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

    def process_folder(self, folder_path: str, output_csv: str, min_frames: int = 3,
                       detection_threshold: float = 0.3, strict_mode: bool = False,
                       image_threshold: float = 0.85,
                       immich_url: str = None, immich_api_key: str = None, immich_tag: str = "Watercolor",
                       immich_path_mappings: Dict[str, str] = None,
                       force_reprocess: bool = False):
        """
        Recursively process a folder and write results to a CSV file.
        """
        immich_client, tag_id = self._initialize_immich(immich_url, immich_api_key, immich_tag, immich_path_mappings)

        files_to_process = self._collect_files(folder_path)
        print(f"Found {len(files_to_process)} files to process in {folder_path}")

        if not files_to_process:
            print("No supported files found.")
            return

        # Check cache statistics
        # db = self.classifier.db or self.video_processor.db
        # if db:
        #     cached_count = 0
        #     needs_processing_count = 0
            
        #     for file_path in files_to_process:
        #         if os.path.exists(file_path):
        #             needs_processing, cached_result = db.check_if_processed(file_path)
        #             if needs_processing:
        #                 needs_processing_count += 1
        #             else:
        #                 cached_count += 1
            
        #     print(f"\n=== Processing Statistics ===")
        #     print(f"Total files found: {len(files_to_process)}")
        #     print(f"Files in cache: {cached_count}")
        #     print(f"Files needing processing: {needs_processing_count}")
        #     print(f"=============================\n")

        results = []

        # Use tqdm for a progress bar
        for file_path in tqdm(files_to_process, desc="Processing files"):
            ext = os.path.splitext(file_path)[1].lower()
            result_data = None

            try:
                if ext in self.video_exts:
                    result_data = self._process_video_file(
                        file_path, force_reprocess, min_frames, detection_threshold,
                        strict_mode, image_threshold
                    )
                elif ext in self.image_exts:
                    result_data = self._process_image_file(
                        file_path, force_reprocess, image_threshold, strict_mode
                    )

                if result_data:
                    results.append(result_data)
                    self._tag_asset_if_needed(immich_client, tag_id, file_path, result_data)

            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                results.append(self._create_error_result(file_path))

        # Write to CSV
        self._write_csv(results, output_csv)
        print(f"\nResults saved to {output_csv}")

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

    def _process_video_file(self, file_path, force, min_frames, detection_threshold, strict_mode, image_threshold):
        """Process a single video file."""
        vid_result = self.video_processor.process_video_with_cache(
            file_path, force=force, min_frames=min_frames, detection_threshold=detection_threshold,
            strict_mode=strict_mode, image_threshold=image_threshold
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

    def _process_image_file(self, file_path, force, threshold, strict_mode):
        """Process a single image file."""
        img_result = self.classifier.classify_with_cache(
            file_path, threshold=threshold,
            strict_mode=strict_mode, force=force
        )

        is_wc = img_result['is_watercolor']
        wc_prob = img_result['confidence']

        return {
            "file_path": file_path,
            "folder": os.path.dirname(file_path),
            "filename": os.path.basename(file_path),
            "type": "image",
            "is_watercolor": is_wc,
            "confidence": wc_prob,
            "duration_seconds": 0,
            "processed_frames": 1,
            "planned_frames": 1,
            "total_frames": 1,
            "watercolor_frames_count": 1 if is_wc else 0,
            "watercolor_frames_percent": 1.0 if is_wc else 0.0,
            "avg_watercolor_confidence": wc_prob if is_wc else 0.0
        }

    def _tag_asset_if_needed(self, immich_client, tag_id, file_path, result_data):
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
                print(f"Failed to create/get tag '{granular_tag_name}'")
            else:
                asset_id = immich_client.get_asset_id_from_path(file_path)
                if asset_id:
                    success = immich_client.add_tag_to_asset(asset_id, granular_tag_id)
                    if success:
                        print(f"Tagged {os.path.basename(file_path)} with {granular_tag_name}.")
                    else:
                        print(f"Failed to tag {os.path.basename(file_path)} with {granular_tag_name}.")

        # Check for "Painting" tag
        top_label = result_data.get('top_label')
        painting_labels = ["a watercolor painting", "an oil painting", "an acrylic painting"]
        
        if top_label in painting_labels:
            painting_tag_id = immich_client.create_tag_if_not_exists("Painting")
            if painting_tag_id:
                asset_id = immich_client.get_asset_id_from_path(file_path)
                if asset_id:
                    success = immich_client.add_tag_to_asset(asset_id, painting_tag_id)
                    if success:
                        print(f"Tagged {os.path.basename(file_path)} with 'Painting'.")
                    else:
                        print(f"Failed to tag {os.path.basename(file_path)} with 'Painting'.")

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
            print("Error: No database available")
            return
            
        print("Processing cached results from database...")
        
        tagged_count = 0
        skipped_count = 0
        error_count = 0
        
        for result in db.get_all_results():
            file_path = result.get('file_path')
            confidence = result.get('confidence', 0.0)
            
            granular_tag_name = self.get_granular_tag(confidence)
            
            if not granular_tag_name and not result.get('top_label'):
                skipped_count += 1
                continue
                
            try:
                asset_id = immich_client.get_asset_id_from_path(file_path)
                if not asset_id:
                    skipped_count += 1
                    continue

                # Apply granular tag
                if granular_tag_name:
                    granular_tag_id = immich_client.create_tag_if_not_exists(granular_tag_name)
                    if granular_tag_id:
                        success = immich_client.add_tag_to_asset(asset_id, granular_tag_id)
                        if success:
                            print(f"Tagged {os.path.basename(file_path)} with {granular_tag_name}")
                            tagged_count += 1
                        else:
                            print(f"Failed to tag {os.path.basename(file_path)}")
                            error_count += 1
                    else:
                        print(f"Failed to create/get tag '{granular_tag_name}'")
                        error_count += 1

                # Apply "Painting" tag
                top_label = result.get('top_label')
                painting_labels = ["a watercolor painting", "an oil painting", "an acrylic painting"]
                
                if top_label in painting_labels:
                    painting_tag_id = immich_client.create_tag_if_not_exists("Painting")
                    if painting_tag_id:
                        success = immich_client.add_tag_to_asset(asset_id, painting_tag_id)
                        if success:
                            print(f"Tagged {os.path.basename(file_path)} with 'Painting'")
                            tagged_count += 1
                        else:
                            print(f"Failed to tag {os.path.basename(file_path)} with 'Painting'")
                            error_count += 1
                    
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                error_count += 1
                
        print(f"\n=== Summary ===")
        print(f"Tagged: {tagged_count}")
        print(f"Skipped: {skipped_count}")
        print(f"Errors: {error_count}")

    def _create_error_result(self, file_path):
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
            "top_label": None
        }

    def _write_csv(self, results: List[Dict], output_csv: str):
        fieldnames = [
            "file_path", "folder", "filename", "type", "is_watercolor", "confidence",
            "duration_seconds", "processed_frames", "planned_frames", "total_frames",
            "watercolor_frames_count", "watercolor_frames_percent",
            "avg_watercolor_confidence", "top_label"
        ]

        with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                writer.writerow(row)
