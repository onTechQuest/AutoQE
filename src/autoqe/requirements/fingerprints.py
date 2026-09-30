import hashlib
import unicodedata


def normalize_markdown(content: str) -> str:
    normalized = unicodedata.normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in normalized.split("\n")]
    return "\n".join(lines).strip() + "\n"


def content_fingerprint(content: str) -> str:
    normalized = normalize_markdown(content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()