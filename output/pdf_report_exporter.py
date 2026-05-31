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


def export_log_to_pdf(log_entries: list[str], filepath: str, camera_name: str = "",
                      stats_lines: list[str] = None) -> bool:
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

        # Секция статистики
        if stats_lines:
            story.append(Spacer(1, 6 * mm))
            story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
            story.append(Spacer(1, 4 * mm))

            section_style = ParagraphStyle(
                "Section",
                fontName=font_bold,
                fontSize=12,
                leading=16,
                spaceAfter=6,
            )
            stats_head_style = ParagraphStyle(
                "StatsHead",
                fontName=font_bold,
                fontSize=9,
                leading=13,
                spaceAfter=1,
                textColor=colors.HexColor("#1a6a9a"),
            )
            stats_val_style = ParagraphStyle(
                "StatsVal",
                fontName=font_name,
                fontSize=9,
                leading=13,
                spaceAfter=1,
                leftIndent=10,
            )

            story.append(Paragraph("Статистика транспортного потока", section_style))

            for line in stats_lines:
                text = line.strip()
                if not text:
                    story.append(Spacer(1, 3 * mm))
                    continue
                safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                # Строки с "Зона:" или начинающиеся с "Статистика" выделяем
                if text.startswith("Зона:") or text.startswith("Статистика"):
                    story.append(Paragraph(safe, stats_head_style))
                else:
                    story.append(Paragraph(safe, stats_val_style))

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


def export_stats_to_pdf(stats_tracker, source_id, filepath: str, camera_name: str = "") -> bool:
    """
    Экспортирует только статистику транспортного потока (для дальшейшего улучшения бизнес-процессов)
    """
    try:
        font_name, font_bold = _register_fonts()

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            leftMargin=20 * mm, rightMargin=20 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
        )

        title_style = ParagraphStyle("T", fontName=font_bold, fontSize=16, leading=22, spaceAfter=4)
        subtitle_style = ParagraphStyle("S", fontName=font_name, fontSize=10,
                                        textColor=colors.HexColor("#555555"), spaceAfter=10)
        zone_style = ParagraphStyle("Z", fontName=font_bold, fontSize=11, leading=16,
                                    textColor=colors.HexColor("#1a6a9a"), spaceBefore=8, spaceAfter=3)
        row_style = ParagraphStyle("R", fontName=font_name, fontSize=9, leading=14,
                                   leftIndent=12, spaceAfter=1)
        row_bold_style = ParagraphStyle("RB", fontName=font_bold, fontSize=10, leading=14,
                                        leftIndent=12, spaceAfter=1)
        empty_style = ParagraphStyle("E", fontName=font_name, fontSize=9,
                                     textColor=colors.HexColor("#999999"))
        footer_style = ParagraphStyle("F", fontName=font_name, fontSize=8,
                                      textColor=colors.HexColor("#888888"))

        CLASS_LABELS = {"car": "Легковые", "truck": "Грузовые",
                        "bus": "Автобусы", "motorcycle": "Мотоциклы"}

        story = []

        story.append(Paragraph("Статистика транспортного потока", title_style))
        generated_at = datetime.now().strftime("%d.%m.%Y в %H:%M")
        since = stats_tracker.session_start.strftime("%d.%m.%Y %H:%M")
        parts = [f"Сформирован {generated_at}", f"Данные с {since}"]
        if camera_name:
            parts.insert(0, f"Объект: {camera_name}")
        story.append(Paragraph("   |   ".join(parts), subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
        story.append(Spacer(1, 5 * mm))

        fmt = stats_tracker.format_duration
        all_stats = sorted(stats_tracker.get_all_stats(source_id), key=lambda s: s.zone_index)

        if not all_stats or all(s.count() == 0 and s.entered == 0 for s in all_stats):
            story.append(Paragraph("Нет данных о завершенных визитах за текущий сеанс.", empty_style))
        else:
            total_vehicles = 0
            for zs in all_stats:
                sm = zs.summary()
                if sm["total_vehicles"] == 0 and sm["entered"] == 0:
                    continue
                total_vehicles += sm["total_vehicles"]

                safe_name = zs.zone_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                story.append(Paragraph(f"Зона: {safe_name}", zone_style))

                story.append(Paragraph(
                    f"Въехало ТС: {sm['entered']} &nbsp;&nbsp;|&nbsp;&nbsp; Выехало ТС: {sm['exited']}",
                    row_bold_style))
                if sm["conversion"] is not None:
                    story.append(Paragraph(
                        f"Конверсия (выезд/въезд): {sm['conversion'] * 100:.0f}%", row_style))

                story.append(Paragraph(f"Всего транспортных средств: {sm['total_vehicles']}", row_bold_style))

                if sm["avg"] is not None:
                    story.append(Paragraph(f"Среднее время в зоне: {fmt(sm['avg'])}", row_bold_style))
                    story.append(Paragraph(f"Минимальное: {fmt(sm['min'])}", row_style))
                    story.append(Paragraph(f"Максимальное: {fmt(sm['max'])}", row_style))

                for cls, cnt in sm["by_class"].items():
                    label = CLASS_LABELS.get(cls, cls)
                    story.append(Paragraph(f"{label}: {cnt} шт.", row_style))

                story.append(Spacer(1, 3 * mm))

            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#cccccc")))
            story.append(Spacer(1, 3 * mm))
            story.append(Paragraph(f"Итого за смену: {total_vehicles} транспортных средств", row_bold_style))

        story.append(Spacer(1, 8 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#eeeeee")))
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"Отчет сформирован автоматически системой мониторинга", footer_style))

        doc.build(story)
        return True

    except Exception as e:
        print(f"Ошибка экспорта статистики PDF: {e}")
        return False
