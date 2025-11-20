# Watercolor Classification Tool

A Python tool to classify images and videos as watercolor paintings using OpenAI's CLIP model.

## Features
- **High Accuracy**: Uses CLIP (Contrastive Language-Image Pre-training) for zero-shot classification.
- **Video Support**: Processes videos by sampling frames and aggregating results.
- **Easy to Use**: Simple CLI interface.

## Installation

This project uses `uv` for dependency management.

```bash
# Install dependencies
uv sync
```

## Usage

### Classify an Image

```bash
uv run python main.py path/to/image.jpg
```

### Classify a Video

```bash
uv run python main.py path/to/video.mp4
```

### Options

- `--threshold`: Set the confidence threshold (default: 0.85).

## How it Works

The tool uses `openai/clip-vit-base-patch32` to compare the input image against a set of text prompts:
- "a watercolor painting"
- "an oil painting"
- "a photograph"
- etc.

It calculates the probability distribution and determines if "a watercolor painting" is the most likely category with sufficient confidence.
