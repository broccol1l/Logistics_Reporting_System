import pandas as pd
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- НАСТРОЙКА ШРИФТА ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "fonts", "arial.ttf")

if os.path.exists(FONT_PATH):
    pdfmetrics.registerFont(TTFont('ArialCustom', FONT_PATH))
    FONT_NAME = 'ArialCustom'
else:
    FONT_NAME = 'Helvetica'


# --- EXCEL GENERATION ---
def create_shift_excel(shift, is_admin=False):
    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)
    data = []

    for d in sorted_deliveries:
        diff = d.weight_fact - d.weight_plan
        row = {
            "Bog'cha": d.kindergarten.name,
            "Mahsulot": d.product.name,
            "Birl.": d.product.unit,
            "Reja": d.weight_plan,
            "Fakt": d.weight_fact,
            "Farq": diff,
            "Narxi": int(d.p_sadik_fact),
            "Summa": int(d.total_price_sadik)
        }
        if is_admin:
            row["Xarid"] = int(d.p_zakup_fact)
            row["Foyda"] = int(d.net_profit)
        data.append(row)

    df = pd.DataFrame(data)
    os.makedirs("temp", exist_ok=True)
    suffix = "ADMIN" if is_admin else "HAYDOVCHI"
    file_path = os.path.join("temp", f"Hisobot_{suffix}_{shift.opened_at.strftime('%d_%m')}_{shift.id}.xlsx")

    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Hisobot', startrow=4)
        ws = writer.sheets['Hisobot']

        ws.cell(row=1, column=1, value=f"{shift.opened_at.strftime('%d.%m.%Y')} SANA UCHUN HISOBOT ({suffix})")
        ws.cell(row=2, column=1, value=f"Haydovchi: {shift.driver.full_name}")
        ws.cell(row=3, column=1, value=f"Telefon: {shift.driver.phone}")

        last_row = len(data) + 6
        total_rev = sum(d.total_price_sadik for d in shift.deliveries)
        fuel = shift.fuel_expense or 0

        other_exp = shift.other_expenses or 0
        other_comment = shift.other_expenses_comment or ""
        total_expenses = fuel + other_exp

        ws.cell(row=last_row, column=1, value="UMUMIY TUSHUM (ВЫРУЧКА):")
        ws.cell(row=last_row, column=2, value=int(total_rev))

        ws.cell(row=last_row + 1, column=1, value="BENZIN XARAJATI:")
        ws.cell(row=last_row + 1, column=2, value=int(fuel))

        if other_exp > 0:
            comment_text = f" ({other_comment})" if other_comment else ""
            ws.cell(row=last_row + 2, column=1, value=f"BOSHQA XARAJATLAR{comment_text}:")
            ws.cell(row=last_row + 2, column=2, value=int(other_exp))
            summary_offset = 3
        else:
            summary_offset = 2

        if is_admin:
            total_cost = sum(d.total_cost_zakup for d in shift.deliveries)
            ws.cell(row=last_row + summary_offset, column=1, value="SOF FOYDA (ЧИСТАЯ ПРИБЫЛЬ):")
            ws.cell(row=last_row + summary_offset, column=2, value=int(total_rev - total_cost - total_expenses))
        else:
            ws.cell(row=last_row + summary_offset, column=1, value="TOPSHIRILADIGAN JAMI SUMMA:")
            ws.cell(row=last_row + summary_offset, column=2, value=int(total_rev - total_expenses))

        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 20

    return file_path


# --- PDF GENERATION ---
def create_shift_pdf(shift, is_admin=False):
    os.makedirs("temp", exist_ok=True)
    suffix = "ADMIN" if is_admin else "HAYDOVCHI"
    file_path = os.path.join("temp", f"Hisobot_{suffix}_{shift.id}.pdf")

    doc = SimpleDocTemplate(file_path, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)

    cell_style = ParagraphStyle('Cell', fontName=FONT_NAME, fontSize=7, leading=9, alignment=1)
    name_style = ParagraphStyle('Name', fontName=FONT_NAME, fontSize=7, leading=9, alignment=0)

    elements = []

    header_text = f"<b>{shift.opened_at.strftime('%d.%m.%Y')} SANA UCHUN HISOBOT ({suffix})</b><br/>"
    header_text += f"Haydovchi: {shift.driver.full_name} | Tel: {shift.driver.phone}"
    elements.append(Paragraph(header_text, ParagraphStyle('H', fontName=FONT_NAME, fontSize=10)))
    elements.append(Spacer(1, 15))

    header = ["Obyekt", "Mahsulot", "Birl.", "Reja", "Fakt", "Farq", "Narxi", "Summa"]
    if is_admin:
        header += ["Xarid", "Foyda"]

    table_data = [[Paragraph(h, cell_style) for h in header]]
    sorted_deliveries = sorted(shift.deliveries, key=lambda x: x.id)

    for d in sorted_deliveries:
        diff = d.weight_fact - d.weight_plan
        row = [
            Paragraph(d.kindergarten.name, name_style),
            Paragraph(d.product.name, name_style),
            Paragraph(d.product.unit, cell_style),
            Paragraph(str(d.weight_plan), cell_style),
            Paragraph(str(d.weight_fact), cell_style),
            Paragraph(f"{diff:+.2f}", cell_style),
            Paragraph(f"{d.p_sadik_fact:,.0f}", cell_style),
            Paragraph(f"{d.total_price_sadik:,.0f}", cell_style)
        ]
        if is_admin:
            row += [
                Paragraph(f"{d.p_zakup_fact:,.0f}", cell_style),
                Paragraph(f"{d.net_profit:,.0f}", cell_style)
            ]
        table_data.append(row)

    if not is_admin:
        col_widths = [115, 100, 30, 45, 45, 45, 60, 70]
    else:
        col_widths = [85, 80, 25, 40, 40, 40, 50, 60, 50, 60]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4F4F4F")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, -1), FONT_NAME),
    ]))

    elements.append(t)
    elements.append(Spacer(1, 15))

    total_rev = sum(d.total_price_sadik for d in shift.deliveries)
    fuel = shift.fuel_expense or 0
    other_exp = shift.other_expenses or 0
    other_comment = shift.other_expenses_comment or ""

    total_expenses = fuel + other_exp

    res_text = f"TUSHUM: <b>{total_rev:,.0f}</b> | BENZIN: <b>{fuel:,.0f}</b>"

    if other_exp > 0:
        comment_str = f" ({other_comment})" if other_comment else ""
        res_text += f" | BOSHQA: <b>{other_exp:,.0f}</b>{comment_str}"

    if is_admin:
        total_cost = sum(d.total_cost_zakup for d in shift.deliveries)
        final_profit = total_rev - total_cost - total_expenses
        res_text += f"<br/>📈 <b>SOF FOYDA: {final_profit:,.0f} so'm</b>"
    else:
        final_total = total_rev - total_expenses
        res_text += f"<br/>💵 <b>JAMI: {final_total:,.0f} so'm</b>"

    elements.append(Paragraph(res_text, ParagraphStyle('S', fontName=FONT_NAME, fontSize=9, leading=12)))

    doc.build(elements)
    return file_path