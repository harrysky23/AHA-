"""One bounded PDF extraction subprocess; input/output are pipes, never files."""
import io
import json
import logging
import sys

MAX_PAGES = 20
MAX_CHARACTERS = 12_000
MAX_PAGE_STREAM = 2_000_000


def extract(data: bytes) -> dict:
    from pypdf import PdfReader, overwrite_configuration
    # Tighten pypdf's decompression limit for this small PoC, including font streams.
    overwrite_configuration(zlib_maximum_output_length=MAX_PAGE_STREAM,
                            array_based_stream_maximum_output_length=MAX_PAGE_STREAM,
                            lzw_maximum_output_length=MAX_PAGE_STREAM,
                            run_length_maximum_output_length=MAX_PAGE_STREAM,
                            brotli_maximum_output_length=MAX_PAGE_STREAM,
                            maximum_declared_stream_length=5 * 1024 * 1024,
                            stream_decoding_work_maximum_length=8 * 1024 * 1024,
                            xform_maximum_invocations_per_extraction=100)
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    reader = PdfReader(io.BytesIO(data), strict=True, root_object_recovery_limit=1000, xref_stream_maximum_entries=100_000)
    if reader.is_encrypted:
        return {"error": "encrypted_pdf"}
    count = len(reader.pages)
    if count < 1 or count > MAX_PAGES:
        return {"error": "pdf_page_limit"}
    pages, empty, remaining, truncated = [], [], MAX_CHARACTERS, False
    for number, page in enumerate(reader.pages, 1):
        content = page.get_contents()
        if content is not None and len(content.get_data()) > MAX_PAGE_STREAM:
            return {"error": "pdf_complexity"}
        text = (page.extract_text() or "").replace("\x00", "").strip()
        if not text:
            empty.append(number)
            continue
        if len(text) > remaining:
            text = text[:remaining]
            truncated = True
        if text:
            pages.append({"page": number, "text": text})
            remaining -= len(text)
        if remaining == 0:
            truncated = truncated or number < count
            break
    return {"pages": pages, "page_count": count, "empty_pages": empty, "truncated": truncated,
            "extracted_characters": sum(len(p["text"]) for p in pages)}


def main():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024,) * 2)
    except (ImportError, OSError, ValueError):
        pass
    try:
        result = extract(sys.stdin.buffer.read(5 * 1024 * 1024 + 1))
    except MemoryError:
        result = {"error": "pdf_complexity"}
    except Exception:
        # Never echo parser messages, document text or file paths to logs.
        result = {"error": "invalid_pdf"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
