"""
Script to generate publication-grade technical PDF documentation for Veritas
covering all 5 input modalities: Text, Image, DOCX, PDF, and URL.
Uses standard Helvetica/Courier fonts with pure ASCII typography to guarantee
100% clean rendering with zero missing glyphs across exactly 6 beautifully balanced pages.
"""

import sys
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# Veritas Palette
C_DARK = colors.HexColor("#151C18")       # Editorial Ink
C_FOREST = colors.HexColor("#243C30")     # Veritas Forest Green
C_GOLD = colors.HexColor("#B8860B")       # Ochre / Gold
C_LIGHT_BG = colors.HexColor("#F8F6F0")   # Warm Paper
C_BORDER = colors.HexColor("#D8D0C2")     # Border line
C_TEXT = colors.HexColor("#1F2722")       # Charcoal Body Text
C_MUTED = colors.HexColor("#536259")      # Muted Slate
C_ACCENT_BG = colors.HexColor("#EAE4D5")  # Table Header
C_CODE_BG = colors.HexColor("#19211C")    # Terminal Dark
C_CODE_TEXT = colors.HexColor("#EAE4D5")  # Terminal Light

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        # Running header on pages 2..N
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 8)
            self.setFillColor(C_FOREST)
            self.drawString(54, 750, "VERITAS")
            self.setFont("Helvetica", 8)
            self.setFillColor(C_MUTED)
            self.drawString(102, 750, "|   Input Modalities Architecture: Text, Image, DOCX, PDF & URL")
            
            # Top rule
            self.setStrokeColor(C_BORDER)
            self.setLineWidth(0.75)
            self.line(54, 742, letter[0] - 54, 742)

        # Bottom footer on all pages
        self.setStrokeColor(C_BORDER)
        self.setLineWidth(0.75)
        self.line(54, 45, letter[0] - 54, 45)
        self.setFont("Helvetica", 8)
        self.setFillColor(C_MUTED)
        self.drawString(54, 32, "Veritas Engineering Guide  -  Automated Fact-Checking System")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(letter[0] - 54, 32, page_str)
        self.restoreState()


