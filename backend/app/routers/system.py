from fastapi import APIRouter

from backend.app.schemas import HardwareProfile, LanguageProfile
from backend.app.services.hardware import detect_hardware_profile
from backend.app.services.language_profiles import list_language_profiles

router = APIRouter()


@router.get("/system/profile", response_model=HardwareProfile)
def get_system_profile() -> HardwareProfile:
    return detect_hardware_profile()


@router.get("/languages", response_model=list[LanguageProfile])
def get_languages() -> list[LanguageProfile]:
    return list_language_profiles()
