#!/usr/bin/env python3
"""
Coordinate Utilities - DPR and Window Coordinate Handling
Handles coordinate system transformations and DPR scaling
"""

from typing import List, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CoordinateTransformer:
    """Handles coordinate transformations between different coordinate systems"""

    def __init__(self):
        pass

    def transform_point_to_screen(self, point_in_capture: List[int],
                                capture_spec: Dict[str, Any]) -> List[int]:
        """
        Transform point from capture coordinates to screen coordinates

        Args:
            point_in_capture: Point coordinates [x, y] in capture coordinate system
            capture_spec: Capture specification with mode, offsets, DPR, etc.

        Returns:
            Point coordinates [x, y] in screen coordinate system
        """
        try:
            x_capture, y_capture = point_in_capture
            mode = capture_spec.get("mode", "full")
            dpr = capture_spec.get("dpr", 1.0)

            # Start with capture coordinates
            x_screen = x_capture
            y_screen = y_capture

            # Apply window offset if not full screen
            if mode in ["active_window", "region"]:
                window_offset = capture_spec.get("window_offset", [0, 0])
                x_screen += window_offset[0]
                y_screen += window_offset[1]

            # Apply DPR scaling if needed
            # Note: This depends on how the screenshot was taken
            # If screenshot was taken at physical pixel resolution, divide by DPR
            # If screenshot was taken at logical pixel resolution, no scaling needed
            if dpr != 1.0:
                # For now, assume screenshots are at logical resolution
                # In practice, this would depend on the capture implementation
                pass

            return [int(x_screen), int(y_screen)]

        except Exception as e:
            logger.error(f"Coordinate transformation failed: {e}")
            return point_in_capture  # Return original coordinates as fallback

    def transform_bbox_to_screen(self, bbox_in_capture: List[int],
                               capture_spec: Dict[str, Any]) -> List[int]:
        """
        Transform bounding box from capture coordinates to screen coordinates

        Args:
            bbox_in_capture: Bounding box [x1, y1, x2, y2] in capture coordinates
            capture_spec: Capture specification

        Returns:
            Bounding box [x1, y1, x2, y2] in screen coordinates
        """
        try:
            # Transform top-left and bottom-right points
            top_left = self.transform_point_to_screen(
                [bbox_in_capture[0], bbox_in_capture[1]], capture_spec
            )
            bottom_right = self.transform_point_to_screen(
                [bbox_in_capture[2], bbox_in_capture[3]], capture_spec
            )

            return [top_left[0], top_left[1], bottom_right[0], bottom_right[1]]

        except Exception as e:
            logger.error(f"Bbox transformation failed: {e}")
            return bbox_in_capture

    def normalize_coordinates(self, point: List[int], reference_size: List[int]) -> List[float]:
        """
        Normalize coordinates to [0, 1] range

        Args:
            point: Point coordinates [x, y] in pixels
            reference_size: Reference size [width, height] in pixels

        Returns:
            Normalized coordinates [x_norm, y_norm] in [0, 1] range
        """
        try:
            x, y = point
            width, height = reference_size

            x_norm = max(0.0, min(1.0, x / width))
            y_norm = max(0.0, min(1.0, y / height))

            return [x_norm, y_norm]

        except Exception as e:
            logger.error(f"Coordinate normalization failed: {e}")
            return [0.0, 0.0]

    def denormalize_coordinates(self, point_norm: List[float],
                              reference_size: List[int]) -> List[int]:
        """
        Denormalize coordinates from [0, 1] range to pixels

        Args:
            point_norm: Normalized coordinates [x_norm, y_norm] in [0, 1] range
            reference_size: Reference size [width, height] in pixels

        Returns:
            Point coordinates [x, y] in pixels
        """
        try:
            x_norm, y_norm = point_norm
            width, height = reference_size

            x = int(x_norm * width)
            y = int(y_norm * height)

            return [x, y]

        except Exception as e:
            logger.error(f"Coordinate denormalization failed: {e}")
            return [0, 0]

    def normalize_bbox(self, bbox: List[int], reference_size: List[int]) -> List[float]:
        """
        Normalize bounding box to [0, 1] range

        Args:
            bbox: Bounding box [x1, y1, x2, y2] in pixels
            reference_size: Reference size [width, height] in pixels

        Returns:
            Normalized bounding box [x1_norm, y1_norm, x2_norm, y2_norm]
        """
        try:
            x1, y1, x2, y2 = bbox
            width, height = reference_size

            x1_norm = max(0.0, min(1.0, x1 / width))
            y1_norm = max(0.0, min(1.0, y1 / height))
            x2_norm = max(0.0, min(1.0, x2 / width))
            y2_norm = max(0.0, min(1.0, y2 / height))

            return [x1_norm, y1_norm, x2_norm, y2_norm]

        except Exception as e:
            logger.error(f"Bbox normalization failed: {e}")
            return [0.0, 0.0, 1.0, 1.0]

    def denormalize_bbox(self, bbox_norm: List[float],
                        reference_size: List[int]) -> List[int]:
        """
        Denormalize bounding box from [0, 1] range to pixels

        Args:
            bbox_norm: Normalized bbox [x1_norm, y1_norm, x2_norm, y2_norm]
            reference_size: Reference size [width, height] in pixels

        Returns:
            Bounding box [x1, y1, x2, y2] in pixels
        """
        try:
            x1_norm, y1_norm, x2_norm, y2_norm = bbox_norm
            width, height = reference_size

            x1 = int(x1_norm * width)
            y1 = int(y1_norm * height)
            x2 = int(x2_norm * width)
            y2 = int(y2_norm * height)

            return [x1, y1, x2, y2]

        except Exception as e:
            logger.error(f"Bbox denormalization failed: {e}")
            return [0, 0, width, height]

    def scale_coordinates_by_dpr(self, coordinates: List[int], dpr: float,
                                direction: str = "down") -> List[int]:
        """
        Scale coordinates by device pixel ratio

        Args:
            coordinates: Coordinates to scale (can be point or bbox)
            dpr: Device pixel ratio
            direction: "down" to scale down (physical->logical), "up" to scale up

        Returns:
            Scaled coordinates
        """
        try:
            if dpr == 1.0:
                return coordinates

            scale_factor = 1.0 / dpr if direction == "down" else dpr

            return [int(coord * scale_factor) for coord in coordinates]

        except Exception as e:
            logger.error(f"DPR scaling failed: {e}")
            return coordinates

    def validate_coordinates(self, point: List[int], bounds: List[int]) -> bool:
        """
        Validate that coordinates are within bounds

        Args:
            point: Point coordinates [x, y]
            bounds: Bounds [width, height]

        Returns:
            True if coordinates are valid
        """
        try:
            x, y = point
            width, height = bounds

            return 0 <= x < width and 0 <= y < height

        except Exception as e:
            logger.error(f"Coordinate validation failed: {e}")
            return False

    def create_mapping_hint(self, capture_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create mapping hint for client coordinate transformation

        Args:
            capture_spec: Capture specification

        Returns:
            Mapping hint dictionary
        """
        mode = capture_spec.get("mode", "full")
        dpr = capture_spec.get("dpr", 1.0)

        return {
            "apply_window_offset": mode != "full",
            "expects_dpr": dpr,
            "mode": mode,
            "transformation_needed": mode != "full" or dpr != 1.0
        }


class DPRHandler:
    """Handles Device Pixel Ratio (DPR) specific operations"""

    @staticmethod
    def detect_dpr() -> float:
        """
        Detect current device pixel ratio

        Returns:
            Detected DPR value (fallback to 1.0)
        """
        # This is a placeholder implementation
        # In practice, DPR would be detected from the client environment
        # or provided in the request
        return 1.0

    @staticmethod
    def adjust_image_size_for_dpr(logical_size: List[int], dpr: float) -> List[int]:
        """
        Calculate physical image size from logical size and DPR

        Args:
            logical_size: Logical size [width, height]
            dpr: Device pixel ratio

        Returns:
            Physical size [width, height]
        """
        return [int(logical_size[0] * dpr), int(logical_size[1] * dpr)]

    @staticmethod
    def get_dpr_info(capture_spec: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get DPR information from capture specification

        Args:
            capture_spec: Capture specification

        Returns:
            DPR information dictionary
        """
        dpr = capture_spec.get("dpr", 1.0)
        screen_size = capture_spec.get("screen_size", [1920, 1080])

        return {
            "dpr": dpr,
            "logical_size": screen_size,
            "physical_size": DPRHandler.adjust_image_size_for_dpr(screen_size, dpr),
            "scaling_needed": dpr != 1.0
        }


# Global coordinate transformer instance
_coordinate_transformer = None

def get_coordinate_transformer() -> CoordinateTransformer:
    """Get singleton coordinate transformer instance"""
    global _coordinate_transformer
    if _coordinate_transformer is None:
        _coordinate_transformer = CoordinateTransformer()
    return _coordinate_transformer


# Utility functions for common operations
def transform_response_coordinates(response_data: Dict[str, Any],
                                 capture_spec: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform all coordinates in a response from capture to screen coordinates

    Args:
        response_data: Response data containing coordinates
        capture_spec: Capture specification

    Returns:
        Response data with transformed coordinates
    """
    transformer = get_coordinate_transformer()

    # Transform decision coordinates
    if "decision" in response_data:
        decision = response_data["decision"]

        if "point_in_capture" in decision:
            point_screen = transformer.transform_point_to_screen(
                decision["point_in_capture"], capture_spec
            )
            decision["point_in_screen"] = point_screen

        if "bbox_in_capture" in decision and decision["bbox_in_capture"]:
            bbox_screen = transformer.transform_bbox_to_screen(
                decision["bbox_in_capture"], capture_spec
            )
            decision["bbox_in_screen"] = bbox_screen

    # Transform per-element coordinates (explain_all mode)
    elements = response_data.get("elements")
    if isinstance(elements, list):
        for el in elements:
            if not isinstance(el, dict):
                continue
            if "point_in_capture" in el:
                try:
                    el["point_in_screen"] = transformer.transform_point_to_screen(
                        el["point_in_capture"], capture_spec
                    )
                except Exception:
                    pass
            if "bbox_in_capture" in el and el.get("bbox_in_capture"):
                try:
                    el["bbox_in_screen"] = transformer.transform_bbox_to_screen(
                        el["bbox_in_capture"], capture_spec
                    )
                except Exception:
                    pass

    return response_data


def validate_capture_spec(capture_spec: Dict[str, Any]) -> bool:
    """
    Validate capture specification

    Args:
        capture_spec: Capture specification to validate

    Returns:
        True if specification is valid
    """
    required_fields = ["mode", "screen_size"]

    for field in required_fields:
        if field not in capture_spec:
            logger.error(f"Missing required field in capture_spec: {field}")
            return False

    mode = capture_spec.get("mode")
    if mode not in ["full", "active_window", "region"]:
        logger.error(f"Invalid capture mode: {mode}")
        return False

    if mode in ["active_window", "region"]:
        if "window_offset" not in capture_spec or "window_size" not in capture_spec:
            logger.error(f"window_offset and window_size required for mode: {mode}")
            return False

    return True
