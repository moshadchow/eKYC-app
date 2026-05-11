"""Backwards-compatibility shim — logic moved to app/services/ocr_service.py."""
from app.services.ocr_service import MockOCRService

mock_ocr_service = MockOCRService()
