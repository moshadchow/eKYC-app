"""
OCR Service abstraction layer.
Set OCR_PROVIDER env var to switch between mock and production providers.
Set MOCK_OCR_SCENARIO to test different mock outcomes:
  high_confidence  (default) — all fields, confidence 0.92
  low_confidence             — all fields, confidence 0.40
  missing_nid                — extracted_nid=None, confidence 0.92
  missing_dob                — extracted_dob=None, confidence 0.92
"""

import json
import os
from abc import ABC, abstractmethod

from app.core.config import settings

_SCENARIO = os.getenv("MOCK_OCR_SCENARIO", "high_confidence")

_BASE = {
    "extracted_name_en": "Mohammad Karim",
    "extracted_name_bn": "মোহাম্মদ করিম",
    "extracted_nid": "1234567890123",
    "extracted_dob": "1990-05-15",
    "extracted_address": "House 12, Road 4, Dhanmondi, Dhaka-1205",
    "extracted_fathers_name": "Abdul Karim",
    "extracted_mothers_name": "Fatema Begum",
}


class BaseOCRService(ABC):
    @abstractmethod
    async def extract(self, nid_front_key: str, nid_back_key: str) -> dict: ...


class MockOCRService(BaseOCRService):

    async def extract(self, nid_front_key: str, nid_back_key: str) -> dict:
        if _SCENARIO == "low_confidence":
            result = {**_BASE, "confidence_score": 0.40}
        elif _SCENARIO == "missing_nid":
            result = {**_BASE, "extracted_nid": None, "confidence_score": 0.92}
        elif _SCENARIO == "missing_dob":
            result = {**_BASE, "extracted_dob": None, "confidence_score": 0.92}
        else:
            result = {**_BASE, "confidence_score": 0.92}

        result["source_front_key"] = nid_front_key
        result["source_back_key"] = nid_back_key
        result["ocr_provider"] = "mock"
        result["field_confidence"] = None
        result["quality_flags"] = None
        result["raw_json"] = json.dumps(result)
        return result


class AWSTextractOCRService(BaseOCRService):

    async def extract(self, nid_front_key: str, nid_back_key: str) -> dict:
        raise NotImplementedError(
            "AWSTextractOCRService requires production credentials and NID card layout mapping. "
            "See spec step-3-ocr-extraction.md for implementation guide."
        )


def get_ocr_service() -> BaseOCRService:
    if settings.OCR_PROVIDER == "aws_textract":
        return AWSTextractOCRService()
    return MockOCRService()
