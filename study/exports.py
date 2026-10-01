"""TXT and PDF export of a study material."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def to_txt(m):
    n = m.notes
    out = [m.topic.upper(), "=" * len(m.topic), "", "SHORT NOTES", n.get("definition", ""), ""]
    out += [f"- {p}" for p in n.get("key_points", [])]
    out += ["", "Important concepts: " + ", ".join(n.get("important_concepts", [])), "", "EXAM QUESTIONS"]
    for i, q in enumerate(m.exam_questions.all(), 1):
        out += [f"Q{i}. [{q.marks} marks] {q.question}", f"Ans: {q.answer}", ""]
    out.append("VIVA QUESTIONS")
    for i, q in enumerate(m.viva_questions.all(), 1):
        out += [f"Q{i}. {q.question}", f"Ans: {q.answer}", ""]
    return "\n".join(out)


def to_pdf(m):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48,
                            title=m.topic)
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], alignment=0, fontSize=22, textColor=colors.HexColor("#1B2BD8"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], spaceBefore=16, textColor=colors.HexColor("#0F1226"))
    body, q = ss["BodyText"], ParagraphStyle("q", parent=ss["BodyText"], fontName="Helvetica-Bold", spaceBefore=6)
    n = m.notes
    s = [Paragraph(escape(m.topic), h1), Paragraph("Short notes", h2), Paragraph(escape(n.get("definition", "")), body)]
    s += [Paragraph("&bull; " + escape(p), body) for p in n.get("key_points", [])]
    s += [Spacer(1, 6), Paragraph("<b>Key concepts:</b> " + escape(", ".join(n.get("important_concepts", []))), body)]
    s.append(Paragraph("Exam questions", h2))
    for i, e in enumerate(m.exam_questions.all(), 1):
        s += [Paragraph(f"Q{i}. ({e.marks} marks) {escape(e.question)}", q), Paragraph(escape(e.answer), body)]
    s.append(Paragraph("Viva questions", h2))
    for i, e in enumerate(m.viva_questions.all(), 1):
        s += [Paragraph(f"Q{i}. {escape(e.question)}", q), Paragraph(escape(e.answer), body)]
    doc.build(s)
    return buf.getvalue()
