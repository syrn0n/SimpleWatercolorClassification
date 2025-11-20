import argparse
import os
import sys
from datetime import datetime
from src.classifier import WatercolorClassifier
from src.video_processor import VideoProcessor
from src.batch_processor import BatchProcessor

def main():
    parser = argparse.ArgumentParser(description="Classify images or videos as watercolor paintings.")
    parser.add_argument("path", help="Path to the image, video, or folder")
    parser.add_argument("--threshold", type=float, default=0.85, help="Confidence threshold for classification")
    parser.add_argument("--output", help="Path to output CSV file (optional, defaults to timestamped file)")
    parser.add_argument("--min-frames", type=int, default=3, help="Minimum number of frames to sample per video (default: 3)")
    parser.add_argument("--detection-threshold", type=float, default=0.3, help="Percentage of frames (0.0-1.0) required to classify video as watercolor (default: 0.3)")
    parser.add_argument("--strict-mode", action="store_true", help="Enable strict multi-condition classification to minimize false positives")

    args = parser.parse_args()

    if not os.path.exists(args.path):
        print(f"Error: Path not found at {args.path}")
        sys.exit(1)

    classifier = WatercolorClassifier()
    video_processor = VideoProcessor(classifier)

    if os.path.isdir(args.path):
        # Batch processing
        output_csv = args.output
        if not output_csv:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_csv = f"watercolor_results_{timestamp}.csv"
            print(f"No output file specified. Using default: {output_csv}")

        print(f"Processing folder: {args.path}")
        batch_processor = BatchProcessor(classifier, video_processor)
        batch_processor.process_folder(
            args.path, output_csv, min_frames=args.min_frames,
            detection_threshold=args.detection_threshold,
            strict_mode=args.strict_mode,
            image_threshold=args.threshold
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
