import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable


def _register_fonts():
    # Пробуем найти системный шрифт с кириллицей
    candidates = [
        ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        ("C:/Windows/Fonts/calibri.ttf", "C:/Windows/Fonts/calibrib.ttf"),
        ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
    ]
    for regular, bold in candidates:
        if os.path.exists(regular):
            pdfmetrics.registerFont(TTFont("ReportFont", regular))
            if os.path.exists(bold):
                pdfmetrics.registerFont(TTFont("ReportFont-Bold", bold))
            else:
                pdfmetrics.registerFont(TTFont("ReportFont-Bold", regular))
            return "ReportFont", "ReportFont-Bold"

    # Запасной вариант - встроенный Helvetica (самый красивый шрифт на мой взгляд), но не поддерживает кириллицу
    return "Helvetica", "Helvetica-Bold"


def export_log_to_pdf(log_entries: list[str], filepath: str, camera_name: str = "") -> bool:
    """
    :param log_entries: список строк вида "[HH:MM:SS] текст"
    :param filepath: путь к выходному .pdf файлу
    :param camera_name: название камеры или объекта для шапки
    :return:
    """
    try:
        font_name, font_bold = _register_fonts()

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            "Title",
            fontName=font_bold,
            fontSize=16,
            leading=20,
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            "Subtitle",
            fontName=font_name,
            fontSize=10,
            textColor=colors.HexColor("#555555"),
            spaceAfter=10,
        )
        entry_style = ParagraphStyle(
            "Entry",
            fontName=font_name,
            fontSize=9,
            leading=13,
            spaceAfter=1,
        )
        alert_style = ParagraphStyle(
            "Alert",
            fontName=font_bold,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#c0392b"),
            spaceAfter=1,
        )
        info_style = ParagraphStyle(
            "Info",
            fontName=font_name,
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1a6a9a"),
            spaceAfter=1,
        )

        story = []

        story.append(Paragraph("Отчет по событиям видеонаблюдения", title_style))

        generated_at = datetime.now().strftime("%d.%m.%Y в %H:%M")
        subtitle_parts = [f"Сформирован {generated_at}"]
        if camera_name:
            subtitle_parts.append(f"Объект: {camera_name}")
        story.append(Paragraph("   |   ".join(subtitle_parts), subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 6 * mm))

        if not log_entries:
            story.append(Paragraph("Записей в журнале нет", entry_style))
        else:
            for line in log_entries:
                text = line.strip()
                if not text:
                    continue

                # Выбираем стиль по содержимому
                low = text.lower()
                if any(w in low for w in ("тревога", "alert", "нарушение", "зона", "zone")):
                    style = alert_style
                elif any(w in low for w in ("соединение", "подключ", "камера", "запущ", "остановл")):
                    style = info_style
                else:
                    style = entry_style

                # Экранируем символы для движка reportlab
                safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(safe, style))

        story.append(Spacer(1, 8 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 3 * mm))

        # Итоговая строка
        total = len(log_entries)
        alerts = sum(
            1 for l in log_entries
            if any(w in l.lower() for w in ("тревога", "alert", "нарушение", "зона", "zone"))
        )
        summary = ParagraphStyle(
            "Summary",
            fontName=font_name,
            fontSize=8,
            textColor=colors.HexColor("#888888"),
        )
        story.append(Paragraph(
            f"Всего записей: {total}   |   Из них тревог: {alerts}",
            summary
        ))

        doc.build(story)
        return True

    except Exception as e:
        print(f"Ошибка экспорта PDF: {e}")
        return False
