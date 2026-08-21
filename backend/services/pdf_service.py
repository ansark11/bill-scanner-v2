import io
import pdfplumber


def extract_pdf_text(attachment_data: bytes) -> str:
    text_parts = []
    with pdfplumber.open(io.BytesIO(attachment_data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
    return "\n".join(text_parts)
