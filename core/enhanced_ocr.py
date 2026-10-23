#!/usr/bin/env python3
"""
Enhanced OCR System
Stage 11: Robustness & Anti-detection & Fault tolerance

Multi-engine OCR system with preprocessing, post-processing, and confidence scoring:
1. Multiple OCR engines (Tesseract, PaddleOCR, EasyOCR)
2. Image preprocessing pipelines
3. Text correction and validation
4. Confidence scoring and fusion
5. Language detection and optimization
"""

import os
import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter
from typing import List, Dict, Optional, Tuple, Any
import re
import difflib
from dataclasses import dataclass
from enum import Enum

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None

try:
    import easyocr
except ImportError:
    easyocr = None

class OCREngine(Enum):
    TESSERACT = "tesseract"
    PADDLE = "paddle"
    EASY = "easy"

@dataclass
class OCRResult:
    """OCR result with confidence and bounding box"""
    text: str
    confidence: float
    bbox: List[int]  # [x1, y1, x2, y2]
    engine: str
    language: Optional[str] = None

@dataclass
class ProcessingConfig:
    """Image preprocessing configuration"""
    denoise: bool = True
    enhance_contrast: bool = True
    sharpen: bool = True
    binarize: bool = True
    deskew: bool = True
    resize_factor: float = 2.0
    min_text_height: int = 12

