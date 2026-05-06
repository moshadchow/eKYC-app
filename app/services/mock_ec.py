"""
Mock Election Commission (EC) API
Simulates NID validation, face matching, and fingerprint matching.
Replace with real EC API endpoints when available.
"""

import random
from datetime import date
from typing import Optional


class MockNIDRecord:
    def __init__(self, nid: str):
        self.nid_number = nid
        self.full_name_en = "Mohammad Karim"
        self.full_name_bn = "মোহাম্মদ করিম"
        self.fathers_name_en = "Abdul Karim"
        self.fathers_name_bn = "আব্দুল করিম"
        self.mothers_name_en = "Fatema Begum"
        self.mothers_name_bn = "ফাতেমা বেগম"
        self.date_of_birth = date(1990, 5, 15)
        self.gender = "M"
        self.present_address = "House 12, Road 4, Dhanmondi, Dhaka-1205"
        self.permanent_address = "Village: Karimpur, Upazila: Comilla Sadar, Comilla"
        self.photo_url = "https://mock-ec.example.com/photos/nid_photo.jpg"


class MockECService:
    """
    Mock implementation of the Bangladesh Election Commission
    NID verification API (similar to the real EC API).
    """

    # Simulated NID records for testing
    _VALID_NIDS = {
        "1234567890123": {"dob": date(1990, 5, 15), "name": "Mohammad Karim"},
        "9876543210987": {"dob": date(1985, 3, 22), "name": "Fatema Akter"},
        "1111222233334": {"dob": date(1995, 11, 8), "name": "Rahim Uddin"},
    }

    async def validate_nid(
        self,
        nid_number: str,
        date_of_birth: date,
    ) -> dict:
        """
        Validate NID + DOB against EC database.
        Returns NID record data if matched.
        """
        if nid_number in self._VALID_NIDS:
            record = self._VALID_NIDS[nid_number]
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

        # For any unknown NID — simulate a successful match in dev
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

    async def face_match(
        self,
        nid_number: str,
        selfie_storage_key: str,
    ) -> dict:
        """
        Match a live selfie against the face stored in the EC NID database.
        Returns similarity score 0–100.
        """
        # Simulate ~85% pass rate with realistic score distribution
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
        self,
        nid_number: str,
        fingerprint_template: str,
        finger_position: Optional[str] = None,
    ) -> dict:
        """
        Match a captured fingerprint against all 10 fingers stored in EC database.
        """
        base_score = random.uniform(65, 99)
        is_matched = base_score >= 70.0

        return {
            "matched": is_matched,
            "similarity_score": round(base_score, 2),
            "threshold": 70.0,
            "nid_number": nid_number,
            "finger_position": finger_position or "right_index",
            "api_version": "mock-v1",
        }


mock_ec_service = MockECService()
