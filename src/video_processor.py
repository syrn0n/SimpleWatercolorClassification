import cv2
from PIL import Image
from typing import Dict
from tqdm import tqdm
from .classifier import WatercolorClassifier


class VideoProcessor:
    def __init__(self, classifier: WatercolorClassifier):
        self.classifier = classifier

    def process_video(self, video_path: str, sample_interval_sec: float = 1.0, min_frames: int = 3,
                     detection_threshold: float = 0.3, strict_mode: bool = False,
                     image_threshold: float = 0.85) -> Dict[str, any]:
        """
        Process a video file, sampling frames and classifying them.

        Args:
            video_path: Path to the video file.
            sample_interval_sec: How many seconds between sampled frames.
            min_frames: Minimum number of frames to process (default: 3).
            detection_threshold: Percentage of frames (0.0-1.0) that must be watercolor to classify the video as such.
            strict_mode: If True, use strict multi-condition classification to minimize false positives.
            image_threshold: Confidence threshold for individual frame classification.

        Returns:
            Dictionary containing:
            - is_watercolor: bool
            - confidence: float (average probability of watercolor)
            - frame_results: List of results for each sampled frame
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        # Calculate interval based on time
        frame_interval = int(fps * sample_interval_sec)

        # Ensure we meet the minimum frame count
        # If total frames is small, we might take every frame
        if total_frames > 0:
            max_interval_for_min_frames = total_frames // min_frames
            if max_interval_for_min_frames == 0:
                max_interval_for_min_frames = 1

            # If the time-based interval is too large (skipping too many), reduce it
            if frame_interval > max_interval_for_min_frames or frame_interval == 0:
                frame_interval = max_interval_for_min_frames

        if frame_interval < 1:
            frame_interval = 1

        # Calculate planned frames
        planned_frames_count = 0
        if total_frames > 0:
            planned_frames_count = (total_frames // frame_interval) + 1  # Approximate

        # Optimization: Early stopping
        # If we have many frames to process, check after 10% if we already have a positive result
        early_stop_threshold_frames = 0
        if planned_frames_count > 100:
            early_stop_threshold_frames = int(planned_frames_count * 0.1)
            print(f"Optimization enabled: Will check for early stopping after {early_stop_threshold_frames} frames")

        results = []
        watercolor_probs = []

        print(f"Processing video: {video_path}")
        print(f"Duration: {duration:.2f}s, FPS: {fps}, Total Frames: {total_frames}")
        print(f"Sampling every {frame_interval} frames (approx every {frame_interval/fps:.2f}s)")
        print(f"Planned frames to process: ~{planned_frames_count}")

        # We can use tqdm for progress
        pbar = tqdm(total=planned_frames_count)

        current_frame = 0
        processed_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % frame_interval == 0:
                # OpenCV is BGR, PIL needs RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)

                probs = self.classifier.predict(pil_image)

                wc_prob = probs.get("a watercolor painting", 0.0)

                # Use strict mode if enabled
                if strict_mode:
                    is_wc = self.classifier.is_watercolor_strict(pil_image, threshold=image_threshold)
                else:
                    is_wc = wc_prob > 0.5 and max(probs, key=probs.get) == "a watercolor painting"

                results.append({
                    "frame_index": current_frame,
                    "timestamp": current_frame / fps if fps > 0 else 0,
                    "probs": probs,
                    "is_watercolor": is_wc
                })
                watercolor_probs.append(wc_prob)
                processed_count += 1
                pbar.update(1)

                # Early stopping check
                if early_stop_threshold_frames > 0 and processed_count == early_stop_threshold_frames:
                    # Check if we have a "good probability of an answer"
                    # We interpret this as: Is the video ALREADY classified as watercolor based on the threshold?
                    current_wc_count = sum(1 for r in results if r["is_watercolor"])
                    current_percent = current_wc_count / processed_count

                    if current_percent >= detection_threshold:
                        print(f"\nEarly stopping triggered: {current_percent:.2%} watercolor frames detected after {processed_count} frames.")
                        break

            current_frame += 1

        cap.release()
        pbar.close()

        if not results:
            return {
                "is_watercolor": False,
                "confidence": 0.0,
                "details": "No frames processed",
                "processed_frames": 0,
                "planned_frames": planned_frames_count,
                "total_video_frames": total_frames,
                "duration_seconds": duration,
                "watercolor_frames_count": 0,
                "percent_watercolor_frames": 0.0,
                "avg_watercolor_confidence": 0.0
            }

        # Aggregate results
        avg_confidence = sum(watercolor_probs) / len(watercolor_probs)
        watercolor_frames_count = sum(1 for r in results if r["is_watercolor"])
        percent_watercolor_frames = watercolor_frames_count / len(results)

        # Calculate average confidence specifically for frames classified as watercolor
        watercolor_confidences = [r["probs"].get("a watercolor painting", 0.0) for r in results if r["is_watercolor"]]
        avg_watercolor_confidence = sum(watercolor_confidences) / len(watercolor_confidences) if watercolor_confidences else 0.0

        # Use the custom detection threshold
        is_video_watercolor = percent_watercolor_frames >= detection_threshold

        return {
            "is_watercolor": is_video_watercolor,
            "confidence": avg_confidence, # Average confidence across ALL processed frames
            "percent_watercolor_frames": percent_watercolor_frames,
            "processed_frames": len(results),
            "planned_frames": planned_frames_count,
            "total_video_frames": total_frames,
            "duration_seconds": duration,
            "watercolor_frames_count": watercolor_frames_count,
            "avg_watercolor_confidence": avg_watercolor_confidence
        }
