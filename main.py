import argparse
import os
from dotenv import load_dotenv, dotenv_values
import sys
from datetime import datetime
from src.classifier import WatercolorClassifier
from src.video_processor import VideoProcessor
from src.batch_processor import BatchProcessor
from src.asset_mover import AssetMover
from src.immich_client import ImmichClient


def main():
    load_dotenv()
    vals = dotenv_values()

    # Generate timestamp for default report names
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_csv = f"move_report_{timestamp}.csv"
    default_log = f"move_log_{timestamp}.json"

    parser = argparse.ArgumentParser(description="Classify images or videos as watercolor paintings.")
    parser.add_argument("path", help="Path to the image, video, or folder")
    parser.add_argument("--threshold", type=float, default=float(os.getenv("WATERCOLOR_THRESHOLD", 0.85)),
                        help="Confidence threshold for classification")
    parser.add_argument("--output", default=os.getenv("WATERCOLOR_OUTPUT"),
                        help="Path to output CSV file (optional, defaults to timestamped file)")
    parser.add_argument("--min-frames", type=int, default=int(os.getenv("WATERCOLOR_MIN_FRAMES", 3)),
                        help="Minimum number of frames to sample per video (default: 3)")
    parser.add_argument("--detection-threshold", type=float,
                        default=float(os.getenv("WATERCOLOR_DETECTION_THRESHOLD", 0.3)),
                        help="Percentage of frames (0.0-1.0) required to classify video as watercolor (default: 0.3)")
    parser.add_argument("--strict-mode", action="store_true",
                        default=os.getenv("WATERCOLOR_STRICT_MODE", "false").lower() == "true",
                        help="Enable strict multi-condition classification to minimize false positives")
    parser.add_argument("--immich-url", default=os.getenv("IMMICH_URL"),
                        help="Immich Server URL (e.g., http://192.168.1.100:2283)")
    parser.add_argument("--immich-key", default=os.getenv("IMMICH_API_KEY"), help="Immich API Key")
    parser.add_argument("--immich-tag", default=os.getenv("IMMICH_TAG", "Watercolor"),
                        help="Tag name to apply in Immich (default: Watercolor)")
    parser.add_argument("--immich-path-mapping", default=vals.get("IMMICH_PATH_MAPPING"),
                        help="Path mappings in format 'local:remote;local2:remote2' "
                             "(e.g., '/mnt/photos:/usr/src/app/photos')")
    parser.add_argument("--move-tagged-assets", action="store_true",
                        default=vals.get("MOVE_TAGGED_ASSETS", "false").lower() == "true",
                        help="Move assets with IMMICH_TAG to destination folder and delete from Immich")
    parser.add_argument("--move-destination", default=vals.get("MOVE_DESTINATION_ROOT"),
                        help="Destination root folder for moved assets")
    parser.add_argument("--dry-run", action="store_true",
                        default=vals.get("MOVE_DRY_RUN", "false").lower() == "true",
                        help="Simulate move operation without actually moving files or deleting from Immich")
    parser.add_argument("--csv-report", default=default_csv, help="Path to save CSV report of move operations")
    parser.add_argument("--transaction-log", default=default_log, help="Path to save transaction log JSON file")

    args = parser.parse_args()

    # Handle move-tagged-assets mode
    if args.move_tagged_assets:
        # Validate required parameters
        if not args.move_destination:
            print("Error: --move-destination is required for move operation")
            sys.exit(1)

        if not args.immich_url or not args.immich_key:
            print("Error: Immich URL and API key are required for move operation")
            sys.exit(1)

        if not args.immich_path_mapping:
            print("Error: Path mapping is required for move operation")
            sys.exit(1)

        # Confirmation prompt (skip in dry-run mode or if configured)
        skip_confirmation = vals.get("MOVE_SKIP_CONFIRMATION", "false").lower() == "true"

        if not args.dry_run and not skip_confirmation:
            print(f"WARNING: This will move assets tagged '{args.immich_tag}' and DELETE them from Immich.")
            print(f"Destination: {args.move_destination}")
            confirm = input("Type 'yes' to continue: ")

            if confirm.lower() != 'yes':
                print("Operation cancelled.")
                sys.exit(0)
        else:
            if args.dry_run:
                print(f"DRY RUN MODE: Simulating move of assets tagged '{args.immich_tag}'")
            else:
                print(f"Moving assets tagged '{args.immich_tag}' (confirmation skipped)")
            print(f"Destination: {args.move_destination}")

        # Parse path mappings
        path_mappings = {}
        for mapping in args.immich_path_mapping.split(';'):
            if ':' in mapping:
                local, remote = mapping.rsplit(':', 1)
                path_mappings[local.strip()] = remote.strip()

        # Initialize clients
        immich_client = ImmichClient(
            args.immich_url,
            args.immich_key,
            path_mappings
        )

        asset_mover = AssetMover(
            immich_client,
            args.move_destination,
            path_mappings,
            dry_run=args.dry_run
        )

        # Process assets
        print("\nProcessing tagged assets...")
        results = asset_mover.process_tagged_assets(args.immich_tag)

        print("\n=== Results ===")
        print(f"Assets found: {results['total']}")
        print(f"Successfully moved: {results['moved']}")
        print(f"Failed to move: {results['failed']}")
        print(f"Deleted from Immich: {results['deleted']}")

        # Save reports if requested
        if args.csv_report:
            asset_mover.save_csv_report(args.csv_report)
            print(f"\nCSV report saved to: {args.csv_report}")

        if args.transaction_log:
            asset_mover.save_transaction_log(args.transaction_log)
            print(f"Transaction log saved to: {args.transaction_log}")

        # Exit after move operation - do not proceed to classification
        sys.exit(0)

    # Continue with normal classification flow
    if not os.path.exists(args.path):
        print(f"Error: Path not found at {args.path}")
        sys.exit(1)

    classifier = WatercolorClassifier()
    video_processor = VideoProcessor(classifier)

    if os.path.isdir(args.path):
        # Batch processing
        output_csv = args.output
        if not output_csv:
            output_csv = f"watercolor_results_{timestamp}.csv"
            print(f"No output file specified. Using default: {output_csv}")

        # Parse path mappings
        path_mappings = {}
        if args.immich_path_mapping:
            try:
                for mapping in args.immich_path_mapping.split(';'):
                    if ':' in mapping:
                        local, remote = mapping.rsplit(':', 1)
                        path_mappings[local.strip()] = remote.strip()
            except Exception as e:
                print(f"Error parsing path mappings: {e}")
                sys.exit(1)

        print(f"Processing folder: {args.path}")
        batch_processor = BatchProcessor(classifier, video_processor)
        batch_processor.process_folder(
            args.path, output_csv, min_frames=args.min_frames,
            detection_threshold=args.detection_threshold,
            strict_mode=args.strict_mode,
            image_threshold=args.threshold,
            immich_url=args.immich_url,
            immich_api_key=args.immich_key,
            immich_tag=args.immich_tag,
            immich_path_mappings=path_mappings
        )

    else:
        # Single file processing
        ext = os.path.splitext(args.path)[1].lower()
        video_exts = ['.mp4', '.avi', '.mov', '.mkv']
        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tiff']

        if ext in video_exts:
            print(f"Detected video file: {args.path}")
            result = video_processor.process_video(
                args.path, min_frames=args.min_frames,
                detection_threshold=args.detection_threshold,
                strict_mode=args.strict_mode,
                image_threshold=args.threshold
            )

            print("\n--- Video Results ---")
            print(f"Is Watercolor: {result['is_watercolor']}")
            print(f"Average Confidence: {result['confidence']:.2%}")
            print(f"Percentage of Watercolor Frames: {result['percent_watercolor_frames']:.2%}")

        elif ext in image_exts:
            print(f"Detected image file: {args.path}")
            probs = classifier.predict(args.path)

            if args.strict_mode:
                is_wc = classifier.is_watercolor_strict(args.path, threshold=args.threshold)
            else:
                is_wc = classifier.is_watercolor(args.path, threshold=args.threshold)

            print("\n--- Image Results ---")
            print(f"Is Watercolor: {is_wc}")
            print(f"Confidence: {probs['a watercolor painting']:.2%}")
            print("\nFull Probabilities:")
            for label, prob in sorted(probs.items(), key=lambda x: x[1], reverse=True):
                print(f"  {label}: {prob:.2%}")

        else:
            print(f"Unsupported file extension: {ext}")
            print("Please provide an image, video, or folder.")


if __name__ == "__main__":
    main()
