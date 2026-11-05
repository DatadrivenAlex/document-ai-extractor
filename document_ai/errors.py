"""Errors raised by the extractor."""


class DocumentAIError(Exception):
    """Base error for extraction, generation, and provider setup."""


class UnsupportedFileTypeError(DocumentAIError):
    """The file extension is not a PDF or a supported image."""


class TesseractNotAvailableError(DocumentAIError):
    """An image was submitted but the Tesseract binary is not installed."""


class LLMProviderError(DocumentAIError):
    """An LLM provider was requested but could not run."""
