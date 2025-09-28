from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import LETTER
from pathlib import Path

def render_t1_pdf(path: str, fields: dict) -> str:
  p = Path(path)
  c = canvas.Canvas(str(p), pagesize=LETTER)
  c.setFont("Helvetica", 10)
  y = 750
  for k, v in fields.items():
    c.drawString(72, y, f"{k}: {v}")
    y -= 14
  c.showPage()
  c.save()
  return str(p)
