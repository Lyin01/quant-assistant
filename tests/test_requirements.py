from pathlib import Path


def test_main_requirements_include_ocr_runtime():
    root = Path(__file__).resolve().parents[1]
    requirements = (root / "requirements.txt").read_text(encoding="utf-8")
    packages = (root / "packages.txt").read_text(encoding="utf-8")

    assert 'opencv-python-headless>=4.8; python_version < "3.13"' in requirements
    assert 'rapidocr-onnxruntime>=1.3; python_version < "3.13"' in requirements
    assert "libgl1" in packages
    assert "libglib2.0-0t64" in packages
