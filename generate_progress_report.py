"""Generate the end-semester progress report as a styled DOCX.

Run from the project directory with:
    .venv\\Scripts\\python.exe generate_progress_report.py
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.enum.style import WD_STYLE_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Inches, Pt, RGBColor


BASE_DIR = Path(__file__).resolve().parent
OUTPUT = BASE_DIR / "EdgeVision_Progress_Report_November_2026.docx"

NAVY = "152638"
INK = "203445"
MUTED = "60758B"
TEAL = "159A83"
MINT = "DDF5EE"
BLUE = "E8F0FB"
AMBER = "FFF1D9"
RED = "FBE5E8"
LILAC = "EEE9FA"
LIGHT = "F4F7FA"
GRID = "D7E0E8"
WHITE = "FFFFFF"


def shade(cell, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    element = properties.find(qn("w:shd"))
    if element is None:
        element = OxmlElement("w:shd")
        properties.append(element)
    element.set(qn("w:fill"), fill)


def cell_margins(cell, top=100, start=120, bottom=100, end=120) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for key, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = margins.find(qn(f"w:{key}"))
        if node is None:
            node = OxmlElement(f"w:{key}")
            margins.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def cant_split(row) -> None:
    properties = row._tr.get_or_add_trPr()
    properties.append(OxmlElement("w:cantSplit"))


def set_cell_text(cell, text, *, bold=False, color=INK, size=9, align=None) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(0)
    if align is not None:
        paragraph.alignment = align
    run = paragraph.add_run(str(text))
    run.bold = bold
    run.font.name = "Aptos"
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    cell_margins(cell)


def set_column_widths(table, widths) -> None:
    for row in table.rows:
        for index, width in enumerate(widths):
            row.cells[index].width = Inches(width)


def add_table(doc, headers, rows, *, widths=None, header_fill=NAVY, font_size=8.5,
              first_column_bold=False, row_fills=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        set_cell_text(table.rows[0].cells[index], header, bold=True, color=WHITE, size=8.5)
        shade(table.rows[0].cells[index], header_fill)
    cant_split(table.rows[0])
    for row_index, values in enumerate(rows):
        row = table.add_row()
        cant_split(row)
        fill = (row_fills or {}).get(row_index, WHITE if row_index % 2 == 0 else LIGHT)
        for index, value in enumerate(values):
            set_cell_text(row.cells[index], value, bold=first_column_bold and index == 0,
                          size=font_size)
            shade(row.cells[index], fill)
    if widths:
        set_column_widths(table, widths)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_field(paragraph, instruction: str) -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    paragraph._p.append(begin)
    paragraph._p.append(text)
    paragraph._p.append(separate)
    paragraph._p.append(end)


def add_hyperlink(paragraph, text: str, url: str) -> None:
    relationship = paragraph.part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship)
    run = OxmlElement("w:r")
    properties = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "167A9B")
    properties.append(color)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    properties.append(underline)
    run.append(properties)
    text_node = OxmlElement("w:t")
    text_node.text = text
    run.append(text_node)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def add_bullet(doc, text: str, level=0, color=INK) -> None:
    paragraph = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    paragraph.paragraph_format.space_after = Pt(3)
    paragraph.paragraph_format.left_indent = Inches(0.24 + level * 0.2)
    run = paragraph.add_run(text)
    run.font.name = "Aptos"
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor.from_string(color)


def add_number(doc, text: str) -> None:
    paragraph = doc.add_paragraph(style="List Number")
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(text)
    run.font.name = "Aptos"
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor.from_string(INK)


def add_code(doc, text: str) -> None:
    paragraph = doc.add_paragraph(style="Code Block")
    paragraph.add_run(text)


def add_callout(doc, title: str, text: str, fill=BLUE, accent=TEAL) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    shade(cell, fill)
    cell_margins(cell, top=140, start=170, bottom=140, end=170)
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_after = Pt(4)
    run = paragraph.add_run(title)
    run.bold = True
    run.font.name = "Aptos Display"
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor.from_string(accent)
    paragraph = cell.add_paragraph()
    paragraph.paragraph_format.space_after = Pt(0)
    run = paragraph.add_run(text)
    run.font.name = "Aptos"
    run.font.size = Pt(9.2)
    run.font.color.rgb = RGBColor.from_string(INK)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_section_title(doc, number: str, title: str, subtitle: str | None = None) -> None:
    paragraph = doc.add_paragraph(style="Heading 1")
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(f"{number}  {title}")
    run.font.color.rgb = RGBColor.from_string(NAVY)
    if subtitle:
        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(9)
        run = paragraph.add_run(subtitle)
        run.italic = True
        run.font.name = "Aptos"
        run.font.size = Pt(9.5)
        run.font.color.rgb = RGBColor.from_string(MUTED)


def add_subtitle(doc, title: str) -> None:
    paragraph = doc.add_paragraph(style="Heading 2")
    paragraph.paragraph_format.keep_with_next = True
    paragraph.add_run(title)


def add_body(doc, text: str, *, bold_prefix: str | None = None) -> None:
    paragraph = doc.add_paragraph(style="Body Text")
    paragraph.paragraph_format.space_after = Pt(6)
    paragraph.paragraph_format.line_spacing = 1.12
    if bold_prefix and text.startswith(bold_prefix):
        first = paragraph.add_run(bold_prefix)
        first.bold = True
        rest = paragraph.add_run(text[len(bold_prefix):])
        for run in (first, rest):
            run.font.name = "Aptos"
            run.font.size = Pt(9.7)
            run.font.color.rgb = RGBColor.from_string(INK)
    else:
        run = paragraph.add_run(text)
        run.font.name = "Aptos"
        run.font.size = Pt(9.7)
        run.font.color.rgb = RGBColor.from_string(INK)


def setup_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(1.7)
    section.bottom_margin = Cm(1.6)
    section.left_margin = Cm(1.75)
    section.right_margin = Cm(1.75)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Aptos"
    normal.font.size = Pt(9.7)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal.paragraph_format.space_after = Pt(5)

    body = styles["Body Text"]
    body.font.name = "Aptos"
    body.font.size = Pt(9.7)
    body.font.color.rgb = RGBColor.from_string(INK)

    for name, size, color in (("Heading 1", 16, NAVY), ("Heading 2", 11.5, TEAL), ("Heading 3", 10, NAVY)):
        style = styles[name]
        style.font.name = "Aptos Display"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style.paragraph_format.space_before = Pt(10 if name != "Heading 1" else 14)
        style.paragraph_format.space_after = Pt(5)

    if "Code Block" not in styles:
        code = styles.add_style("Code Block", WD_STYLE_TYPE.PARAGRAPH)
    else:
        code = styles["Code Block"]
    code.font.name = "Cascadia Mono"
    code.font.size = Pt(8.2)
    code.font.color.rgb = RGBColor.from_string("DCEEF4")
    code.paragraph_format.left_indent = Inches(0.15)
    code.paragraph_format.right_indent = Inches(0.15)
    code.paragraph_format.space_before = Pt(4)
    code.paragraph_format.space_after = Pt(8)

    # Header and footer are deliberately restrained so the report remains formal.
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    header.paragraph_format.space_after = Pt(2)
    run = header.add_run("EDGEVISION  |  MINOR PROJECT PROGRESS REPORT")
    run.font.name = "Aptos"
    run.font.size = Pt(7.5)
    run.font.bold = True
    run.font.color.rgb = RGBColor.from_string(MUTED)
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.space_before = Pt(3)
    run = footer.add_run("ECE 5th Semester  •  November 2026 target  •  Page ")
    run.font.name = "Aptos"
    run.font.size = Pt(7.5)
    run.font.color.rgb = RGBColor.from_string(MUTED)
    add_field(footer, "PAGE")
    return doc


def build_report() -> Path:
    doc = setup_document()
    doc.core_properties.title = "EdgeVision Progress Report — November 2026"
    doc.core_properties.subject = "AI-Powered Smart Video Doorbell and Automated Access Sentry"
    doc.core_properties.author = "EdgeVision Minor Project Team"
    doc.core_properties.comments = "Generated from the implemented software prototype."

    # Cover page
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(55)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run("ECE 5TH SEMESTER  |  MINOR PROJECT")
    run.bold = True
    run.font.name = "Aptos"
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor.from_string(TEAL)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(14)
    p.paragraph_format.space_after = Pt(5)
    run = p.add_run("PROGRESS REPORT")
    run.bold = True
    run.font.name = "Aptos Display"
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor.from_string(MUTED)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    run = p.add_run("AI-Powered Smart Video Doorbell\n& Automated Access Sentry")
    run.bold = True
    run.font.name = "Aptos Display"
    run.font.size = Pt(27)
    run.font.color.rgb = RGBColor.from_string(NAVY)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(24)
    run = p.add_run("Edge-Vision Smart Surveillance and Access Control System")
    run.font.name = "Aptos"
    run.font.size = Pt(13)
    run.font.color.rgb = RGBColor.from_string(TEAL)

    add_callout(doc, "REPORT PURPOSE", "This report records the progress of the Software-in-the-Loop prototype, identifies the hardware and firmware work that remains, and defines the concrete plan and expected conclusion for the semester ending 30 November 2026.", fill=MINT, accent=TEAL)

    metadata = [
        ("Project type", "ECE 5th Semester Minor Project"),
        ("System concept", "AI-powered smart video doorbell and access sentry"),
        ("Current reporting date", "06 October 2026"),
        ("Planned semester conclusion", "30 November 2026"),
        ("Prototype location", r"C:\Users\aayus\working-ly\edge-vision-sitl"),
        ("Prepared for", "Project review / viva progress evaluation"),
    ]
    table = doc.add_table(rows=0, cols=2)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.style = "Table Grid"
    for label, value in metadata:
        row = table.add_row()
        cant_split(row)
        set_cell_text(row.cells[0], label, bold=True, color=MUTED, size=9)
        shade(row.cells[0], LIGHT)
        set_cell_text(row.cells[1], value, color=INK, size=9)
        shade(row.cells[1], WHITE)
    set_column_widths(table, [1.7, 4.8])

    doc.add_paragraph().paragraph_format.space_after = Pt(3)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(18)
    run = p.add_run("Student: ________________________________    Guide: ________________________________")
    run.font.name = "Aptos"
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor.from_string(MUTED)
    doc.add_page_break()

    # Contents
    add_section_title(doc, "CONTENTS", "Report structure", "The field-based hardware work is intentionally separated from the completed SITL work.")
    toc = doc.add_paragraph()
    toc.paragraph_format.space_after = Pt(10)
    add_field(toc, 'TOC \\o "1-3" \\h \\z \\u')
    add_callout(doc, "DOCUMENT NOTE", "Open the DOCX in Microsoft Word and choose Update Field on the contents block if page numbers are not refreshed automatically.", fill=AMBER, accent="9A6617")
    doc.add_page_break()

    # 1 Executive summary
    add_section_title(doc, "1", "Executive summary", "Current position: software prototype is functionally complete; physical edge validation is the principal remaining milestone.")
    add_body(doc, "The project is being developed as an AI-Powered Smart Video Doorbell and Automated Access Sentry. The intended final system uses a PIR sensor to detect a person near a door, wakes or activates an ESP32-CAM, sends image frames over Wi-Fi to an AI service, makes an access decision, actuates a relay for an authorized owner, and sends an evidence-backed alert to an owner dashboard for relatives or unknown visitors.")
    add_body(doc, "The completed Software-in-the-Loop prototype proves the end-to-end interaction without requiring procured hardware. It contains a selectable house-and-person simulation, a PIR detection zone, a doorbell, a gate boundary, two synchronized dashboards, owner approval, occupancy tracking, persistent event history, a real laptop-camera mode, OpenCV Haar/LBPH face recognition, managed owner/relative face IDs, MJPEG video, WebSocket events, and a mock timed relay.")
    add_body(doc, "The next immediate phase is to connect the same backend interfaces to the physical ESP32-CAM, HC-SR501 PIR sensor, and relay assembly. The software has a hardware abstraction boundary and configured ESP32/relay contracts, but physical interrupt wake-up, OV2640/PSRAM/DMA behavior, electrical isolation, and bench measurements are not claimed as completed until the components are available and tested.")
    add_table(doc, ["Area", "Status at this report", "Evidence / interpretation"], [
        ("Interactive house SITL", "COMPLETED", "Two-dashboard visitor journey with gate collision, PIR zone, bell, approval, entry/exit and occupancy."),
        ("Owner monitoring", "COMPLETED", "Live inbox, visitor images, approval controls, household data, emergency links and persistent logs."),
        ("Laptop-camera pipeline", "IMPLEMENTED", "Webcam selection, VGA capture, MOG2 motion, Haar/LBPH, snapshots and mock relay; live device selection remains a demo-day check."),
        ("Owner/relative face IDs", "COMPLETED", "Role-aware FaceRegistry, upload/capture/delete APIs, role overlays and relative approval workflow."),
        ("ESP32-CAM/PIR/relay bench", "PENDING HARDWARE", "HAL and HTTP/serial relay contracts are prepared; wiring, firmware ISR and physical measurements remain."),
        ("Indicative overall progress", "~65%", "Software/SITL scope is substantially complete; hardware integration and final validation account for the remaining work."),
    ], widths=[1.55, 1.35, 3.6], first_column_bold=True)

    # 2 problem/objectives
    add_section_title(doc, "2", "Project problem and objectives")
    add_body(doc, "A conventional surveillance system continuously captures, processes and transmits video even when no person is near the door. This increases energy use, network traffic, storage requirements and operator fatigue. The proposed sentry follows an event-driven edge/cloud split: low-cost sensing at the doorway, computationally heavier vision on a server, and a human approval path when identity is not sufficient for automatic access.")
    add_subtitle(doc, "Primary objectives")
    for item in [
        "Detect an approaching person through PIR motion rather than treating the camera as a permanently active recorder.",
        "Capture or stream frames from an ESP32-CAM-class source and process them with lightweight computer vision or a future embedding model.",
        "Automatically grant access to a registered owner, while requiring owner approval for relatives and unknown visitors.",
        "Keep the gate locked for an unknown visitor, preserve a timestamped evidence snapshot and raise a visible owner alert.",
        "Provide a live dashboard that explains the decision, hardware status, occupancy and audit trail during a viva demonstration.",
        "Keep the hardware/software boundary replaceable so laptop webcam and mock relay can be replaced by ESP32-CAM and physical GPIO/serial control without rewriting the access policy.",
    ]:
        add_bullet(doc, item)
    add_callout(doc, "ENGINEERING PRINCIPLE", "The project is not only a face-recognition demo. Its core contribution is an event-driven access-control chain: sensor interrupt → camera activation → identity decision → safe actuation or owner escalation → durable audit evidence.", fill=BLUE, accent=TEAL)

    # 3 architecture
    add_section_title(doc, "3", "Target architecture and current implementation")
    add_subtitle(doc, "Target physical/cloud data path")
    add_code(doc, "[HC-SR501 PIR] -- GPIO interrupt --> [ESP32-CAM / OV2640]\n        |                                      |\n        |                                      +-- Wi-Fi MJPEG / JPEG frames --> [FastAPI + OpenCV / Face model]\n        |                                                                         |\n        +-- wake / active window                                                   +-- known owner --> [Relay / lock]\n                                                                                   +-- relative --> [Owner approval]\n                                                                                   +-- unknown --> [Snapshot + alert + locked state]\n                                                                                                      |\n                                                                                           [Owner monitoring dashboard]")
    add_subtitle(doc, "Current SITL architecture")
    add_table(doc, ["Layer", "Implemented component", "Current behavior"], [
        ("Experience layer", "`/simulation` and `/owner`", "Two connected dashboards share one authoritative server-side house state over WebSockets."),
        ("Real-camera layer", "`/camera`", "Starts a selected laptop camera on demand; displays MJPEG frames and overlays identity/role decisions."),
        ("Capture abstraction", "`CameraStream`, `OpenCVSource`", "Supports webcam index, synthetic test source and ESP32 HTTP stream configuration."),
        ("Motion layer", "`MotionDetector`", "MOG2 background subtraction with warm-up, shadow rejection, morphology and confirmation frames."),
        ("Vision layer", "`FaceEngine`", "Haar frontal-face detection and OpenCV-contrib LBPH matching; score is explicitly a heuristic, not probability."),
        ("Identity layer", "`FaceRegistry`", "Persistent IDs with name, reference image, owner/relative role, timestamp and safe deletion."),
        ("Policy layer", "`SurveillanceController` / `SimulationEngine`", "Owners auto-grant; relatives can wait for owner approval; unknown faces remain denied."),
        ("Actuation layer", "`TimedRelay`, mock/HTTP/serial drivers", "Mock relay logs GPIO 12 HIGH/LOW and relocks independently with a watchdog."),
        ("Storage layer", "SQLite + JSON sidecar", "Simulation events, camera audit events, captures, occupancy and face-ID metadata survive restarts."),
    ], widths=[1.2, 1.8, 3.5], first_column_bold=True, font_size=8.2)
    add_body(doc, "The present dashboard is a modular FastAPI-served HTML/CSS/JavaScript application rather than a React build. It provides the required monitoring and control behavior in the prototype. A React/Tailwind migration can be added after physical integration if the department specifically requires a React deliverable; it is not necessary to prove the embedded-to-server access flow.")

    # 4 completed progress
    add_section_title(doc, "4", "Progress completed to date")
    add_subtitle(doc, "4.1 Software foundation and server")
    for item in [
        "FastAPI application with lifecycle-managed background workers, REST routes, MJPEG streaming and WebSocket broadcast.",
        "Configuration through `.env` and validated Pydantic settings, including server address, camera source, frame rate, motion thresholds, approval timeout and relay backend.",
        "Bounded WebSocket queues and reconnection-aware dashboards so a slow browser does not block camera capture or relay timing.",
        "Optional API-key protection for control, enrollment, logs, snapshots and WebSocket access; default server binds to loopback.",
    ]:
        add_bullet(doc, item)
    add_subtitle(doc, "4.2 House simulation and owner workflow")
    for item in [
        "Eight fictional selectable people: owners/residents, relatives and unknown visitors.",
        "Rendered house with living spaces, approach path, gate, doorbell, PIR radius, moving visitor and occupant markers.",
        "Arrow-key and arrow-button movement with server-side collision rules; locked gate cannot be bypassed.",
        "Owner bell ring automatically grants access; relative/unknown ring creates a pending request and illustrated capture for the owner.",
        "Entry is recorded only after the person crosses the unlocked doorway; approval alone does not falsely add someone to occupancy.",
        "Persistent occupancy, last-entry record, pending-request lifecycle, approval timeout, cancellation and exit events.",
    ]:
        add_bullet(doc, item)
    add_subtitle(doc, "4.3 Owner monitoring dashboard")
    for item in [
        "Doorbell inbox with image, relationship label, time, gate status, Unlock & allow and Keep locked controls.",
        "Live occupancy count, residents/guests currently home, last person to enter and fictional household profiles.",
        "PIR, recognition and relay indicators, auto-lock timer, event history filters, older-event pagination and phone shortcuts for police 100 / ambulance 108.",
        "Responsive desktop/mobile layouts tested through real browser automation.",
    ]:
        add_bullet(doc, item)
    add_subtitle(doc, "4.4 Laptop-camera computer-vision path")
    for item in [
        "On-demand device index selection solves the virtual-camera/Smart Connect problem without forcing the simulation to open a webcam.",
        "VGA 640×480 capture target and 15–20 FPS validation range; current default is 18 FPS.",
        "MOG2 software motion trigger plus manual PIR trigger; recognition begins only during the analysis window.",
        "Haar detection plus LBPH matching with three-frame confirmation. Authorized owners receive green overlay; relatives receive a gold role overlay; unknown faces receive red intruder overlay.",
        "JPEG snapshots for camera decisions and server-side audit records.",
    ]:
        add_bullet(doc, item)
    add_subtitle(doc, "4.5 Face-ID management")
    add_table(doc, ["Capability", "Completed behavior"], [
        ("Register", "Owner dashboard accepts a name, role and uploaded JPEG/PNG with exactly one detected face."),
        ("Capture", "Current webcam frame can be captured directly as a reference after camera start."),
        ("Role policy", "Owner/resident auto-unlocks; relative requires owner approval; same name cannot be assigned conflicting roles."),
        ("Model reload", "LBPH model is rebuilt after add/remove without restarting the server."),
        ("Persistence", "Reference images remain in `authorized_faces/`; metadata is stored in `data/face_registry.json`."),
        ("Removal", "Owner can delete an individual reference; remaining references for the same person continue to work."),
    ], widths=[1.45, 5.05], first_column_bold=True)

    # 5 validation
    add_section_title(doc, "5", "Verification and current evidence")
    add_body(doc, "The software prototype has been exercised with unit, integration, runtime and browser-level tests. The test suite uses temporary databases and synthetic/scripted inputs where physical hardware is unavailable; it does not claim that an actual ESP32-CAM, HC-SR501 or relay has already been validated.")
    add_table(doc, ["Verification group", "Result", "What was checked"], [
        ("Automated suite", "43 passed", "Full project suite including simulation, API, vision, controller, runtime, browser and owner Face-ID tests."),
        ("Vision", "Passed", "Haar face detection, LBPH reference matching, unknown-face rejection, overlays and image validation."),
        ("Camera API", "Passed", "Lazy start, device selection, stop/release, MJPEG availability and current-frame face-ID capture."),
        ("Owner approval", "Passed", "Recognized relative enters ACCESS_PENDING, owner approves/denies, relay and audit update correctly."),
        ("Simulation journey", "Passed", "Owner auto-grant, relative approval, unknown denial, physical doorway collision and occupancy update."),
        ("Browser UI", "Passed", "Two-tab workflow, face-ID management, desktop/mobile layout, live WebSocket and image loading."),
        ("Physical hardware", "Not yet measured", "Procurement/bench phase remains: GPIO interrupt, PSRAM/DMA behavior, actual stream latency, relay current and electrical isolation."),
    ], widths=[1.45, 1.1, 3.95], first_column_bold=True)
    add_callout(doc, "INTERPRETATION OF THE 43 TESTS", "The result establishes software correctness and repeatable SITL behavior. It is evidence for the server, dashboard, policy and recognition prototype—not a substitute for hardware-in-the-loop measurements or a security certification.", fill=AMBER, accent="9A6617")

    # 6 immediate plan
    add_section_title(doc, "6", "What will be done as soon as possible")
    add_body(doc, "The next work is intentionally ordered to reduce risk early: first freeze a reproducible demonstration, then make the physical device produce a trustworthy frame and interrupt, then connect the already-tested server and policy layers.")
    add_table(doc, ["Priority", "Immediate task", "Acceptance evidence"], [
        ("P0", "Run the laptop-camera demo on the target laptop; enumerate camera indices and document the correct built-in webcam index.", "Recorded camera index, live 640×480 feed, measured FPS and a short owner/relative/unknown demo video or screenshots."),
        ("P0", "Register at least one owner and one relative using the owner dashboard; tune LBPH threshold under expected room lighting.", "Owner auto-grant, relative approval card, unknown denial, false-match observations and chosen threshold recorded."),
        ("P1", "Procure and wire ESP32-CAM, HC-SR501 and relay/LED test load on a safe low-voltage bench.", "Wiring photograph, pin map, measured supply voltage/current and relay state table."),
        ("P1", "Implement ESP32 firmware: PIR GPIO interrupt, wake/active window, camera init, PSRAM frame buffers, Wi-Fi reconnect and MJPEG endpoint.", "ESP32 stream URL produces frames; serial log proves PIR interrupt and active capture window."),
        ("P1", "Connect the backend to the ESP32 stream using `MOCK_MODE=false` and `ESP32_STREAM_URL`.", "Server receives real frames, dashboard shows live source as ESP32-CAM and camera failure is visible."),
        ("P1", "Implement/validate the relay gateway contract over HTTP or serial; keep server-side and device-side auto-relock.", "Known owner unlocks the low-voltage test load; denied visitor never energizes relay; timeout returns to locked."),
        ("P2", "Run end-to-end hardware scenarios and collect latency/reliability data.", "Timing sheet for PIR→frame, frame→decision, decision→relay, stream FPS, reconnect behavior and 20+ repeated trials."),
        ("P2", "Prepare final viva material and freeze the report/demo path by 30 November.", "Final report, architecture diagram, pin table, test matrix, limitations, screenshots and fallback SITL demo."),
    ], widths=[0.55, 3.05, 2.9], first_column_bold=True, font_size=8.2)

    add_subtitle(doc, "Hardware integration checklist")
    for item in [
        "Confirm ESP32-CAM board variant, camera pin map, PSRAM availability and stable 5 V / 3.3 V power rails.",
        "Connect HC-SR501 output to a documented interrupt-capable GPIO; validate logic level and debounce/retrigger timing.",
        "Use an optocoupler or transistor driver, flyback protection and a separate suitable supply for the relay/lock load; do not drive an inductive load directly from an ESP32 GPIO.",
        "Use a green LED or low-voltage lamp as the first relay load; postpone any mains-connected load until supervised electrical review.",
        "Record the ESP32 stream URL and relay endpoint in `.env`; keep a software fallback for viva day if Wi-Fi or procurement fails.",
    ]:
        add_bullet(doc, item)

    # 7 schedule
    add_section_title(doc, "7", "Plan to semester end — 30 November 2026")
    add_table(doc, ["Period", "Work package", "Expected output"], [
        ("06–12 Oct", "SITL freeze and laptop camera validation", "Stable demonstration, correct camera index, owner/relative references, baseline metrics and known limitations."),
        ("13–19 Oct", "ESP32-CAM firmware and PIR interrupt", "PIR event wakes/activates camera, OV2640 frame capture and first local MJPEG stream."),
        ("20–26 Oct", "Relay/LED bench and hardware safety", "Documented pin map, driver circuit, opto/flyback protection, locked/unlocked measurements."),
        ("27 Oct–02 Nov", "Server-to-ESP32 integration", "Real ESP32 source selected through HAL; frame and relay contracts validated."),
        ("03–09 Nov", "AI/policy tuning", "Known owner, registered relative approval, unknown alert and snapshot paths tested in real lighting."),
        ("10–16 Nov", "Reliability and security trials", "Reconnect tests, relay timeout tests, audit persistence, API-key check, repeated scenario matrix."),
        ("17–23 Nov", "Demonstration and documentation", "Viva script, architecture/pin diagrams, measurements, screenshots and fallback plan."),
        ("24–30 Nov", "Final freeze and conclusion", "Final code/report, hardware/SITL demonstration, limitations and future-work statement."),
    ], widths=[1.2, 2.35, 2.95], first_column_bold=True)
    add_callout(doc, "FALLBACK PLAN", "If procurement or hardware debugging slips beyond the planned window, the project will still conclude with the verified SITL + laptop-camera prototype, a documented ESP32/PIR/relay interface, measured software performance, and a clearly labelled hardware-integration plan. This preserves a complete demonstrable software outcome without misrepresenting unfinished hardware tests.", fill=BLUE, accent=TEAL)

    # 8 final deliverables
    add_section_title(doc, "8", "What will be concluded at the end of the semester")
    add_body(doc, "By 30 November 2026, the project will conclude with a validated event-driven smart-door access architecture and a defensible boundary between completed evidence and future enhancement. The final result is expected to demonstrate the following:")
    add_table(doc, ["Final conclusion", "Definition of done"], [
        ("Event-driven operation", "The system waits for a PIR event and activates/analyses the camera window instead of treating continuous heavy processing as the default."),
        ("Edge/cloud partition", "ESP32-CAM handles sensing/capture/streaming; the laptop/server handles face analysis, policy and dashboard services."),
        ("Access policy", "Registered owner match can unlock; relative requires owner approval; unknown visitor remains locked and generates evidence."),
        ("Hardware actuation", "Relay/LED test load follows an acknowledged, time-limited command and returns to a safe locked state."),
        ("Human monitoring", "Owner receives live image, status, decision controls, emergency shortcuts and persistent audit history."),
        ("Traceability", "Every important transition has a timestamp, person/category, decision, source and snapshot/reference where available."),
        ("Academic explanation", "Viva presentation explains GPIO interrupt wake-up, OV2640 SCCB, PSRAM/DMA rationale, Wi-Fi streaming, offloaded AI, relay isolation and limitations."),
    ], widths=[1.75, 4.75], first_column_bold=True)
    add_body(doc, "The final academic conclusion will be that an inexpensive, event-driven edge device can reduce unnecessary continuous surveillance work while preserving a practical owner-in-the-loop safety path. The project demonstrates a complete software architecture now and will use the remaining weeks to validate the physical sensing, streaming and actuation boundary.")
    add_callout(doc, "EXPECTED VIVA MESSAGE", "The prototype does not claim that every unknown person can be classified perfectly. It shows a safer system response: owners can be automated, relatives can be escalated to a human decision, and unknown visitors are denied by default with evidence retained.", fill=MINT, accent=TEAL)

    # 9 measurements
    add_section_title(doc, "9", "Metrics to record before final submission")
    add_table(doc, ["Metric", "Target / reference", "How it will be measured"], [
        ("Camera frame size", "640 × 480 VGA", "Dashboard status and saved frame dimensions."),
        ("Frame rate", "15–20 FPS target", "Count received frames over a 30-second interval."),
        ("PIR-to-camera activation", "As low as practical; document actual", "Timestamp ISR/HTTP trigger and first valid JPEG."),
        ("Face decision time", "Stable decision after configured confirmation frames", "Timestamp first analysis frame and decision event."),
        ("Relay response", "Document command-to-LED/relay transition", "Oscilloscope or high-speed timestamp observation where available."),
        ("Auto-relock", "5 s camera relay / configured physical timer", "Measure unlock command to locked indication."),
        ("Unknown-face safety", "0 unintended unlocks in test matrix", "Repeat unknown/low-light/side-by-side trials."),
        ("Reconnect behavior", "Recover without unsafe unlock", "Disconnect Wi-Fi/camera and verify visible fault + locked output."),
        ("Power objective", "Compare idle event-driven vs active window", "Measure current at idle, PIR-triggered capture and relay-active states."),
    ], widths=[1.65, 2.3, 2.55], first_column_bold=True)

    # 10 risks
    add_section_title(doc, "10", "Risks, limitations and mitigations")
    add_table(doc, ["Risk / limitation", "Impact", "Mitigation or disclosure"], [
        ("Virtual Smart Connect camera selected", "No useful face image", "Camera index selector, visible source status, stop/switch control and documented Windows camera permissions."),
        ("LBPH is lighting-sensitive", "False reject or false accept", "Multiple references, stable threshold, consecutive-frame confirmation and explicit non-probability score."),
        ("No liveness detection", "Photo spoofing is possible", "Disclose that the minor-project prototype is not a certified biometric lock; future work can add liveness."),
        ("ESP32 Wi-Fi loss", "No current frame or delayed decision", "Fail-safe locked relay, visible fault state, reconnect loop and fallback SITL demonstration."),
        ("Relay inductive load", "Electrical damage or unsafe switching", "Optocoupler/transistor driver, flyback protection, separate supply and low-voltage test load first."),
        ("PIR false triggers", "Unnecessary camera wake/analysis", "Warm-up, morphology, confirmation frames, cooldown and future sensor placement/tuning."),
        ("Hardware not procured in time", "No physical viva demo", "Keep software/hardware interfaces stable, collect laptop evidence and present a clearly labelled SITL fallback."),
        ("Personal data/privacy", "Unauthorized image exposure", "Local storage by default, optional API key, private network binding, no reference directory serving."),
    ], widths=[1.75, 1.55, 3.2], first_column_bold=True, font_size=8.2)

    # 11 viva points
    add_section_title(doc, "11", "Viva defence points")
    add_subtitle(doc, "Microcontroller and memory architecture")
    add_body(doc, "The OV2640 camera produces JPEG frames through the ESP32 camera interface. PSRAM is important for frame buffers because ordinary internal SRAM is constrained. DMA reduces CPU intervention while moving camera data. These statements describe the intended ESP32 hardware path; the laptop SITL uses OpenCV buffers and therefore cannot validate the board's PSRAM/DMA electrical behavior.")
    add_subtitle(doc, "Power management and interrupt design")
    add_body(doc, "The intended low-power design keeps the ESP32-CAM in an idle/deep-sleep or low-activity state and uses the HC-SR501 output as a GPIO wake/interrupt source. The current SITL emulates the decision boundary with software MOG2 and manual triggers. The final hardware phase must validate the selected GPIO, wake source, PIR hold time, debouncing and active capture window on the actual board.")
    add_subtitle(doc, "Hardware isolation and actuation")
    add_body(doc, "The ESP32 GPIO must not directly power a high-current lock or an inductive relay coil. The bench circuit should use an optocoupler or suitable transistor driver, a flyback diode for a DC coil, a separate load supply and a low-voltage LED/test load first. The mock and configured HTTP/serial drivers already model a time-limited, acknowledged actuation command and safe relock behavior.")
    add_subtitle(doc, "Hardware/software boundary")
    add_body(doc, "The `CameraStream` source and `RelayDriver` interfaces isolate device-specific code from face recognition, access policy, audit storage and dashboards. That is why the project can demonstrate a laptop webcam now and switch to an ESP32 HTTP stream later. The policy remains server-side so it can log evidence and enforce owner approval consistently.")

    # 12 appendix
    add_section_title(doc, "12", "Appendix: demonstration commands and files")
    add_subtitle(doc, "Windows launch")
    add_code(doc, 'Set-Location "C:\\Users\\aayus\\working-ly\\edge-vision-sitl"\n.\\.venv\\Scripts\\python.exe main.py')
    add_subtitle(doc, "Dashboard URLs")
    add_table(doc, ["URL", "Purpose"], [
        ("http://127.0.0.1:8000/simulation", "Selectable house, visitor movement, PIR zone and doorbell."),
        ("http://127.0.0.1:8000/owner", "Owner monitoring, approval inbox, occupancy, Face IDs and logs."),
        ("http://127.0.0.1:8000/camera", "Laptop webcam, MJPEG feed, recognition and manual PIR trigger."),
        ("http://127.0.0.1:8000/docs", "FastAPI interactive API documentation."),
    ], widths=[3.0, 3.5], first_column_bold=True)
    add_subtitle(doc, "Important implementation files")
    add_table(doc, ["File", "Responsibility"], [
        ("`main.py`", "FastAPI lifecycle, dashboards, REST routes, camera controls and WebSocket events."),
        ("`simulation_engine.py`", "House movement, PIR zone, doorbell, gate boundary, approval and occupancy."),
        ("`camera_stream.py`", "Webcam/ESP32 source abstraction and MOG2 motion detector."),
        ("`face_engine.py`", "Haar/LBPH face detection, matching, overlays and reference validation."),
        ("`face_registry.py`", "Owner/relative face-ID roles and persistent metadata."),
        ("`controller.py`", "Camera state machine, relative approval, snapshots and relay control."),
        ("`hardware_mock.py`", "Mock relay, HTTP/serial relay drivers and watchdog relock."),
        ("`tests/`", "43 automated tests covering software, API, camera and browser workflows."),
    ], widths=[1.75, 4.75], first_column_bold=True)
    add_callout(doc, "FINAL STATUS", "At this reporting point the software prototype is ready for demonstration and hardware attachment. The remaining work is measurable and bounded: assemble the edge hardware, validate the interrupt/stream/relay contracts, collect performance data, and freeze the final viva evidence by 30 November 2026.", fill=MINT, accent=TEAL)

    # References and sign-off
    add_section_title(doc, "13", "References and review sign-off")
    for item in [
        "Espressif Systems, ESP32 CameraWebServer and ESP32 camera driver documentation — camera interface, frame buffers and PSRAM configuration.",
        "OpenCV documentation — VideoCapture, MOG2 background subtraction, Haar cascades and LBPH face recognizer.",
        "FastAPI and Uvicorn documentation — asynchronous API services, multipart uploads, streaming responses and WebSockets.",
        "HC-SR501 PIR module documentation — trigger hold time, sensitivity and output behavior.",
        "Project source tree: `C:\\Users\\aayus\\working-ly\\edge-vision-sitl` and generated test evidence.",
    ]:
        add_bullet(doc, item)
    doc.add_paragraph().paragraph_format.space_after = Pt(20)
    sign = add_table(doc, ["Review role", "Name / signature", "Date"], [
        ("Student / project team", "________________________________", "____________"),
        ("Project guide", "________________________________", "____________"),
        ("Progress review committee", "________________________________", "____________"),
    ], widths=[2.0, 3.15, 1.35], first_column_bold=True)

    # Ensure all headings remain in the navigation pane and document opens on page 1.
    for paragraph in doc.paragraphs:
        if paragraph.style.name.startswith("Heading"):
            paragraph.paragraph_format.keep_with_next = True

    doc.save(OUTPUT)
    return OUTPUT


if __name__ == "__main__":
    path = build_report()
    print(path)
