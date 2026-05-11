"""Backwards-compatibility shim — logic moved to app/services/ec_service.py."""
from app.services.ec_service import MockECService

mock_ec_service = MockECService()