def build_pdf(filename: str):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()

    # Typography Styles
    title_style = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=C_DARK,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        'CoverSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=C_MUTED,
        spaceAfter=12,
    )
    h1_style = ParagraphStyle(
        'Heading1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=C_FOREST,
        spaceBefore=10,
        spaceAfter=6,
        keepWithNext=True,
    )
    h2_style = ParagraphStyle(
        'Heading2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=C_DARK,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13.5,
        textColor=C_TEXT,
        spaceAfter=5,
    )
    bullet_style = ParagraphStyle(
        'Bullet',
        parent=body_style,
        leftIndent=14,
        firstLineIndent=-10,
        spaceAfter=3.5,
    )
    code_style = ParagraphStyle(
        'CodeSnippet',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.2,
        leading=10,
        textColor=C_CODE_TEXT,
    )
    callout_style = ParagraphStyle(
        'CalloutText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=C_DARK,
    )
    table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=C_TEXT,
    )
    table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=C_DARK,
    )

    story = []

    # =========================================================================
    # PAGE 1: OVERVIEW & MODALITY COMPARISON MATRIX
    # =========================================================================
    story.append(Paragraph("VERITAS ARCHITECTURAL REFERENCE", ParagraphStyle('Eyebrow', fontName='Helvetica-Bold', fontSize=9, textColor=C_GOLD, spaceAfter=3)))
    story.append(Paragraph("How the 5 Input Modalities Work Under the Hood", title_style))
    story.append(Paragraph("A Deep-Dive into Intake, Extraction, Security & Verification Pipelines for <b>Text, Image, DOCX, PDF, and URL</b>", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_FOREST, spaceBefore=0, spaceAfter=10))

    # Executive Summary Card
    summary_text = (
        "<b>Executive Summary (Karyakram Saransh):</b> Veritas is an evidence-first fact-checking system. Users can submit "
        "artifacts in 5 distinct forms: raw copy/claims (<b>TEXT</b>), screenshots/photos (<b>IMAGE</b>), Word files (<b>DOCX</b>), "
        "PDF reports (<b>PDF</b>), and public web links (<b>URL</b>). Each modality has a specialized ingestion and extraction pathway "
        "that isolates checkable factual claims. Once normalized, all inputs converge into a unified <b>LangGraph 7-Agent "
        "Verification Graph</b> that executes live multi-provider web research, fact-checker cross-referencing, vector evidence "
        "indexing, and semantic adjudication."
    )
    summary_table = Table([[Paragraph(summary_text, callout_style)]], colWidths=[letter[0] - 108])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 10))

    story.append(Paragraph("Modality Comparison Matrix", h2_style))
    matrix_data = [
        [
            Paragraph("Modality", table_header),
            Paragraph("Ingestion Route / Protocol", table_header),
            Paragraph("Parsing & Intelligence Engine", table_header),
            Paragraph("Safety Guardrails & Key Output", table_header),
        ],
        [
            Paragraph("<b>1. TEXT / CLAIM</b>", table_cell),
            Paragraph("POST /api/v1/verify<br/>ArtifactKind.TEXT / CLAIM", table_cell),
            Paragraph("spaCy (en_core_web_sm) + NLTK tokenization + Optional LLM", table_cell),
            Paragraph("MAX_TEXT_CHARS (100k), filters min 4 tokens, extracts named entities & key claims.", table_cell),
        ],
        [
            Paragraph("<b>2. IMAGE</b>", table_cell),
            Paragraph("POST /api/v1/files/upload-media<br/>-► POST /api/v1/verify", table_cell),
            Paragraph("Pillow + Vision LLM (Qwen/GPT-4o) + Google Vision + OpenCV OCR", table_cell),
            Paragraph("25MP/46MP decompression bomb defense, EXIF camera metadata, reverse image matching.", table_cell),
        ],
        [
            Paragraph("<b>3. DOCX</b>", table_cell),
            Paragraph("POST /api/v1/files/extract-text<br/>(file: UploadFile)", table_cell),
            Paragraph("python-docx<br/>(Document.paragraphs)", table_cell),
            Paragraph("50 MB streaming cap, extracts paragraph prose into structured text for claim extraction.", table_cell),
        ],
        [
            Paragraph("<b>4. PDF</b>", table_cell),
            Paragraph("POST /api/v1/files/extract-text<br/>(file: UploadFile)", table_cell),
            Paragraph("pypdf<br/>(PdfReader.pages)", table_cell),
            Paragraph("50 MB streaming limit, multi-page text aggregation, resilient against glyph errors.", table_cell),
        ],
        [
            Paragraph("<b>5. URL</b>", table_cell),
            Paragraph("POST /api/v1/verify<br/>ArtifactKind.URL", table_cell),
            Paragraph("HTTPX Stream + HTMLParser<br/>(_PageTextParser)", table_cell),
            Paragraph("Industrial SSRF guard (blocks private IPs & cloud metadata), 3-hop redirect check, HTML strip.", table_cell),
        ],
    ]
    matrix_tbl = Table(matrix_data, colWidths=[80, 130, 140, 154])
    matrix_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_ACCENT_BG),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(matrix_tbl)
    story.append(Spacer(1, 10))

    # Architecture Flow Banner
    flow_text = (
        "<b>Unified Dataflow Pattern:</b><br/>"
        "Raw Input (Text / Image / DOCX / PDF / URL)  - - -►  Triage & Safe Extraction  - - -►  "
        "Claim Extraction Service (spaCy/LLM)  - - -►  LangGraph 7-Agent Verification Graph  - - -►  "
        "Adjudication & Final Evidence Record."
    )
    flow_tbl = Table([[Paragraph(flow_text, callout_style)]], colWidths=[letter[0] - 108])
    flow_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 0.5, C_BORDER),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(flow_tbl)

    story.append(PageBreak())

    # =========================================================================
    # PAGE 2: TEXT & DOCUMENTS (DOCX & PDF)
    # =========================================================================
    story.append(Paragraph("1. Text & Claim Modality Pipeline", h1_style))
    story.append(Paragraph(
        "Direct text input is the core foundation of Veritas. Whether a user pastes a headline, forwarded message, or entire article, "
        "the text desk filters and structures assertions into verified checkable units.",
        body_style
    ))
    story.append(Paragraph("<b>Step-by-Step Architecture:</b>", h2_style))
    story.append(Paragraph("• <b>Intake & Length Enforcement:</b> Direct copy is submitted via <code>POST /api/v1/verify</code>. The request handler validates that string length does not exceed <code>MAX_TEXT_CHARS=100,000</code> to prevent denial-of-service via unbounded prompt generation.", bullet_style))
    story.append(Paragraph("• <b>Triage by TextDesk (<code>app.desks.text.TextDesk</code>):</b> Evaluates whether the submission is already a specific assertion (<code>ArtifactKind.CLAIM</code>) or a long article/post (<code>ArtifactKind.TEXT</code>). Direct claims bypass redundant extraction.", bullet_style))
    story.append(Paragraph("• <b>Linguistic Claim Extraction (<code>app.services.claims.ClaimExtractionService</code>):</b>", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;- <b>Sentence Boundary Detection:</b> Uses spaCy's <code>en_core_web_sm</code> pipeline and NLTK's <code>punkt_tab</code> model to split sentences with linguistic awareness.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;- <b>Token Thresholding:</b> Evaluates clause density (<code>CLAIM_MIN_TOKENS=4</code>). Discards conversational noise ('Yes it did') while preserving verifiable claims ('The bridge opened in March').", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;- <b>Named Entity Recognition (NER) & Keywords:</b> Extracts entities (people, organizations, dates, statistics) up to <code>CLAIM_MAX_KEYWORDS=10</code>.", bullet_style))
    story.append(Paragraph("&nbsp;&nbsp;&nbsp;&nbsp;- <b>Optional LLM Extraction:</b> When <code>CLAIM_EXTRACTION_LLM=true</code> is enabled, Groq/OpenAI runs a structured pass separating core verifiable factual claims from opinions and rhetorical questions.", bullet_style))

    story.append(Spacer(1, 10))
    story.append(Paragraph("2. Document Modalities: DOCX & PDF", h1_style))
    story.append(Paragraph(
        "Documents uploaded by users are processed through a two-step pattern: client-side safe extraction via "
        "<code>POST /api/v1/files/extract-text</code>, followed by submission into the verification lifecycle.",
        body_style
    ))
    story.append(Paragraph("<b>DOCX Working Mechanism:</b>", h2_style))
    story.append(Paragraph("• <b>File Streaming & Size Limit:</b> Uploaded as <code>multipart/form-data</code>. The backend reads bytes in 64 KB chunks via <code>_read_limited</code>, ensuring it stays strictly below <code>MAX_UPLOAD_BYTES=52,428,800</code> (50 MB).", bullet_style))
    story.append(Paragraph("• <b>In-Memory Parsing:</b> Uses <code>python-docx</code> wrapped over an in-memory <code>io.BytesIO(content)</code> stream to eliminate filesystem IO overhead and directory traversal risks.", bullet_style))
    story.append(Paragraph("• <b>Paragraph Extraction:</b> Iterates across <code>doc.paragraphs</code>, extracts <code>item.text</code>, filters empty whitespace blocks, and joins them using newlines. Returns clean prose.", bullet_style))

    story.append(Spacer(1, 4))
    story.append(Paragraph("<b>PDF Working Mechanism:</b>", h2_style))
    story.append(Paragraph("• <b>Streaming Intake:</b> Enforces the 50 MB byte limit during chunk reading. Non-PDF files attempting to spoof extensions are rejected.", bullet_style))
    story.append(Paragraph("• <b>Page Extraction via PyPDF:</b> Instantiates <code>pypdf.PdfReader(io.BytesIO(content))</code>. Iterates page by page: <code>page.extract_text() or ''</code>.", bullet_style))
    story.append(Paragraph("• <b>Resilience & Unicode Normalization:</b> If a page contains broken glyphs or malformed formatting, empty strings are substituted rather than raising an uncaught 500 error. Aggregated text is returned as JSON: <code>{'text': extracted_copy}</code>.", bullet_style))
    story.append(Paragraph("• <b>Handoff to Verification:</b> The frontend receives the extracted text, renders a preview in the examination bench, and submits it to <code>POST /api/v1/verify</code> with <code>kind: 'text'</code>.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 3: IMAGE MODALITY (OCR, VISION LLM & GOOGLE VISION)
    # =========================================================================
    story.append(Paragraph("3. Image Modality: Visual Context & Claims", h1_style))
    story.append(Paragraph(
        "In Veritas, an image is treated as a <b>delivery mechanism for a claim</b>. "
        "A photo or screenshot contains both visual context (scene, faces, logos, metadata) and embedded text (memes, headlines, screenshots).",
        body_style
    ))

    # Architecture card
    img_card = (
        "<b>IMAGE EXAMINATION MULTI-PRONGED PIPELINE:</b><br/>"
        "1. <b>Upload & Bomb Defense:</b> <code>POST /api/v1/files/upload-media</code> enforces 50MB byte cap and 25-46MP pixel guards.<br/>"
        "2. <b>EXIF & Geometry:</b> <code>ImageOps.exif_transpose</code> corrects orientation; extracts camera make, model, timestamps.<br/>"
        "3. <b>Multimodal Vision Model:</b> Vision LLM extracts verbatim text, visual observations, and 3 targeted web queries.<br/>"
        "4. <b>Google Cloud Vision:</b> Web Detection reverse-image search uncovers recycled photos and prior publications.<br/>"
        "5. <b>Local OCR Fallback:</b> OpenCV binarization and candidate arbitration if vision models are unconfigured.<br/>"
        "6. <b>Verification Graph:</b> Extracted copy and scene queries feed directly into the LangGraph fact-checking engine."
    )
    img_tbl = Table([[Paragraph(img_card, callout_style)]], colWidths=[letter[0] - 108])
    img_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, C_BORDER),
        ('PADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(img_tbl)
    story.append(Spacer(1, 8))

    story.append(Paragraph("<b>Deep Dive: Image Sub-Systems:</b>", h2_style))
    story.append(Paragraph("• <b>Decompression Bomb Prevention (<code>app.vision.prepare</code> & <code>context</code>):</b> A small 4 KB compressed PNG can expand to 60,000x60,000 pixels consuming 10 GB of RAM. Veritas traps <code>Image.DecompressionBombWarning</code> as an error and enforces a ceiling of <b>25 Megapixels</b> (Pillow) and <b>46 Megapixels</b> (OpenCV).", bullet_style))
    story.append(Paragraph("• <b>Multimodal Scene Comprehension (<code>app.vision.context.describe</code>):</b> Converts the image into a base64 JPEG thumbnail (max 1800x1800 px, quality 90). Sends a strict system prompt to the vision LLM (e.g. Qwen-VL or GPT-4o-mini): <i>'Describe only what is visibly present. Recover readable text verbatim, including Hindi. Do not infer identities, dates, or authenticity without evidence. Suggest up to 3 focused web queries.'</i> Returns structured JSON matching the <code>Scene</code> schema.", bullet_style))
    story.append(Paragraph("• <b>Reverse Image Search (<code>app.vision.context.reverse_matches</code>):</b> Sends the image content to Google Cloud Vision API (<code>WEB_DETECTION</code>). Parses <code>pagesWithMatchingImages</code> to identify where and when this exact image appeared on the web. This instantly uncovers recycled photos being shared with fabricated new headlines.", bullet_style))
    story.append(Paragraph("• <b>Adaptive OCR Candidate Arbitration (<code>app.vision.prepare.candidates</code>):</b> When running local OCR, Veritas notes that <i>'preprocessing that rescues a photograph ruins a screenshot'</i>. It generates multiple image variants (deskewed, grayscale, adaptive Otsu thresholding, contrast-enhanced) and lets the reader retain whichever candidate recognized the highest-confidence text.", bullet_style))
    story.append(Paragraph("• <b>Exhibits & Limitations Ledger:</b> Visual observations are reported alongside an explicit limitation: <i>'Visual observations and editable file metadata cannot prove that pixels are authentic or AI-generated.'</i>", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 4: URL MODALITY (SSRF PROTECTION & SCRAPING)
    # =========================================================================
    story.append(Paragraph("4. URL Modality: Public Link Ingestion & SSRF Defense", h1_style))
    story.append(Paragraph(
        "When a user submits a public web link (news article, blog post, or tweet), Veritas fetches the remote page, "
        "strips non-editorial clutter, and feeds the underlying story into the verification engine.",
        body_style
    ))
    story.append(Paragraph("<b>Security Architecture: Server-Side Request Forgery (SSRF) Defense:</b>", h2_style))
    story.append(Paragraph(
        "A URL supplied by an untrusted user and fetched by the server is an inherent request-forgery threat. Without defenses, "
        "an attacker could probe internal endpoints like <code>http://localhost:5432</code> (PostgreSQL) or <code>http://169.254.169.254/</code> "
        "(cloud metadata holding IAM keys). Veritas implements industrial-grade defenses in <code>app.media.fetch</code>:",
        body_style
    ))
    story.append(Paragraph("• <b>Scheme Whitelisting:</b> Permits only <code>http</code> and <code>https</code>. Rejects <code>file://</code>, <code>ftp://</code>, <code>gopher://</code>, or unix domain sockets.", bullet_style))
    story.append(Paragraph("• <b>Full IP Address Resolution (<code>_permitted</code>):</b> Resolves the host using <code>socket.getaddrinfo</code>. Iterates through <i>all</i> returned IP addresses. If any address is private (RFC 1918), loopback (127.0.0.1), link-local, or reserved, the connection is aborted with a <code>ValidationError</code>.", bullet_style))
    story.append(Paragraph("• <b>Strict Hop-by-Hop Redirect Validation:</b> Disables automatic client redirects. Manually follows redirects up to <code>MAX_REDIRECTS=3</code>, re-running the IP resolution guard on <b>every single hop</b>. This stops attacks where an allowed public domain returns a <code>302 Redirect</code> pointing to an internal IP.", bullet_style))
    story.append(Paragraph("• <b>Streaming Byte Ceiling:</b> Enforces <code>MAX_UPLOAD_BYTES</code> while streaming chunks. If the remote server transmits an endless data stream, the connection is terminated once the byte threshold is breached.", bullet_style))

    story.append(Spacer(1, 8))
    story.append(Paragraph("<b>Editorial HTML Extraction (<code>_PageTextParser</code>):</b>", h2_style))
    story.append(Paragraph("• <b>Noise Stripping:</b> Automatically discards non-content markup: <code>&lt;nav&gt;, &lt;script&gt;, &lt;style&gt;, &lt;title&gt;, &lt;noscript&gt;, &lt;template&gt;, &lt;svg&gt;</code>.", bullet_style))
    story.append(Paragraph("• <b>Semantic Content Hierarchy:</b> Prioritizes <code>&lt;main&gt;</code> and <code>&lt;article&gt;</code> tags so that header navigation, footer links, and sidebar advertisements do not dilute the core claim text.", bullet_style))
    story.append(Paragraph("• <b>Block Normalization:</b> Automatically inserts structured whitespace after block elements (<code>&lt;p&gt;, &lt;div&gt;, &lt;h1-h6&gt;, &lt;li&gt;, &lt;blockquote&gt;</code>), decodes HTML entities, and caps copy to <code>MAX_TEXT_CHARS</code>.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 5: CORE VERIFICATION ENGINE (LANGGRAPH & 7 AGENTS)
    # =========================================================================
    story.append(Paragraph("5. Core Verification Engine: LangGraph Workflow", h1_style))
    story.append(Paragraph(
        "Regardless of whether the input originated as Text, Image, DOCX, PDF, or URL, the extracted prose and claims "
        "converge into the asynchronous verification orchestrator (<code>app.services.verification.VerificationService</code>) "
        "and execute across 7 specialized LangGraph agents.",
        body_style
    ))

    # ASCII Graph Diagram
    graph_box = [
        [
            Paragraph("<b>LANGGRAPH 7-AGENT VERIFICATION TOPOLOGY</b><br/><br/>"
                      "<code>+-------+     +------------+      +-----------------------------------------+<br/>"
                      "| START | --► | ClaimAgent | ---► | SearchAgent (Tavily, Brave, Serper)     |<br/>"
                      "+-------+     +------------+  |   +-----------------------------------------+<br/>"
                      "                    |         |                        |<br/>"
                      "                    |         +------------------------+--► +---------------+<br/>"
                      "                    |         |                             | EvidenceAgent |<br/>"
                      "                    |         |   +---------------------+   +---------------+<br/>"
                      "                    |         +-► | FactCheckAgent (GC) |          |<br/>"
                      "                    |             +---------------------+          ▼<br/>"
                      "                    |                        |              +-------------+<br/>"
                      "                    |                        +------------► | SourceAgent |<br/>"
                      "                    |                                       +-------------+<br/>"
                      "                    |                                              |<br/>"
                      "                    |                                              ▼<br/>"
                      "                    | [No Claims]                       +--------------------+<br/>"
                      "                    |                                   | ContradictionAgent |<br/>"
                      "                    |                                   +--------------------+<br/>"
                      "                    |                                              |<br/>"
                      "                    +----------------------------------------------+--► +---------------+<br/>"
                      "                                                                        | SemanticJudge | --► END<br/>"
                      "                                                                        +---------------+</code>",
                      code_style)
        ]
    ]
    graph_tbl = Table(graph_box, colWidths=[letter[0] - 108])
    graph_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_CODE_BG),
        ('BOX', (0,0), (-1,-1), 1, C_FOREST),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(graph_tbl)
    story.append(Spacer(1, 10))

    story.append(Paragraph("<b>The Seven Specialized Agents:</b>", h2_style))
    story.append(Paragraph("<b>1. ClaimAgent (<code>app.graph.agents.claim</code>):</b> Extracts individual verifiable assertions from the text, normalizes pronoun co-references, and strips rhetorical devices. If zero claims are found, short-circuits directly to the judge.", bullet_style))
    story.append(Paragraph("<b>2. SearchAgent (<code>app.graph.agents.search</code>):</b> Fans out parallel search queries across multi-provider indexes (Tavily general/news, Serper, Brave). Never relies on a single search engine to avoid index bias.", bullet_style))
    story.append(Paragraph("<b>3. FactCheckAgent (<code>app.graph.agents.factcheck</code>):</b> Concurrently queries Google's Fact Check Tools API for prior debunks published by verified IFCN fact-checkers (PolitiFact, Snopes, Vishvas News, AltNews).", bullet_style))
    story.append(Paragraph("<b>4. EvidenceAgent (<code>app.graph.agents.evidence</code>):</b> Indexes harvested passages into ChromaDB vector store, computes cosine similarity with the claim, and retrieves top-scoring excerpts above similarity thresholds.", bullet_style))
    story.append(Paragraph("<b>5. SourceAgent (<code>app.graph.agents.source</code>):</b> Evaluates publisher credibility, domain standing, historical bias, and whether sources are primary documents vs aggregate commentary.", bullet_style))
    story.append(Paragraph("<b>6. ContradictionAgent (<code>app.graph.agents.contradiction</code>):</b> Analyzes semantic stance (Entailment vs Contradiction vs Neutral) between the claimed assertion and the cited evidence passages.", bullet_style))
    story.append(Paragraph("<b>7. SemanticJudge (<code>app.graph.agents.semantic</code>):</b> Synthesizes evidence weight, source standing, and consensus margins to file the definitive determination and confidence score.", bullet_style))

    story.append(PageBreak())

    # =========================================================================
    # PAGE 6: ADJUDICATION, DETERMINATIONS MATRIX & TAKEAWAYS
    # =========================================================================
    story.append(Paragraph("6. Adjudication & Determinations", h1_style))
    story.append(Paragraph(
        "The Adjudicator is the final arbiter in Veritas. It examines all filed reports from the examining desks "
        "(Text Desk, Image Desk, and Fact-Check Desk) and reaches a synthesized, transparent ruling.",
        body_style
    ))
    story.append(Paragraph("<b>Veritas Determinations Matrix:</b>", h2_style))

    # Determinations Table
    det_data = [
        [
            Paragraph("Determination", table_header),
            Paragraph("Definition & Semantic Meaning", table_header),
            Paragraph("Adjudication Criteria", table_header),
        ],
        [
            Paragraph("<font color='#2E7D32'><b>VERIFIED</b></font>", table_cell),
            Paragraph("The claim is directly confirmed by high-reputation independent sources.", table_cell),
            Paragraph("High consensus score, credible primary reporting, zero major contradictions.", table_cell),
        ],
        [
            Paragraph("<font color='#C62828'><b>FALSE / CONTRADICTED</b></font>", table_cell),
            Paragraph("The claim is refuted by established facts, official records, or prior debunks.", table_cell),
            Paragraph("High-credibility sources directly disprove the assertion.", table_cell),
        ],
        [
            Paragraph("<font color='#D84315'><b>MISLEADING</b></font>", table_cell),
            Paragraph("Presents genuine facts or authentic imagery but with deceptive context or spin.", table_cell),
            Paragraph("Partial truth combined with omitted crucial qualifiers or false timeline.", table_cell),
        ],
        [
            Paragraph("<font color='#EF6C00'><b>UNVERIFIED / UNCERTAIN</b></font>", table_cell),
            Paragraph("Insufficient corroboration exists on the public web to rule definitively.", table_cell),
            Paragraph("Conflicting reports, weak sources, or breaking developing story.", table_cell),
        ],
        [
            Paragraph("<font color='#616161'><b>INSUFFICIENT</b></font>", table_cell),
            Paragraph("No checkable factual proposition was contained in the submission.", table_cell),
            Paragraph("Subjective opinion, rhetorical question, or unreadable corrupt media.", table_cell),
        ],
    ]
    det_tbl = Table(det_data, colWidths=[120, 210, 174])
    det_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), C_ACCENT_BG),
        ('GRID', (0,0), (-1,-1), 0.5, C_BORDER),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(det_tbl)
    story.append(Spacer(1, 14))

    story.append(Paragraph("<b>Key Architectural Takeaways for Operators:</b>", h2_style))
    story.append(Paragraph("• <b>Modality Agnostic Core:</b> Regardless of input complexity, all 5 modalities converge into structured textual claims. A photo of a headline and a pasted headline are judged by the exact same truth criteria.", bullet_style))
    story.append(Paragraph("• <b>Zero Blind Trust:</b> LLMs are never allowed to hallucinate verdicts from memory. Every determination requires verifiable web citations, evidence scoring, and source attribution.", bullet_style))
    story.append(Paragraph("• <b>Defense in Depth:</b> SSRF protections safeguard internal cloud metadata, decompression bomb filters protect worker memory, and rate-limiting prevents provider exhaustion.", bullet_style))
    story.append(Paragraph("• <b>Explainable Uncertainty:</b> When evidence is thin, Veritas explicitly returns <i>UNVERIFIED</i> or <i>INSUFFICIENT</i> rather than taking a speculative leap.", bullet_style))

    story.append(Spacer(1, 12))

    final_note = (
        "<b>VERITAS INSPECTABILITY COMMITMENT:</b><br/>"
        "Veritas is built on the philosophy that a fact-check is only as good as its verifiable paper trail. "
        "Every verification record preserves the full exhibits ledger, raw publisher ratings, source URLs, and "
        "confidence calculations so readers can audit the determination for themselves."
    )
    final_tbl = Table([[Paragraph(final_note, callout_style)]], colWidths=[letter[0] - 108])
    final_tbl.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), C_LIGHT_BG),
        ('BOX', (0,0), (-1,-1), 1, C_GOLD),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(final_tbl)

    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF: {filename}")


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "veritas_modalities_architecture.pdf"
    build_pdf(out_path)
