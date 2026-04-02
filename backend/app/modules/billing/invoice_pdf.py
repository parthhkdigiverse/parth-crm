# backend/app/modules/billing/invoice_pdf.py
import io
from xhtml2pdf import pisa
from fastapi import HTTPException

def generate_bill_pdf(html_content: str) -> io.BytesIO:
    """
    Converts HTML invoice content to a PDF byte stream using xhtml2pdf.
    """
    # Create a file-like buffer to receive PDF data
    pdf_buffer = io.BytesIO()
    
    # xhtml2pdf logic
    # Note: Modern CSS like Grid/Flexbox might need simple table-based fallback for xhtml2pdf
    # but since the user wants a professional look, we will try to pass the HTML directly.
    # If the layout breaks, we might need a simplified PDF-specific HTML.
    
    # We add a small CSS tweak to ensure xhtml2pdf respects A4 and colors
    pisa_status = pisa.CreatePDF(
        io.StringIO(html_content),
        dest=pdf_buffer
    )
    
    if pisa_status.err:
        raise HTTPException(status_code=500, detail=f"PDF Generation Error: {pisa_status.err}")
    
    pdf_buffer.seek(0)
    return pdf_buffer
