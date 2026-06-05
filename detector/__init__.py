"""Detector module for object detection"""
from .model_loader import YOLOModelLoader
from .detect import ObjectDetector

__all__ = ["YOLOModelLoader", "ObjectDetector"]