class EnhancedOCR:
    """Enhanced multi-engine OCR system"""

    def __init__(self, engines: List[OCREngine] = None, languages: List[str] = None):
        self.engines = engines or [OCREngine.TESSERACT, OCREngine.PADDLE]
        self.languages = languages or ['en', 'ch_sim']

        # Initialize engines
        self.tesseract_available = False
        self.paddle_ocr = None
        self.easy_reader = None

        self._init_engines()

        # Common English words for spell checking
        self.common_words = self._load_common_words()

        # Text cleaning patterns
        self.cleanup_patterns = [
            (r'[^\w\s\.\,\!\?\-\(\)\:\;]', ''),  # Remove special chars
            (r'\s+', ' '),  # Normalize whitespace
            (r'(\w)\s+(\w)', r'\1\2'),  # Remove spaces in words (if confidence low)
        ]

    def _init_engines(self) -> None:
        """Initialize available OCR engines"""

        # Tesseract
        if pytesseract and OCREngine.TESSERACT in self.engines:
            try:
                pytesseract.get_tesseract_version()
                self.tesseract_available = True
                print("✅ Tesseract OCR initialized")
            except Exception as e:
                print(f"❌ Tesseract OCR unavailable: {e}")

        # PaddleOCR
        if PaddleOCR and OCREngine.PADDLE in self.engines:
            try:
                self.paddle_ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang='en',
                    show_log=False,
                    use_gpu=False  # CPU for stability
                )
                print("✅ PaddleOCR initialized")
            except Exception as e:
                print(f"❌ PaddleOCR unavailable: {e}")

        # EasyOCR
        if easyocr and OCREngine.EASY in self.engines:
            try:
                self.easy_reader = easyocr.Reader(['en', 'ch_sim'])
                print("✅ EasyOCR initialized")
            except Exception as e:
                print(f"❌ EasyOCR unavailable: {e}")

    def _load_common_words(self) -> set:
        """Load common English words for spell checking"""
        common = {
            'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i',
            'it', 'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at',
            'this', 'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she',
            'or', 'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their',
            'what', 'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go',
            'me', 'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
            'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could', 'them',
            'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come', 'its', 'over'
        }
        return common

    def preprocess_image(self, image: np.ndarray, config: ProcessingConfig) -> np.ndarray:
        """Apply image preprocessing pipeline"""
        result = image.copy()

        # Convert to PIL for some operations
        pil_img = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_BGR2RGB))

        # Resize for better OCR accuracy
        if config.resize_factor != 1.0:
            new_width = int(pil_img.width * config.resize_factor)
            new_height = int(pil_img.height * config.resize_factor)
            pil_img = pil_img.resize((new_width, new_height), Image.LANCZOS)

        # Enhance contrast
        if config.enhance_contrast:
            enhancer = ImageEnhance.Contrast(pil_img)
            pil_img = enhancer.enhance(1.5)

        # Sharpen
        if config.sharpen:
            pil_img = pil_img.filter(ImageFilter.SHARPEN)

        # Convert back to OpenCV
        result = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        # Denoise
        if config.denoise:
            result = cv2.fastNlMeansDenoisingColored(result, None, 10, 10, 7, 15)

        # Convert to grayscale for remaining operations
        gray = cv2.cvtColor(result, cv2.COLOR_BGR2GRAY)

        # Deskew (simple rotation correction)
        if config.deskew:
            gray = self._deskew_image(gray)

        # Binarization (adaptive threshold)
        if config.binarize:
            gray = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
            )

        return gray

    def _deskew_image(self, image: np.ndarray) -> np.ndarray:
        """Correct image skew using line detection"""
        try:
            # Detect lines using HoughLinesP
            edges = cv2.Canny(image, 50, 150, apertureSize=3)
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=100, minLineLength=100, maxLineGap=10)

            if lines is not None:
                # Calculate angles of detected lines
                angles = []
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    angle = np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi
                    angles.append(angle)

                if angles:
                    # Use median angle to correct skew
                    median_angle = np.median(angles)
                    if abs(median_angle) > 0.5:  # Only correct if significant skew
                        (h, w) = image.shape[:2]
                        center = (w // 2, h // 2)
                        M = cv2.getRotationMatrix2D(center, median_angle, 1.0)
                        image = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        except Exception:
            pass  # Return original if deskewing fails

        return image

    def run_tesseract(self, image: np.ndarray, config: ProcessingConfig) -> List[OCRResult]:
        """Run Tesseract OCR with configuration"""
        if not self.tesseract_available:
            return []

        results = []
        try:
            # Configure Tesseract
            custom_config = r'--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz '

            # Get detailed results with bounding boxes
            data = pytesseract.image_to_data(image, config=custom_config, output_type=pytesseract.Output.DICT)

            n_boxes = len(data['level'])
            for i in range(n_boxes):
                confidence = float(data['conf'][i])
                text = data['text'][i].strip()

                if confidence > 30 and len(text) > 0:  # Filter low confidence
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    if h >= config.min_text_height:  # Filter small text
                        results.append(OCRResult(
                            text=text,
                            confidence=confidence / 100.0,  # Normalize to 0-1
                            bbox=[x, y, x + w, y + h],
                            engine="tesseract"
                        ))
        except Exception as e:
            print(f"Tesseract OCR error: {e}")

        return results

    def run_paddle_ocr(self, image: np.ndarray, config: ProcessingConfig) -> List[OCRResult]:
        """Run PaddleOCR with configuration"""
        if not self.paddle_ocr:
            return []

        results = []
        try:
            # PaddleOCR expects RGB
            if len(image.shape) == 3:
                rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            else:
                rgb_image = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)

            paddle_results = self.paddle_ocr.ocr(rgb_image, cls=True)

            if paddle_results and paddle_results[0]:
                for line in paddle_results[0]:
                    if len(line) >= 2:
                        bbox_points = line[0]
                        text_info = line[1]

                        if isinstance(text_info, tuple) and len(text_info) >= 2:
                            text = text_info[0].strip()
                            confidence = text_info[1]

                            if confidence > 0.3 and len(text) > 0:
                                # Convert polygon to bounding box
                                xs = [p[0] for p in bbox_points]
                                ys = [p[1] for p in bbox_points]
                                x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

                                if (y2 - y1) >= config.min_text_height:
                                    results.append(OCRResult(
                                        text=text,
                                        confidence=confidence,
                                        bbox=[x1, y1, x2, y2],
                                        engine="paddle"
                                    ))
        except Exception as e:
            print(f"PaddleOCR error: {e}")

        return results

    def run_easy_ocr(self, image: np.ndarray, config: ProcessingConfig) -> List[OCRResult]:
        """Run EasyOCR with configuration"""
        if not self.easy_reader:
            return []

        results = []
        try:
            easy_results = self.easy_reader.readtext(image, detail=1, paragraph=False)

            for result in easy_results:
                if len(result) >= 3:
                    bbox_points = result[0]
                    text = result[1].strip()
                    confidence = result[2]

                    if confidence > 0.3 and len(text) > 0:
                        # Convert polygon to bounding box
                        xs = [p[0] for p in bbox_points]
                        ys = [p[1] for p in bbox_points]
                        x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))

                        if (y2 - y1) >= config.min_text_height:
                            results.append(OCRResult(
                                text=text,
                                confidence=confidence,
                                bbox=[x1, y1, x2, y2],
                                engine="easy"
                            ))
        except Exception as e:
            print(f"EasyOCR error: {e}")

        return results

    def clean_text(self, text: str, confidence: float) -> str:
        """Clean and correct OCR text"""
        result = text.strip()

        # Apply cleanup patterns
        for pattern, replacement in self.cleanup_patterns:
            result = re.sub(pattern, replacement, result)

        # Spell correction for low confidence text
        if confidence < 0.7:
            result = self._spell_correct(result)

        return result.strip()

    def _spell_correct(self, text: str) -> str:
        """Simple spell correction using common words"""
        words = text.split()
        corrected = []

        for word in words:
            word_lower = word.lower()
            if word_lower in self.common_words:
                corrected.append(word)
            else:
                # Find closest match
                matches = difflib.get_close_matches(word_lower, self.common_words, n=1, cutoff=0.8)
                if matches:
                    # Preserve original case
                    if word.isupper():
                        corrected.append(matches[0].upper())
                    elif word.istitle():
                        corrected.append(matches[0].title())
                    else:
                        corrected.append(matches[0])
                else:
                    corrected.append(word)

        return ' '.join(corrected)

    def fuse_results(self, all_results: List[List[OCRResult]]) -> List[OCRResult]:
        """Fuse results from multiple OCR engines"""
        if not all_results:
            return []

        # Flatten all results
        flat_results = []
        for engine_results in all_results:
            flat_results.extend(engine_results)

        if not flat_results:
            return []

        # Group overlapping results
        fused = []
        used = set()

        for i, result in enumerate(flat_results):
            if i in used:
                continue

            # Find overlapping results
            group = [result]
            used.add(i)

            for j, other in enumerate(flat_results[i+1:], i+1):
                if j in used:
                    continue

                if self._boxes_overlap(result.bbox, other.bbox, threshold=0.5):
                    group.append(other)
                    used.add(j)

            # Fuse group into single result
            if len(group) == 1:
                fused_result = group[0]
            else:
                fused_result = self._fuse_group(group)

            fused.append(fused_result)

        # Sort by position (top to bottom, left to right)
        fused.sort(key=lambda r: (r.bbox[1], r.bbox[0]))

        return fused

    def _boxes_overlap(self, box1: List[int], box2: List[int], threshold: float = 0.5) -> bool:
        """Check if two bounding boxes overlap significantly"""
        x1a, y1a, x2a, y2a = box1
        x1b, y1b, x2b, y2b = box2

        # Calculate intersection
        ix1 = max(x1a, x1b)
        iy1 = max(y1a, y1b)
        ix2 = min(x2a, x2b)
        iy2 = min(y2a, y2b)

        if ix2 <= ix1 or iy2 <= iy1:
            return False

        intersection = (ix2 - ix1) * (iy2 - iy1)
        area1 = (x2a - x1a) * (y2a - y1a)
        area2 = (x2b - x1b) * (y2b - y1b)

        # IoU (Intersection over Union)
        union = area1 + area2 - intersection
        iou = intersection / union if union > 0 else 0

        return iou >= threshold

    def _fuse_group(self, group: List[OCRResult]) -> OCRResult:
        """Fuse a group of overlapping OCR results"""
        # Choose result with highest confidence
        best = max(group, key=lambda r: r.confidence)

        # Calculate average bounding box
        all_x1 = [r.bbox[0] for r in group]
        all_y1 = [r.bbox[1] for r in group]
        all_x2 = [r.bbox[2] for r in group]
        all_y2 = [r.bbox[3] for r in group]

        avg_bbox = [
            int(sum(all_x1) / len(all_x1)),
            int(sum(all_y1) / len(all_y1)),
            int(sum(all_x2) / len(all_x2)),
            int(sum(all_y2) / len(all_y2))
        ]

        # Try to improve text by consensus
        texts = [r.text for r in group]
        if len(set(texts)) > 1:
            # If texts differ, choose the one from the engine with highest confidence
            chosen_text = best.text
        else:
            chosen_text = texts[0]

        return OCRResult(
            text=chosen_text,
            confidence=best.confidence,
            bbox=avg_bbox,
            engine=f"fused({','.join(set(r.engine for r in group))})"
        )

    def extract_text(self, image: np.ndarray, config: ProcessingConfig = None) -> List[OCRResult]:
        """Main OCR extraction method"""
        if config is None:
            config = ProcessingConfig()

        # Preprocess image
        processed = self.preprocess_image(image, config)

        # Run all available engines
        all_results = []

        if self.tesseract_available and OCREngine.TESSERACT in self.engines:
            tesseract_results = self.run_tesseract(processed, config)
            all_results.append(tesseract_results)

        if self.paddle_ocr and OCREngine.PADDLE in self.engines:
            paddle_results = self.run_paddle_ocr(processed, config)
            all_results.append(paddle_results)

        if self.easy_reader and OCREngine.EASY in self.engines:
            easy_results = self.run_easy_ocr(processed, config)
            all_results.append(easy_results)

        # Fuse results from different engines
        fused_results = self.fuse_results(all_results)

        # Clean and post-process text
        for result in fused_results:
            result.text = self.clean_text(result.text, result.confidence)

        # Filter empty results
        final_results = [r for r in fused_results if len(r.text.strip()) > 0]

        return final_results

    def extract_text_simple(self, image: np.ndarray) -> List[str]:
        """Simple text extraction returning just text strings"""
        results = self.extract_text(image)
        return [r.text for r in results]

    def extract_text_lines(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """Extract text with line structure similar to original OCR client"""
        results = self.extract_text(image)

        lines = []
        for result in results:
            # Convert bbox to polygon format (for compatibility)
            x1, y1, x2, y2 = result.bbox
            polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

            lines.append({
                'text': result.text,
                'polygon': polygon,
                'conf': result.confidence,
                'engine': result.engine
            })

        return lines