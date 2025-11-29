import cv2
from PIL import Image
from typing import Dict, Optional, Tuple
from .database import DatabaseManager
from tqdm import tqdm
from .classifier import WatercolorClassifier


class VideoProcessor:
    def __init__(self, classifier: WatercolorClassifier, db_path: str = None, use_cache: bool = True):
        self.classifier = classifier
        self.use_cache = use_cache
        self.db = DatabaseManager(db_path) if db_path and use_cache else None

    def process_video(self, video_path: str, sample_interval_sec: float = 1.0, min_frames: int = 3,
                     detection_threshold: float = 0.3, strict_mode: bool = False,
                     image_threshold: float = 0.85) -> Dict[str, any]:
        """
        Process a video file, sampling frames and classifying them.
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Could not open video file: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0

        frame_interval, planned_frames_count = self._calculate_frame_parameters(
            fps, total_frames, sample_interval_sec, min_frames
        )

        # Optimization: Early stopping
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

        pbar = tqdm(total=planned_frames_count)

        current_frame = 0
        processed_count = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if current_frame % frame_interval == 0:
                result_data = self._process_frame(
                    frame, current_frame, fps, strict_mode, image_threshold
                )

                results.append(result_data)
                watercolor_probs.append(result_data["probs"].get("a watercolor painting", 0.0))
                processed_count += 1
                pbar.update(1)

                # Early stopping check
                if self._check_early_stopping(
                    early_stop_threshold_frames, processed_count, results, detection_threshold
                ):
                    break

            current_frame += 1

        cap.release()
        pbar.close()

        return self._aggregate_results(
            results, watercolor_probs, planned_frames_count, total_frames, duration, detection_threshold
        )

    def _calculate_frame_parameters(self, fps, total_frames, sample_interval_sec, min_frames):
        """Calculate frame interval and planned frames count."""
        frame_interval = int(fps * sample_interval_sec)

        if total_frames > 0:
            max_interval_for_min_frames = total_frames // min_frames
            if max_interval_for_min_frames == 0:
                max_interval_for_min_frames = 1

            if frame_interval > max_interval_for_min_frames or frame_interval == 0:
                frame_interval = max_interval_for_min_frames

        if frame_interval < 1:
            frame_interval = 1

        planned_frames_count = 0
        if total_frames > 0:
            planned_frames_count = (total_frames // frame_interval) + 1

        return frame_interval, planned_frames_count

    def _process_frame(self, frame, current_frame, fps, strict_mode, image_threshold):
        """Process a single video frame."""
        # OpenCV is BGR, PIL needs RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        probs = self.classifier.predict(pil_image)
        wc_prob = probs.get("a watercolor painting", 0.0)

        if strict_mode:
            is_wc = self.classifier.is_watercolor_strict(pil_image, threshold=image_threshold)
        else:
            is_wc = wc_prob > 0.5 and max(probs, key=probs.get) == "a watercolor painting"

        return {
            "frame_index": current_frame,
            "timestamp": current_frame / fps if fps > 0 else 0,
            "probs": probs,
            "is_watercolor": is_wc,
            "top_label": max(probs, key=probs.get)
        }

    def _check_early_stopping(self, threshold_frames, processed_count, results, detection_threshold):
        """Check if early stopping condition is met."""
        if threshold_frames > 0 and processed_count == threshold_frames:
            current_wc_count = sum(1 for r in results if r["is_watercolor"])
            current_percent = current_wc_count / processed_count

            if current_percent >= detection_threshold:
                print(f"\nEarly stopping triggered: {current_percent:.2%} watercolor frames detected after {processed_count} frames.")
                return True
        return False

    def _aggregate_results(self, results, watercolor_probs, planned_frames, total_frames, duration, detection_threshold):
        """Aggregate frame results into final video result."""
        if not results:
            return {
                "is_watercolor": False,
                "confidence": 0.0,
                "details": "No frames processed",
                "processed_frames": 0,
                "planned_frames": planned_frames,
                "total_frames": total_frames,
                "duration_seconds": duration,
                "watercolor_frames_count": 0,
                "percent_watercolor_frames": 0.0,
                "avg_watercolor_confidence": 0.0
            }

        avg_confidence = sum(watercolor_probs) / len(watercolor_probs)
        watercolor_frames_count = sum(1 for r in results if r["is_watercolor"])
        percent_watercolor_frames = watercolor_frames_count / len(results)

        watercolor_confidences = [r["probs"].get("a watercolor painting", 0.0) for r in results if r["is_watercolor"]]
        avg_watercolor_confidence = sum(watercolor_confidences) / len(watercolor_confidences) if watercolor_confidences else 0.0

        is_video_watercolor = percent_watercolor_frames >= detection_threshold

        # Determine top label for the video (most frequent top label across frames)
        from collections import Counter
        top_labels = [r.get("top_label") for r in results if r.get("top_label")]
        video_top_label = Counter(top_labels).most_common(1)[0][0] if top_labels else None

        return {
            "is_watercolor": is_video_watercolor,
            "confidence": avg_confidence,
            "percent_watercolor_frames": percent_watercolor_frames,
            "processed_frames": len(results),
            "planned_frames": planned_frames,
            "total_frames": total_frames,
            "duration_seconds": duration,
            "watercolor_frames_count": watercolor_frames_count,
            "avg_watercolor_confidence": avg_watercolor_confidence,
            "top_label": video_top_label
        }

    def process_video_with_cache(self, video_path: str, force: bool = False, quick_sync: bool = False, **kwargs) -> Dict:
        """
        Process video with database caching.
        """
        # Check cache if enabled
        if self.db and not force:
            if quick_sync:
                needs_processing, cached = self.db.check_if_processed_quick(video_path)
            else:
                needs_processing, cached = self.db.check_if_processed(video_path)
            
            if not needs_processing:
                return cached

        # Process video
        result = self.process_video(video_path, **kwargs)

        # Add file path and type
        result['file_path'] = video_path
        result['file_type'] = 'video'

        # Save to cache
        if self.db:
            self.db.save_result(video_path, result)

        return result
