# vision_utils.py
import io
import base64
import numpy as np
from typing import Union, List, Tuple, Optional
import requests
from PIL import Image
import imagehash
from skimage.metrics import structural_similarity as ssim
import cv2


def to_ndarray(image_input: Union[str, bytes]) -> np.ndarray:
    """
    Convert image_b64 or image_url to numpy array.

    Args:
        image_input: Base64 string (with or without data: prefix) or URL string

    Returns:
        np.ndarray: Image as BGR numpy array (OpenCV format)
    """
    if isinstance(image_input, str):
        if image_input.startswith('http'):
            # URL input
            response = requests.get(image_input, timeout=10)
            response.raise_for_status()
            image_bytes = response.content
        else:
            # Base64 input
            if image_input.startswith('data:image'):
                # Remove data URL prefix
                image_input = image_input.split(',', 1)[1]
            image_bytes = base64.b64decode(image_input)
    else:
        image_bytes = image_input

    # Convert to PIL then to numpy array
    pil_image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    rgb_array = np.array(pil_image)
    # Convert RGB to BGR for OpenCV compatibility
    bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)

    return bgr_array


def crop_by_norm(img: np.ndarray, roi_norm: List[float]) -> np.ndarray:
    """
    Crop image by normalized ROI coordinates.

    Args:
        img: Input image as numpy array
        roi_norm: [x, y, w, h] normalized coordinates (0-1)

    Returns:
        np.ndarray: Cropped image
    """
    h, w = img.shape[:2]
    x, y, width, height = roi_norm

    # Convert normalized to pixel coordinates
    x1 = int(x * w)
    y1 = int(y * h)
    x2 = int((x + width) * w)
    y2 = int((y + height) * h)

    # Ensure coordinates are within image bounds
    x1 = max(0, min(x1, w))
    y1 = max(0, min(y1, h))
    x2 = max(x1, min(x2, w))
    y2 = max(y1, min(y2, h))

    return img[y1:y2, x1:x2]


def calc_phash64(img: np.ndarray) -> str:
    """
    Calculate 64-bit perceptual hash of image.

    Args:
        img: Input image as numpy array (BGR or RGB)

    Returns:
        str: Hexadecimal string representation of hash
    """
    # Convert to PIL Image
    if len(img.shape) == 3:
        # Convert BGR to RGB for PIL
        rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb_img)
    else:
        pil_img = Image.fromarray(img)

    # Calculate perceptual hash with 8x8 size for 64-bit hash
    hash_obj = imagehash.phash(pil_img, hash_size=8)
    return str(hash_obj)


def calc_ssim64(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    Calculate SSIM (Structural Similarity Index) between two images.

    Args:
        img1: First image as numpy array
        img2: Second image as numpy array

    Returns:
        float: SSIM value between -1 and 1 (higher is more similar)
    """
    # Convert to grayscale if needed
    if len(img1.shape) == 3:
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    else:
        gray1 = img1

    if len(img2.shape) == 3:
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    else:
        gray2 = img2

    # Resize images to same size if different
    if gray1.shape != gray2.shape:
        h, w = min(gray1.shape[0], gray2.shape[0]), min(gray1.shape[1], gray2.shape[1])
        gray1 = cv2.resize(gray1, (w, h))
        gray2 = cv2.resize(gray2, (w, h))

    # Calculate SSIM
    similarity = ssim(gray1, gray2, data_range=255)
    return float(similarity)


def calc_red_ratio(img: np.ndarray) -> float:
    """
    Calculate ratio of red pixels in image (useful for detecting red notification dots).

    Args:
        img: Input image as numpy array (BGR format)

    Returns:
        float: Ratio of red pixels (0-1)
    """
    if len(img.shape) != 3:
        return 0.0

    # Convert BGR to HSV for better red detection
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Define red color ranges in HSV
    # Red can be in two ranges: 0-10 and 170-180 hue
    lower_red1 = np.array([0, 50, 50])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 50, 50])
    upper_red2 = np.array([180, 255, 255])

    # Create masks for red regions
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)

    # Calculate ratio
    total_pixels = img.shape[0] * img.shape[1]
    red_pixels = np.sum(red_mask > 0)

    return float(red_pixels) / total_pixels if total_pixels > 0 else 0.0


def calc_phash_delta(hash1: str, hash2: str) -> int:
    """
    Calculate Hamming distance between two perceptual hashes.

    Args:
        hash1: First hash as hex string
        hash2: Second hash as hex string

    Returns:
        int: Hamming distance (number of different bits)
    """
    try:
        # Convert hex strings to imagehash objects for comparison
        h1 = imagehash.hex_to_hash(hash1)
        h2 = imagehash.hex_to_hash(hash2)
        return h1 - h2
    except Exception:
        # If conversion fails, compare as strings
        return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))