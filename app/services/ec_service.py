"""
EC (Election Commission) Service abstraction layer.
Set EC_PROVIDER=real in .env to switch to the production Bangladesh EC API.
"""

import random
from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from app.core.config import settings

_VALID_NIDS = {
    "1234567890123": {"dob": date(1990, 5, 15), "name": "Mohammad Karim"},
    "9876543210987": {"dob": date(1985, 3, 22), "name": "Fatema Akter"},
    "1111222233334": {"dob": date(1995, 11, 8), "name": "Rahim Uddin"},
}


class BaseECService(ABC):
    @abstractmethod
    async def validate_nid(self, nid_number: str, date_of_birth: date) -> dict: ...

    @abstractmethod
    async def face_match(self, nid_number: str, selfie_storage_key: str) -> dict: ...

    @abstractmethod
    async def fingerprint_match(
        self, nid_number: str, fingerprint_template: str, finger_position: Optional[str]
    ) -> dict: ...


class MockECService(BaseECService):

    async def validate_nid(self, nid_number: str, date_of_birth: date) -> dict:
        if nid_number in _VALID_NIDS:
            record = _VALID_NIDS[nid_number]
            if record["dob"] == date_of_birth:
                return {
                    "matched": True,
                    "nid_number": nid_number,
                    "full_name_en": record["name"],
                    "full_name_bn": f"বাংলা নাম - {nid_number[-4:]}",
                    "fathers_name_en": "Father Name EN",
                    "fathers_name_bn": "পিতার নাম",
                    "mothers_name_en": "Mother Name EN",
                    "mothers_name_bn": "মাতার নাম",
                    "date_of_birth": date_of_birth.isoformat(),
                    "gender": "M",
                    "present_address": "Dhaka, Bangladesh",
                    "permanent_address": "Dhaka, Bangladesh",
                    "confidence": 1.0,
                }
            return {"matched": False, "reason": "dob_mismatch"}

        # Unknown NID — simulate a successful match in dev
        return {
            "matched": True,
            "nid_number": nid_number,
            "full_name_en": "Test Customer",
            "full_name_bn": "টেস্ট গ্রাহক",
            "fathers_name_en": "Test Father",
            "fathers_name_bn": "পিতার নাম",
            "mothers_name_en": "Test Mother",
            "mothers_name_bn": "মাতার নাম",
            "date_of_birth": date_of_birth.isoformat(),
            "gender": "M",
            "present_address": "Dhaka, Bangladesh",
            "permanent_address": "Dhaka, Bangladesh",
            "confidence": 0.95,
        }

    async def face_match(self, nid_number: str, selfie_storage_key: str) -> dict:
        base_score = random.uniform(70, 98)
        is_matched = base_score >= 75.0
        return {
            "matched": is_matched,
            "similarity_score": round(base_score, 2),
            "threshold": 75.0,
            "nid_number": nid_number,
            "liveness_verified": True,
            "api_version": "mock-v1",
        }

    async def fingerprint_match(
        self, nid_number: str, fingerprint_template: str, finger_position: Optional[str] = None
    ) -> dict:
        return {
            "matched": True,
            "similarity_score": 95.0,
            "threshold": 70.0,
            "nid_number": nid_number,
            "finger_position": finger_position or "right_index",
            "api_version": "mock-v1",
        }


class RealECService(BaseECService):

    async def validate_nid(self, nid_number: str, date_of_birth: date) -> dict:
        raise NotImplementedError(
            "RealECService requires production credentials and Bangladesh EC API access. "
            "Implement POST to settings.EC_API_ENDPOINT/nid-verify with EC_API_KEY auth."
        )

    async def face_match(self, nid_number: str, selfie_storage_key: str) -> dict:
        raise NotImplementedError("RealECService.face_match not yet implemented.")

    async def fingerprint_match(
        self, nid_number: str, fingerprint_template: str, finger_position: Optional[str] = None
    ) -> dict:
        raise NotImplementedError("RealECService.fingerprint_match not yet implemented.")


def get_ec_service() -> BaseECService:
    if settings.EC_PROVIDER == "real":
        return RealECService()
    return MockECService()
