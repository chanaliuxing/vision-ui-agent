"""
Image optimization for LLM vision processing
Copied from main project to reduce token usage while keeping text legible.
"""
import os
import math
import logging
import tempfile
from typing import Optional, Tuple
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

class LLMImageOptimizer:
    def __init__(self):
        self.size_tiers = [1280, 1536, 1920]
        self.current_tier = 0
        self.pre_blur_sigma = 0.4
        self.usm_radius = 1.2
        self.usm_percent = 130
        self.usm_threshold = 3

    def estimate_vision_tokens(self, width: int, height: int) -> int:
        tiles_w = math.ceil(width / 1024)
        tiles_h = math.ceil(height / 1024)
        return tiles_w * tiles_h * 765

    def get_target_size(self, original_width: int, original_height: int) -> int:
        max_dimension = max(original_width, original_height)
        if max_dimension > 2500:
            logger.info(f"Detected likely retina display ({max_dimension}px), applying 0.5x initial downscale")
            base_target = max_dimension * 0.5
        else:
            base_target = max_dimension
        tier_target = self.size_tiers[min(self.current_tier, len(self.size_tiers) - 1)]
        return min(int(base_target), tier_target)

    def optimize_for_llm(self, image_path: str, output_path: Optional[str] = None) -> Tuple[str, dict]:
        try:
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                target_size = self.get_target_size(original_width, original_height)
                original_tokens = self.estimate_vision_tokens(original_width, original_height)

                if max(original_width, original_height) <= target_size:
                    return image_path, {
                        'optimized': False,
                        'original_size': (original_width, original_height),
                        'final_size': (original_width, original_height),
                        'original_tokens': original_tokens,
                        'final_tokens': original_tokens,
                        'reduction_percent': 0
                    }

                scale = target_size / max(original_width, original_height)
                new_width = int(round(original_width * scale))
                new_height = int(round(original_height * scale))

                optimized_img = self._downscale_with_quality(img, new_width, new_height)

                if output_path is None:
                    suffix = '_optimized.png'
                    base = os.path.splitext(image_path)[0]
                    output_path = f"{base}{suffix}"

                optimized_img.save(output_path, format='PNG', optimize=True)

                final_tokens = self.estimate_vision_tokens(new_width, new_height)
                reduction_percent = round((1 - final_tokens / original_tokens) * 100, 1)

                stats = {
                    'optimized': True,
                    'original_size': (original_width, original_height),
                    'final_size': (new_width, new_height),
                    'original_tokens': original_tokens,
                    'final_tokens': final_tokens,
                    'reduction_percent': reduction_percent,
                    'scale_factor': scale,
                    'target_size': target_size,
                    'tier_used': self.current_tier
                }

                return output_path, stats

        except Exception as e:
            logger.error(f"Image optimization failed for {image_path}: {e}")
            return image_path, {'optimized': False, 'error': str(e)}

    def _downscale_with_quality(self, img: Image.Image, new_width: int, new_height: int) -> Image.Image:
        img_blurred = img.filter(ImageFilter.GaussianBlur(self.pre_blur_sigma))
        img_resized = img_blurred.resize((new_width, new_height), Image.LANCZOS)
        img_sharpened = img_resized.filter(
            ImageFilter.UnsharpMask(
                radius=self.usm_radius,
                percent=self.usm_percent,
                threshold=self.usm_threshold
            )
        )
        return img_sharpened

    def escalate_tier(self) -> bool:
        if self.current_tier < len(self.size_tiers) - 1:
            self.current_tier += 1
            return True
        return False

    def reset_tier(self):
        self.current_tier = 0

def optimize_image_for_llm(image_path: str, output_path: Optional[str] = None) -> Tuple[str, dict]:
    optimizer = LLMImageOptimizer()
    return optimizer.optimize_for_llm(image_path, output_path)

def estimate_image_tokens(image_path: str) -> int:
    try:
        with Image.open(image_path) as img:
            optimizer = LLMImageOptimizer()
            return optimizer.estimate_vision_tokens(img.width, img.height)
    except Exception as e:
        logger.error(f"Failed to estimate tokens for {image_path}: {e}")
        return 0
