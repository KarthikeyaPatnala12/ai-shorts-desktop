import platform
import subprocess

from backend.app.schemas import HardwareProfile


def detect_hardware_profile() -> HardwareProfile:
    system = platform.system()
    architecture = platform.machine()
    notes: list[str] = []

    if system == "Darwin" and architecture.lower() in {"arm64", "aarch64"}:
        return HardwareProfile(
            platform=system,
            architecture=architecture,
            accelerator="apple-silicon",
            recommended_whisper_device="cpu",
            recommended_compute_type="int8",
            recommended_model="base",
            notes=["Apple Silicon detected. Current faster-whisper backend is configured conservatively for CPU."],
        )

    if _has_nvidia_gpu():
        return HardwareProfile(
            platform=system,
            architecture=architecture,
            accelerator="nvidia-cuda",
            recommended_whisper_device="cuda",
            recommended_compute_type="float16",
            recommended_model="small",
            notes=["NVIDIA GPU detected. CUDA mode is faster but requires compatible CUDA/cuDNN DLLs."],
        )

    notes.append("No supported GPU accelerator detected. CPU int8 is safest.")
    return HardwareProfile(
        platform=system,
        architecture=architecture,
        accelerator="cpu",
        recommended_whisper_device="cpu",
        recommended_compute_type="int8",
        recommended_model="base",
        notes=notes,
    )


def _has_nvidia_gpu() -> bool:
    try:
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=3)
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "GPU" in result.stdout
