# client/ocr/utils.py
import cv2
import numpy as np

def preprocess_for_ocr(img: np.ndarray) -> np.ndarray:
    """预处理图像以提升OCR准确度"""
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    # 自适应二值化
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    # 去噪声
    kernel = np.ones((1, 1), np.uint8)
    clean = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return clean

def extract_text_regions(img: np.ndarray, min_area=100):
    """提取可能包含文本的区域"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    # 查找轮廓
    contours, _ = cv2.findContours(gray, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(contour)
            regions.append({"x": x, "y": y, "w": w, "h": h, "area": area})

    return regions