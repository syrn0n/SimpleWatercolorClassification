import torch
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from typing import Union, Dict


class WatercolorClassifier:
    def __init__(self, model_name: str = "openai/clip-vit-base-patch32"):
        """
        Initialize the CLIP model and processor.
        """
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        # For Mac M1/M2/M3 chips, use mps if available
        if torch.backends.mps.is_available():
            self.device = "mps"

        print(f"Loading model {model_name} on {self.device}...")
        self.model = CLIPModel.from_pretrained(model_name).to(self.device)
        self.processor = CLIPProcessor.from_pretrained(model_name)

        # Define the labels we want to classify against
        self.labels = [
            "a watercolor painting",
            "an oil painting",
            "a pencil sketch",
            "a photograph",
            "digital art",
            "an acrylic painting",
            "a vector illustration",
            "a black and white photo"
        ]
        self.target_label = "a watercolor painting"

    def predict(self, image: Union[str, Image.Image]) -> Dict[str, float]:
        """
        Predict the probability of the image being a watercolor painting vs other styles.
        """
        if isinstance(image, str):
            image = Image.open(image)

        inputs = self.processor(
            text=self.labels,
            images=image,
            return_tensors="pt",
            padding=True
        ).to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)
            logits_per_image = outputs.logits_per_image  # this is the image-text similarity score
            probs = logits_per_image.softmax(dim=1)  # we can take the softmax to get the label probabilities

        # Convert to dictionary
        probs_list = probs.cpu().tolist()[0]
        result = {label: prob for label, prob in zip(self.labels, probs_list)}
        return result

    def is_watercolor(self, image_path: str, threshold: float = 0.85) -> bool:
        """
        Determine if an image is a watercolor painting.

        Args:
            image_path: Path to the image file or PIL Image object.
            threshold: Minimum probability threshold.

        Returns:
            Boolean indicating if the image is classified as watercolor.
        """
        probs = self.predict(image_path)
        wc_prob = probs.get("a watercolor painting", 0.0)

        # Check if watercolor has the highest probability and exceeds threshold
        return wc_prob > threshold and max(probs, key=probs.get) == "a watercolor painting"

    def is_watercolor_strict(self, image_path: str, threshold: float = 0.85,
                              min_margin: float = 0.15, max_photo_prob: float = 0.3,
                              max_digital_prob: float = 0.3) -> bool:
        """
        Strict watercolor classification with multiple conditions to minimize false positives.

        Args:
            image_path: Path to the image file or PIL Image object.
            threshold: Minimum probability threshold for watercolor.
            min_margin: Minimum margin between top and second-best category.
            max_photo_prob: Maximum allowed probability for "photograph" category.
            max_digital_prob: Maximum allowed probability for "digital art" category.

        Returns:
            Boolean indicating if the image passes all strict watercolor checks.
        """
        probs = self.predict(image_path)
        wc_prob = probs.get("a watercolor painting", 0.0)

        # Condition 1: Watercolor must be highest
        if max(probs, key=probs.get) != "a watercolor painting":
            return False

        # Condition 2: Watercolor probability must exceed threshold
        if wc_prob < threshold:
            return False

        # Condition 3: Margin over second-best must be significant
        sorted_probs = sorted(probs.values(), reverse=True)
        if len(sorted_probs) > 1:
            margin = sorted_probs[0] - sorted_probs[1]
            if margin < min_margin:
                return False

        # Condition 4: Non-watercolor categories should be low
        photo_prob = probs.get("a photograph", 0.0)
        digital_prob = probs.get("digital art", 0.0)
        if photo_prob > max_photo_prob or digital_prob > max_digital_prob:
            return False

        return True
