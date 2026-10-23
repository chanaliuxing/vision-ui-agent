"""
Image optimization for LLM vision processing
Reduces token usage while preserving UI text readability
"""
import os
import math
import logging
import tempfile
from typing import Optional, Tuple
from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

class LLMImageOptimizer:
    """
    Optimizes images for LLM vision processing to reduce token usage
    while maintaining text readability for UI automation
    """

    def __init__(self):
        # Multi-tier sizing strategy
        self.size_tiers = [1280, 1536, 1920]  # Progressive fallback
        self.current_tier = 0

        # Quality-preserving settings
        self.pre_blur_sigma = 0.4
        self.usm_radius = 1.2
        self.usm_percent = 130
        self.usm_threshold = 3

    def estimate_vision_tokens(self, width: int, height: int) -> int:
        """
        Estimate vision tokens using GPT-4o tile-based calculation
        Each 1024x1024 tile ≈ 765 tokens
        """
        tiles_w = math.ceil(width / 1024)
        tiles_h = math.ceil(height / 1024)
        return tiles_w * tiles_h * 765

    def get_target_size(self, original_width: int, original_height: int) -> int:
        """
        Get target long side based on image characteristics and current tier
        Handles retina displays and progressive scaling
        """
        max_dimension = max(original_width, original_height)

        # Detect likely retina/2x captures (common Mac screenshot sizes)
        if max_dimension > 2500:
            logger.info(f"Detected likely retina display ({max_dimension}px), applying 0.5x initial downscale")
            base_target = max_dimension * 0.5
        else:
            base_target = max_dimension

        # Apply tier-based sizing
        tier_target = self.size_tiers[min(self.current_tier, len(self.size_tiers) - 1)]

        # Use smaller of calculated target and tier limit
        return min(int(base_target), tier_target)

    def optimize_for_llm(self, image_path: str, output_path: Optional[str] = None) -> Tuple[str, dict]:
        """
        Optimize image for LLM vision processing

        Args:
            image_path: Path to source image
            output_path: Optional output path, creates temp file if None

        Returns:
            Tuple of (optimized_path, stats_dict)
        """
        try:
            # Load and analyze image
            with Image.open(image_path) as img:
                original_width, original_height = img.size
                original_format = img.format

                # Convert to RGB for processing
                if img.mode != 'RGB':
                    img = img.convert('RGB')

                # Calculate optimization parameters
                target_size = self.get_target_size(original_width, original_height)
                original_tokens = self.estimate_vision_tokens(original_width, original_height)

                # Check if optimization needed
                if max(original_width, original_height) <= target_size:
                    logger.info(f"Image already optimal size ({original_width}x{original_height})")
                    return image_path, {
                        'optimized': False,
                        'original_size': (original_width, original_height),
                        'final_size': (original_width, original_height),
                        'original_tokens': original_tokens,
                        'final_tokens': original_tokens,
                        'reduction_percent': 0
                    }

                # Calculate new dimensions preserving aspect ratio
                scale = target_size / max(original_width, original_height)
                new_width = int(round(original_width * scale))
                new_height = int(round(original_height * scale))

                logger.info(f"Optimizing image: {original_width}x{original_height} → {new_width}x{new_height}")

                # Apply quality-preserving downscale
                optimized_img = self._downscale_with_quality(img, new_width, new_height)

                # Prepare output path
                if output_path is None:
                    suffix = '_optimized.png'
                    base = os.path.splitext(image_path)[0]
                    output_path = f"{base}{suffix}"

                # Save optimized image
                optimized_img.save(output_path, format='PNG', optimize=True)

                # Calculate statistics
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

                logger.info(f"Image optimization complete: {reduction_percent}% token reduction "
                          f"({original_tokens} → {final_tokens} tokens)")

                return output_path, stats

        except Exception as e:
            logger.error(f"Image optimization failed for {image_path}: {e}")
            # Return original path on failure
            return image_path, {'optimized': False, 'error': str(e)}

    def _downscale_with_quality(self, img: Image.Image, new_width: int, new_height: int) -> Image.Image:
        """
        Apply quality-preserving downscale recipe:
        1. Light pre-blur to prevent aliasing
        2. Lanczos resize for clean downsampling
        3. Unsharp mask to restore text clarity
        """
        # Step 1: Light pre-blur to prevent aliasing on thin text/lines
        img_blurred = img.filter(ImageFilter.GaussianBlur(self.pre_blur_sigma))

        # Step 2: High-quality resize with Lanczos
        img_resized = img_blurred.resize((new_width, new_height), Image.LANCZOS)

        # Step 3: Unsharp mask to restore edge clarity for text
        img_sharpened = img_resized.filter(
            ImageFilter.UnsharpMask(
                radius=self.usm_radius,
                percent=self.usm_percent,
                threshold=self.usm_threshold
            )
        )

        return img_sharpened

    def escalate_tier(self) -> bool:
        """
        Move to next size tier for better quality
        Returns True if escalation possible, False if already at max tier
        """
        if self.current_tier < len(self.size_tiers) - 1:
            self.current_tier += 1
            logger.info(f"Escalated to tier {self.current_tier} (target: {self.size_tiers[self.current_tier]}px)")
            return True
        return False

    def reset_tier(self):
        """Reset to base tier (1280px)"""
        self.current_tier = 0

# Convenience functions
def optimize_image_for_llm(image_path: str, output_path: Optional[str] = None) -> Tuple[str, dict]:
    """
    Convenience function to optimize a single image
    """
    optimizer = LLMImageOptimizer()
    return optimizer.optimize_for_llm(image_path, output_path)

def estimate_image_tokens(image_path: str) -> int:
    """
    Estimate token usage for an image file
    """
    try:
        with Image.open(image_path) as img:
            optimizer = LLMImageOptimizer()
            return optimizer.estimate_vision_tokens(img.width, img.height)
    except Exception as e:
        logger.error(f"Failed to estimate tokens for {image_path}: {e}")
        return 0