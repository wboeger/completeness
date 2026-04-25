"""
generate_manuals.py
Generates the Porcentômetro user manual in English and Portuguese as PDF files.
Run once: python generate_manuals.py
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.platypus.tableofcontents import TableOfContents

W, H = A4
MARGIN = 2.2 * cm
APP_URL = 'https://comfortable-emotion-production-e366.up.railway.app/'

# ── colour palette ─────────────────────────────────────────────────────────────
BLUE_DARK  = colors.HexColor('#1a3a5c')
BLUE_MID   = colors.HexColor('#2980b9')
BLUE_LIGHT = colors.HexColor('#eaf4fd')
GREY_LIGHT = colors.HexColor('#f4f6f9')
GREY_MID   = colors.HexColor('#7f8c8d')
GREEN      = colors.HexColor('#27ae60')
ORANGE     = colors.HexColor('#e67e22')
RED        = colors.HexColor('#c0392b')

# ── style factory ──────────────────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()
    S = {}
    S['title'] = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=26,
                                 textColor=BLUE_DARK, leading=32, spaceAfter=6,
                                 alignment=TA_CENTER)
    S['subtitle'] = ParagraphStyle('subtitle', fontName='Helvetica', fontSize=13,
                                    textColor=GREY_MID, leading=18, spaceAfter=4,
                                    alignment=TA_CENTER)
    S['version'] = ParagraphStyle('version', fontName='Helvetica', fontSize=10,
                                   textColor=GREY_MID, leading=14, spaceAfter=2,
                                   alignment=TA_CENTER)
    S['h1'] = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=16,
                              textColor=BLUE_DARK, leading=22, spaceBefore=18, spaceAfter=6,
                              borderPad=4)
    S['h2'] = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=13,
                              textColor=BLUE_MID, leading=18, spaceBefore=14, spaceAfter=4)
    S['h3'] = ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLUE_DARK, leading=16, spaceBefore=10, spaceAfter=3)
    S['body'] = ParagraphStyle('body', fontName='Helvetica', fontSize=10,
                                textColor=colors.black, leading=15, spaceAfter=6,
                                alignment=TA_JUSTIFY)
    S['bullet'] = ParagraphStyle('bullet', fontName='Helvetica', fontSize=10,
                                  textColor=colors.black, leading=14, spaceAfter=3,
                                  leftIndent=14, firstLineIndent=-10)
    S['code'] = ParagraphStyle('code', fontName='Courier', fontSize=8.5,
                                textColor=colors.HexColor('#2c3e50'), leading=13,
                                spaceAfter=3, leftIndent=12,
                                backColor=GREY_LIGHT, borderPad=4)
    S['note'] = ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=9.5,
                                textColor=colors.HexColor('#6d4a00'), leading=14,
                                spaceAfter=4, leftIndent=8)
    S['toc'] = ParagraphStyle('toc', fontName='Helvetica', fontSize=10,
                               textColor=BLUE_DARK, leading=16, spaceAfter=2)
    S['footer'] = ParagraphStyle('footer', fontName='Helvetica', fontSize=8,
                                  textColor=GREY_MID, alignment=TA_CENTER)
    S['url_label'] = ParagraphStyle('url_label', fontName='Helvetica-Bold', fontSize=9,
                                     textColor=colors.HexColor('#1a5276'),
                                     leading=13, spaceAfter=2, alignment=TA_CENTER)
    S['url_link'] = ParagraphStyle('url_link', fontName='Courier-Bold', fontSize=12,
                                    textColor=BLUE_MID, leading=18, spaceAfter=0,
                                    alignment=TA_CENTER)
    return S


def url_box(label, S):
    """Highlighted box with the application URL."""
    inner = Table(
        [[Paragraph(label, S['url_label'])],
         [Paragraph(f'<link href="{APP_URL}" color="#2980b9">{APP_URL}</link>',
                    S['url_link'])]],
        colWidths=[W - 2 * MARGIN - 1.6 * cm]
    )
    inner.setStyle(TableStyle([
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 12),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 12),
    ]))
    outer = Table([[inner]], colWidths=[W - 2 * MARGIN])
    outer.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BLUE_LIGHT),
        ('BOX',           (0, 0), (-1, -1), 1.5, BLUE_MID),
        ('ROUNDEDCORNERS', [6]),
        ('TOPPADDING',    (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    return outer


def rule():
    return HRFlowable(width='100%', thickness=1, color=BLUE_MID, spaceAfter=6, spaceBefore=2)


def section_rule():
    return HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#dce1e7'),
                      spaceAfter=4, spaceBefore=2)


def field_table(rows, S):
    """Render a two-column (Field | Description) table."""
    header = [Paragraph('<b>Field</b>', S['body']), Paragraph('<b>Description</b>', S['body'])]
    data = [header] + [[Paragraph(f'<font name="Courier" size="8.5">{r[0]}</font>', S['body']),
                         Paragraph(r[1], S['body'])] for r in rows]
    t = Table(data, colWidths=[4.5*cm, 11.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BLUE_DARK),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',   (0,0), (-1,0), 9),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID',    (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN',  (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    return t


def output_table(rows, S, col1='Sheet / File', col2='Contents'):
    header = [Paragraph(f'<b>{col1}</b>', S['body']), Paragraph(f'<b>{col2}</b>', S['body'])]
    data = [header] + [[Paragraph(f'<font name="Courier" size="8.5">{r[0]}</font>', S['body']),
                         Paragraph(r[1], S['body'])] for r in rows]
    t = Table(data, colWidths=[5*cm, 11*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), GREEN),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID',    (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN',  (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    return t


# ══════════════════════════════════════════════════════════════════════════════
#  ENGLISH MANUAL
# ══════════════════════════════════════════════════════════════════════════════
def build_english(path):
    S = make_styles()
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN,
                            title='Porcentômetro — User Manual',
                            author='CTFB / Taxon Analysis App')

    story = []

    # ── Cover ──────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 2*cm),
        Paragraph('Porcentômetro', S['title']),
        Paragraph('Completeness Assessment System', S['subtitle']),
        Paragraph('Catálogo Taxonômico da Fauna do Brasil (CTFB)', S['subtitle']),
        Spacer(1, 0.4*cm),
        rule(),
        Spacer(1, 0.3*cm),
        Paragraph('User Manual — English', S['version']),
        Paragraph('Version 2.0 · April 2026', S['version']),
        Spacer(1, 1.2*cm),
        url_box('Access the application at:', S),
        Spacer(1, 2*cm),
    ]

    intro_text = (
        'The <b>Porcentômetro</b> is a web-based tool developed for the '
        '<i>Catálogo Taxonômico da Fauna do Brasil</i> (CTFB). It provides two '
        'complementary analyses: (1) the <b>Data Completeness</b> analysis, which '
        'measures how thoroughly the mandatory fields are filled in for species '
        'already catalogued, and (2) the <b>Species-List Completeness</b> analysis, '
        'which compares CTFB records against the Global Biodiversity Information '
        'Facility (GBIF) to identify species known from Brazil that are absent '
        'from the catalogue.'
    )
    story.append(Paragraph(intro_text, S['body']))
    story.append(PageBreak())

    # ── 1. Accessing the System ────────────────────────────────────────────────
    story += [Paragraph('1. Accessing the System', S['h1']), rule()]
    story.append(url_box('Open the application in any modern browser:', S))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        'You will be presented with a login page. Enter your username and password. '
        'If this is your first login after being added by an administrator, you will '
        'be prompted to create your own password before continuing.', S['body']))

    story += [Paragraph('1.1  Authorization', S['h2'])]
    story.append(Paragraph(
        'Each user is associated with one or more taxa listed in the researchers '
        'spreadsheet (<i>pesquisadores.xlsx</i>). You may analyse any taxon within '
        'your area of responsibility and all taxonomically subordinate groups. '
        'Users assigned to <i>Animalia</i> have access to the entire catalogue. '
        'Administrators may analyse any taxon.', S['body']))

    story += [Paragraph('1.2  First Access — Setting Your Password', S['h2'])]
    story.append(Paragraph(
        'Users added by an administrator via the bulk-import tool do <b>not</b> '
        'have a password assigned yet. On first login, the system detects this '
        'and redirects you to a password-creation screen before granting access. '
        'Follow the steps below:', S['body']))

    steps_en = [
        [Paragraph('<b>1</b>', S['body']),
         Paragraph('Open the application URL and type your username in the login form. '
                   'Leave the password field <b>empty</b> and click <i>Login</i> '
                   '(or enter any value — it will be ignored at this stage).', S['body'])],
        [Paragraph('<b>2</b>', S['body']),
         Paragraph('The system recognises that no password has been set and '
                   'automatically redirects you to the <b>Set Password</b> screen, '
                   'which displays a welcome message with your username.', S['body'])],
        [Paragraph('<b>3</b>', S['body']),
         Paragraph('Enter a new password of <b>at least 6 characters</b> in the '
                   '"New password" field, then retype it in the "Confirm password" '
                   'field and click <i>Set password and continue</i>.', S['body'])],
        [Paragraph('<b>4</b>', S['body']),
         Paragraph('If the two entries match and meet the minimum length, your '
                   'password is saved and you are immediately logged in and taken '
                   'to the main analysis page.', S['body'])],
        [Paragraph('<b>5</b>', S['body']),
         Paragraph('From this point on, use your username and the password you just '
                   'created on every subsequent login.', S['body'])],
    ]
    steps_t = Table(steps_en, colWidths=[1*cm, W - 2*MARGIN - 1.4*cm])
    steps_t.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (0, -1), 0),
        ('LEFTPADDING',   (1, 0), (1, -1), 8),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, GREY_LIGHT]),
        ('BOX',           (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
    ]))
    story.append(steps_t)
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'If the passwords do not match or are shorter than 6 characters, an error '
        'message is displayed on the same screen and you are asked to try again. '
        'No data is lost in this case.', S['note']))

    story += [Paragraph('1.3  Forgotten Password', S['h2'])]
    story.append(Paragraph(
        'If you forget your password, you cannot reset it yourself. There are two '
        'ways to recover access:', S['body']))
    for bullet in [
        '<b>Contact your administrator</b> — the administrator can click '
        '<i>Reset password</i> next to your account in the Admin Dashboard. '
        'This clears your current password and sets the "must set password" flag, '
        'so the next time you log in you will be taken to the password-creation '
        'screen exactly as in the first-access flow.',
        '<b>Write to the support address</b> — send an e-mail to '
        '<font name="Courier">faunadobrasilctfb@gmail.com</font> identifying '
        'yourself and your username. The team will ask an administrator to reset '
        'your account.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    story += [Paragraph('1.3  Main Page', S['h2'])]
    story.append(Paragraph(
        'After login the main page shows two analysis-type cards. Click one to '
        'select the analysis type, enter a taxon name in the text field (you may '
        'click a chip from your authorized taxa list to fill it automatically), '
        'then press the action button.', S['body']))

    # ── 2. Data Completeness ───────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('2. Data Completeness Analysis', S['h1']), rule()]
    story.append(Paragraph(
        'This analysis evaluates the fraction of mandatory fields that are filled '
        'in for each accepted species (<i>taxonomicstatus = NOME_ACEITO</i>, '
        '<i>taxonrank = ESPECIE</i> or <i>SUBESPECIE</i>) within the requested '
        'taxon. Results are aggregated by family, order, class, sub-class, and '
        'phylum and include the responsible researcher for each group.', S['body']))

    story += [Paragraph('2.1  The 15 Evaluated Fields', S['h2'])]
    story.append(Paragraph(
        'The following fields are always evaluated unless an ecological exclusion '
        'rule applies (see §2.2):', S['body']))
    story.append(field_table([
        ('bibliographicreference', 'Primary bibliographic reference for the taxon.'),
        ('country',                'Country of occurrence (Brazil = BR).'),
        ('establishmentmeans',     'Native, invasive, introduced, etc.'),
        ('endemicbrazil',          'Whether the species is endemic to Brazil.'),
        ('environment',            'Environment type: epicontinental, marinho, or both.'),
        ('locality',               'Occurrence locality description.'),
        ('epicontinentaldomain',   'Phytogeographic domain for freshwater/terrestrial species.'),
        ('marinedomain',           'Marine biogeographic province (sea species only).'),
        ('lifeform',               'Life-form / feeding guild (herbívoro, parasita, etc.).'),
        ('habitat',                'Habitat description.'),
        ('vernacularname',         'Common name in Portuguese.'),
        ('vernacularnamelanguage', 'Language of the common name.'),
        ('vernacularnamelocality', 'Region to which the common name applies.'),
        ('animalhostnames',        'Animal host species (non-herbivores only — see §2.2).'),
        ('vegetalhostnames',       'Plant host species.'),
    ], S))

    story += [Spacer(1, 0.4*cm), Paragraph('2.2  Ecological Exclusion Rules', S['h2'])]
    story.append(Paragraph(
        'Two fields can be excluded from both the numerator and the denominator '
        'when they are biologically inapplicable:', S['body']))

    excl_data = [
        [Paragraph('<b>Field excluded</b>', S['body']),
         Paragraph('<b>Condition</b>', S['body']),
         Paragraph('<b>Rationale</b>', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">marinedomain</font>', S['body']),
         Paragraph('environment = <i>epicontinental</i>', S['body']),
         Paragraph('A freshwater/terrestrial species has no marine biogeographic province.', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">animalhostnames</font>', S['body']),
         Paragraph('lifeform = <i>herbívoro</i>', S['body']),
         Paragraph('Herbivores feed on plants; the animal-host field is not applicable.', S['body'])],
    ]
    et = Table(excl_data, colWidths=[4.5*cm, 4.5*cm, 7*cm])
    et.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ORANGE),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(et)

    story += [Spacer(1, 0.3*cm),
              Paragraph('Example: a freshwater beetle (<i>environment = epicontinental</i>) '
                        'is evaluated against 14 fields instead of 15 because '
                        '<i>marinedomain</i> is excluded from both the count of filled fields '
                        'and the total applicable fields. The completeness percentage is '
                        'therefore calculated over the applicable denominator only.', S['note'])]

    story += [Paragraph('2.3  Completeness Formula', S['h2'])]
    story.append(Paragraph(
        'For each species the completeness score is computed as:', S['body']))
    story.append(Paragraph(
        'completeness (%) = (filled applicable fields) / (total applicable fields) × 100',
        S['code']))
    story.append(Paragraph(
        'The score is then aggregated per taxonomic group using the mean, minimum, '
        'and maximum across all species in that group. The <b>amplitude</b> '
        '(max − min) indicates within-group heterogeneity.', S['body']))

    story += [Paragraph('2.4  Researcher Attribution', S['h2'])]
    story.append(Paragraph(
        'Each aggregated row lists the researcher (<i>nome_completo</i>) responsible '
        'for that group. The lookup climbs the taxonomic hierarchy starting at the '
        'group\'s own rank and moving upward until a responsible researcher is found. '
        'When the researcher is found at a rank higher than the row\'s own rank, the '
        'cell is annotated with "(via &lt;rank&gt;)" to make the delegation '
        'transparent.', S['body']))

    story += [Paragraph('2.5  Output Files', S['h2'])]
    story.append(Paragraph(
        'Results are packaged in a ZIP file containing:', S['body']))
    story.append(output_table([
        ('completeness.xlsx',    'Six spreadsheet tabs: by_species, by_family, by_order, by_class, by_subclass, by_phylum. Each tab includes the taxonomic context columns, species count, mean/min/max completeness, amplitude, and responsible researcher.'),
        ('by_family.pdf',        'Horizontal bar chart of mean completeness by family, sorted alphabetically, with min–max error bars. The most complete family is highlighted in red.'),
        ('by_order.pdf',         'Same chart aggregated by order.'),
        ('by_class.pdf',         'Same chart aggregated by class.'),
        ('by_subclass.pdf',      'Same chart aggregated by subclass (omitted if no subclass data).'),
        ('by_phylum.pdf',        'Same chart aggregated by phylum (omitted for single-phylum queries).'),
    ], S))

    # ── 3. Species-List Completeness ───────────────────────────────────────────
    story += [PageBreak(), Paragraph('3. Species-List Completeness (GBIF)', S['h1']), rule()]
    story.append(Paragraph(
        'This analysis compares the CTFB accepted species list against species '
        'recorded in Brazil on the Global Biodiversity Information Facility (GBIF), '
        'identifying species that occur in Brazil but are absent from the catalogue. '
        'The analysis runs entirely in the background and reports progress in real '
        'time on the status page.', S['body']))

    story += [Paragraph('3.1  How It Works', S['h2'])]
    story.append(Paragraph(
        'The analysis is divided into four sequential phases:', S['body']))

    phases = [
        ('Phase 1 — Taxon resolution',
         'The taxon name you entered is resolved to a GBIF internal identifier '
         '(<i>usageKey</i>) via the GBIF Species Match API '
         '(api.gbif.org/v1/species/match). An error is returned if the name is '
         'not found.'),
        ('Phase 2 — Species key collection',
         'The GBIF Occurrence Search API is queried with filters country=BR and '
         'taxonKey=&lt;resolved key&gt;, using facets on the speciesKey field to '
         'retrieve the list of all species with at least one occurrence record in '
         'Brazil. Pagination is applied automatically for taxa with more than '
         '50 000 species.'),
        ('Phase 3 — Name resolution',
         'Each species key is resolved to a canonical binomial name (genus + '
         'specific epithet) and its higher taxonomy (family, order, class, phylum) '
         'via the GBIF Species API. Up to 20 parallel requests are made '
         'simultaneously, matching GBIF\'s rate limit. For large taxa this phase '
         'takes the most time.'),
        ('Phase 4 — Comparison with CTFB',
         'CTFB species with taxonomicstatus = NOME_ACEITO and taxonrank = ESPECIE '
         'are extracted and represented as lowercase canonical binomials '
         '(genus + specificepithet). GBIF binomials not found in this set are '
         'classified as absent from the catalogue.'),
    ]
    for title, body in phases:
        story += [KeepTogether([
            Paragraph(f'<b>{title}</b>', S['h3']),
            Paragraph(body, S['body']),
        ])]

    story += [Paragraph('3.2  Matching Method and Caveats', S['h2'])]
    story.append(Paragraph(
        'Matching is done on the <b>lowercase canonical binomial</b> '
        '(genus + specificEpithet). This means:', S['body']))
    for bullet in [
        'Species with identical binomials in GBIF and CTFB are counted as present, regardless of author or year.',
        'Nomenclatural discrepancies — such as genus synonymy, spelling variants, or different taxonomic treatments — will cause a species to appear as "absent" even if it is represented under a different name in CTFB.',
        'Infraspecific taxa (subspecies, varieties) are excluded from both sides of the comparison.',
        'Manual review of the gap list is recommended, especially for groups with known nomenclatural instability.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    story += [Paragraph('3.3  Output File', S['h2'])]
    story.append(Paragraph(
        'A single XLSX file is downloaded with three sheets:', S['body']))
    story.append(output_table([
        ('Ausentes_no_CTFB',    'All GBIF species (Brazil) absent from CTFB, sorted by phylum → class → order → family → name. Columns: phylum_gbif, classe_gbif, ordem_gbif, familia_gbif, nome_cientifico, gbif_species_key.'),
        ('Resumo_por_Familia',  'Summary per family: number of GBIF species absent from CTFB, total GBIF species in that family, and percentage absent. Sorted by number of absent species (descending).'),
        ('Presentes_no_CTFB',   'GBIF species that were matched to a CTFB NOME_ACEITO record. Useful for cross-checking and understanding coverage.'),
    ], S))

    story += [Paragraph('3.4  Expected Run Time', S['h2'])]
    time_data = [
        [Paragraph('<b>Taxon scale</b>', S['body']),
         Paragraph('<b>Approx. GBIF species</b>', S['body']),
         Paragraph('<b>Estimated time</b>', S['body'])],
        [Paragraph('Small order (e.g. Nematomorpha)', S['body']),
         Paragraph('< 200', S['body']),
         Paragraph('10–30 seconds', S['body'])],
        [Paragraph('Medium order (e.g. Araneae)', S['body']),
         Paragraph('~5 000', S['body']),
         Paragraph('2–5 minutes', S['body'])],
        [Paragraph('Large order (e.g. Coleoptera)', S['body']),
         Paragraph('~100 000', S['body']),
         Paragraph('15–30 minutes', S['body'])],
        [Paragraph('Full phylum (e.g. Arthropoda)', S['body']),
         Paragraph('> 200 000', S['body']),
         Paragraph('1–3 hours', S['body'])],
    ]
    tt = Table(time_data, colWidths=[5.5*cm, 4.5*cm, 6*cm])
    tt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BLUE_MID),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(tt)
    story.append(Paragraph(
        'The status page auto-refreshes every 2 seconds and shows a progress bar. '
        'You may close the tab and return later; the job continues server-side '
        'until completion or until the server is redeployed.', S['note']))

    # ── 4. Administration ──────────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('4. Administration', S['h1']), rule()]
    story.append(Paragraph(
        'Administrator accounts have access to the Admin Dashboard via the link '
        'at the bottom of the main page.', S['body']))

    story += [Paragraph('4.1  User Management', S['h2'])]
    for item in [
        ('<b>Bulk import</b> — paste a list of usernames (logins) from <i>pesquisadores.xlsx</i>. '
         'Each user is created with the flag "must set password on first login". '
         'Users not found in the spreadsheet are rejected.'),
        ('<b>Individual add</b> — create a single user with an immediately usable password.'),
        ('<b>Export CSV</b> — download a backup of all user accounts including hashed passwords. '
         'Recommended before every redeployment when using SQLite.'),
        ('<b>Restore CSV</b> — re-import users from a previously exported CSV. '
         'Existing accounts are skipped; hashed passwords are restored so users '
         'do not need to reset their passwords.'),
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))

    story += [Paragraph('4.2  Database Persistence', S['h2'])]
    story.append(Paragraph(
        'The system supports two database backends:', S['body']))
    db_data = [
        [Paragraph('<b>Backend</b>', S['body']),
         Paragraph('<b>Persistence</b>', S['body']),
         Paragraph('<b>How to activate</b>', S['body'])],
        [Paragraph('PostgreSQL', S['body']),
         Paragraph('Permanent — survives all redeployments.', S['body']),
         Paragraph('Set the DATABASE_URL environment variable to a postgresql:// connection string (e.g. from Railway).', S['body'])],
        [Paragraph('SQLite', S['body']),
         Paragraph('Ephemeral — data is lost on each redeployment.', S['body']),
         Paragraph('Default when DATABASE_URL is not set. A warning banner is shown on the Admin Dashboard.', S['body'])],
    ]
    dbt = Table(db_data, colWidths=[3*cm, 4*cm, 9*cm])
    dbt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BLUE_DARK),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(dbt)

    story += [Paragraph('4.3  Data Sources', S['h2'])]
    story.append(Paragraph(
        'The system loads two Google Sheets on startup. If a Sheet is unreachable '
        '(e.g. offline), the system falls back to local XLSX files stored in the '
        '<i>data/</i> directory of the server.', S['body']))
    story.append(output_table([
        ('pesquisadores.xlsx', 'Researcher registry: login, nome_completo, táxons, institution. Drives user authorization and researcher attribution in output tables.'),
        ('planilha_extendida.xlsx', 'Extended CTFB catalogue with all Darwin Core fields plus manual fields. This is the source for all completeness calculations.'),
    ], S, col1='File', col2='Contents'))

    # ── 5. Interpreting Results ────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('5. Interpreting Results', S['h1']), rule()]

    story += [Paragraph('5.1  Data Completeness Charts', S['h2'])]
    story.append(Paragraph(
        'Each PDF chart shows a horizontal bar per taxonomic group. The bar '
        'length represents the mean completeness (%). Error bars extend to the '
        'minimum and maximum completeness found within the group. The bar with '
        'the highest mean is coloured red; all others are blue. Values are '
        'annotated to the right of each bar.', S['body']))
    story.append(Paragraph(
        'A group with 100% mean completeness and zero amplitude is perfectly '
        'homogeneous — every species has all applicable fields filled. A wide '
        'amplitude indicates that some species are well-documented while others '
        'lack many fields, signalling where curatorial effort should be focused.',
        S['body']))

    story += [Paragraph('5.2  Species Gap List', S['h2'])]
    story.append(Paragraph(
        'The <i>Ausentes_no_CTFB</i> sheet lists candidate species for inclusion '
        'in the catalogue. Before acting on an entry, always consider:', S['body']))
    for bullet in [
        'Nomenclatural differences — the species may already be in CTFB under a different (but synonymous) binomial.',
        'Taxonomic scope — GBIF occurrences include records from all habitats; some species may be marine and outside the scope of CTFB\'s current coverage.',
        'Record quality — some GBIF records are misidentified or lack coordinate precision. High-uncertainty records should be verified.',
        'Subspecific taxa — the analysis covers species level only; subspecies absent from CTFB are not flagged.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    # ── Footer ─────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1.5*cm),
        section_rule(),
        Paragraph(
            'Problems or questions? Write to '
            '<font name="Courier">faunadobrasilctfb@gmail.com</font>',
            S['footer']),
        Spacer(1, 0.15*cm),
        Paragraph('Porcentômetro · CTFB · April 2026 · English edition', S['footer']),
    ]

    doc.build(story)
    print(f'✓ English manual written to {path}')


# ══════════════════════════════════════════════════════════════════════════════
#  PORTUGUESE MANUAL
# ══════════════════════════════════════════════════════════════════════════════
def build_portuguese(path):
    S = make_styles()
    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN,
                            title='Porcentômetro — Manual do Usuário',
                            author='CTFB / Taxon Analysis App')

    story = []

    # ── Capa ───────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 2*cm),
        Paragraph('Porcentômetro', S['title']),
        Paragraph('Sistema de Avaliação da Completude', S['subtitle']),
        Paragraph('Catálogo Taxonômico da Fauna do Brasil (CTFB)', S['subtitle']),
        Spacer(1, 0.4*cm),
        rule(),
        Spacer(1, 0.3*cm),
        Paragraph('Manual do Usuário — Português', S['version']),
        Paragraph('Versão 2.0 · Abril de 2026', S['version']),
        Spacer(1, 1.2*cm),
        url_box('Acesse a aplicação em:', S),
        Spacer(1, 2*cm),
    ]

    story.append(Paragraph(
        'O <b>Porcentômetro</b> é uma ferramenta web desenvolvida para o '
        '<i>Catálogo Taxonômico da Fauna do Brasil</i> (CTFB). Ele oferece dois '
        'tipos de análise complementares: (1) a <b>Completude dos Dados</b>, que '
        'mede o grau de preenchimento dos campos obrigatórios das espécies já '
        'catalogadas, e (2) a <b>Completude da Lista de Espécies</b>, que compara '
        'os registros do CTFB com os do Global Biodiversity Information Facility '
        '(GBIF) para identificar espécies conhecidas do Brasil ausentes no '
        'catálogo.', S['body']))
    story.append(PageBreak())

    # ── 1. Acesso ──────────────────────────────────────────────────────────────
    story += [Paragraph('1. Acesso ao Sistema', S['h1']), rule()]
    story.append(url_box('Acesse a aplicação em qualquer navegador moderno:', S))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        'Você verá uma tela de login. Informe seu usuário e senha. Se este for seu '
        'primeiro acesso após ser cadastrado por um administrador, você será '
        'direcionado para criar sua própria senha antes de continuar.', S['body']))

    story += [Paragraph('1.1  Autorização de Acesso', S['h2'])]
    story.append(Paragraph(
        'Cada usuário está associado a um ou mais táxons listados na planilha de '
        'pesquisadores (<i>pesquisadores.xlsx</i>). Você pode analisar qualquer '
        'táxon de sua área de responsabilidade e todos os grupos subordinados '
        'hierarquicamente. Usuários associados a <i>Animalia</i> têm acesso a '
        'todo o catálogo. Administradores podem analisar qualquer táxon.',
        S['body']))

    story += [Paragraph('1.2  Primeiro Acesso — Criação de Senha', S['h2'])]
    story.append(Paragraph(
        'Usuários cadastrados pelo administrador por meio da importação em lote '
        '<b>não possuem senha definida</b>. No primeiro acesso, o sistema detecta '
        'isso automaticamente e redireciona você para a tela de criação de senha '
        'antes de liberar o acesso. Siga os passos abaixo:', S['body']))

    steps_pt = [
        [Paragraph('<b>1</b>', S['body']),
         Paragraph('Abra a URL da aplicação, informe seu nome de usuário (login) no '
                   'formulário e clique em <i>Entrar</i>. O campo de senha pode ficar '
                   'em branco ou com qualquer valor — ele será ignorado nesta etapa.',
                   S['body'])],
        [Paragraph('<b>2</b>', S['body']),
         Paragraph('O sistema identifica que a senha ainda não foi definida e redireciona '
                   'automaticamente para a tela <b>Definir Senha</b>, que exibe uma '
                   'mensagem de boas-vindas com o seu nome de usuário.', S['body'])],
        [Paragraph('<b>3</b>', S['body']),
         Paragraph('Digite uma nova senha com <b>no mínimo 6 caracteres</b> no campo '
                   '"Nova senha", repita-a no campo "Confirme a senha" e clique em '
                   '<i>Definir senha e entrar</i>.', S['body'])],
        [Paragraph('<b>4</b>', S['body']),
         Paragraph('Se as senhas coincidirem e atenderem ao tamanho mínimo, sua senha '
                   'é salva e você é imediatamente autenticado e redirecionado para a '
                   'página principal de análise.', S['body'])],
        [Paragraph('<b>5</b>', S['body']),
         Paragraph('A partir daí, use seu login e a senha criada em todos os acessos '
                   'subsequentes.', S['body'])],
    ]
    steps_t = Table(steps_pt, colWidths=[1*cm, W - 2*MARGIN - 1.4*cm])
    steps_t.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (0, -1), 0),
        ('LEFTPADDING',   (1, 0), (1, -1), 8),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, GREY_LIGHT]),
        ('BOX',           (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
    ]))
    story.append(steps_t)
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'Se as senhas não coincidirem ou tiverem menos de 6 caracteres, uma '
        'mensagem de erro é exibida na mesma tela e você pode tentar novamente. '
        'Nenhum dado é perdido nesse caso.', S['note']))

    story += [Paragraph('1.3  Senha Esquecida', S['h2'])]
    story.append(Paragraph(
        'Se você esquecer sua senha, não é possível redefini-la por conta própria. '
        'Há duas formas de recuperar o acesso:', S['body']))
    for bullet in [
        '<b>Contate o administrador</b> — o administrador pode clicar em '
        '<i>Redefinir senha</i> ao lado da sua conta no Painel Admin. '
        'Isso apaga a senha atual e ativa o flag "deve definir senha", de modo '
        'que no próximo acesso você será direcionado para a tela de criação de '
        'senha, exatamente como no primeiro acesso.',
        '<b>Escreva para o suporte</b> — envie um e-mail para '
        '<font name="Courier">faunadobrasilctfb@gmail.com</font> identificando-se '
        'e informando seu nome de usuário. A equipe solicitará ao administrador '
        'que redefina seu acesso.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    story += [Paragraph('1.4  Página Principal', S['h2'])]
    story.append(Paragraph(
        'Após o login, a página principal exibe dois cartões de seleção de tipo de '
        'análise. Clique no cartão desejado, informe o nome do táxon no campo de '
        'texto (você pode clicar em um dos botões de táxons autorizados para '
        'preenchê-lo automaticamente) e pressione o botão de ação.', S['body']))

    # ── 2. Completude dos Dados ────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('2. Análise de Completude dos Dados', S['h1']), rule()]
    story.append(Paragraph(
        'Esta análise avalia a fração de campos obrigatórios preenchidos para cada '
        'espécie aceita (<i>taxonomicstatus = NOME_ACEITO</i>, '
        '<i>taxonrank = ESPECIE</i> ou <i>SUBESPECIE</i>) dentro do táxon '
        'solicitado. Os resultados são agregados por família, ordem, classe, '
        'subclasse e filo, incluindo o pesquisador responsável por cada grupo.',
        S['body']))

    story += [Paragraph('2.1  Os 15 Campos Avaliados', S['h2'])]
    story.append(Paragraph(
        'Os campos a seguir são sempre avaliados, salvo quando uma regra de '
        'exclusão ecológica se aplica (ver §2.2):', S['body']))
    story.append(field_table([
        ('bibliographicreference', 'Referência bibliográfica primária do táxon.'),
        ('country',                'País de ocorrência (Brasil = BR).'),
        ('establishmentmeans',     'Nativa, invasora, introduzida, etc.'),
        ('endemicbrazil',          'Indica se a espécie é endêmica do Brasil.'),
        ('environment',            'Tipo de ambiente: epicontinental, marinho ou ambos.'),
        ('locality',               'Descrição da localidade de ocorrência.'),
        ('epicontinentaldomain',   'Domínio fitogeográfico para espécies dulcícolas/terrestres.'),
        ('marinedomain',           'Província biogeográfica marinha (apenas espécies marinhas).'),
        ('lifeform',               'Forma de vida / guilda alimentar (herbívoro, parasita, etc.).'),
        ('habitat',                'Descrição do habitat.'),
        ('vernacularname',         'Nome popular em português.'),
        ('vernacularnamelanguage', 'Idioma do nome popular.'),
        ('vernacularnamelocality', 'Região à qual o nome popular se refere.'),
        ('animalhostnames',        'Espécies hospedeiras animais (exceto herbívoros — ver §2.2).'),
        ('vegetalhostnames',       'Espécies hospedeiras vegetais.'),
    ], S))

    story += [Spacer(1, 0.4*cm), Paragraph('2.2  Regras de Exclusão Ecológica', S['h2'])]
    story.append(Paragraph(
        'Dois campos podem ser excluídos do numerador e do denominador quando '
        'biologicamente inaplicáveis:', S['body']))

    excl_data = [
        [Paragraph('<b>Campo excluído</b>', S['body']),
         Paragraph('<b>Condição</b>', S['body']),
         Paragraph('<b>Justificativa</b>', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">marinedomain</font>', S['body']),
         Paragraph('environment = <i>epicontinental</i>', S['body']),
         Paragraph('Espécies dulcícolas/terrestres não possuem província biogeográfica marinha.', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">animalhostnames</font>', S['body']),
         Paragraph('lifeform = <i>herbívoro</i>', S['body']),
         Paragraph('Herbívoros se alimentam de plantas; o campo de hospedeiro animal não se aplica.', S['body'])],
    ]
    et = Table(excl_data, colWidths=[4.5*cm, 4.5*cm, 7*cm])
    et.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), ORANGE),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(et)
    story += [Spacer(1, 0.3*cm),
              Paragraph('Exemplo: um besouro de água doce (<i>environment = epicontinental</i>) '
                        'é avaliado em relação a 14 campos em vez de 15, pois '
                        '<i>marinedomain</i> é excluído do numerador e do denominador. '
                        'O percentual de completude é calculado sobre o denominador '
                        'aplicável.', S['note'])]

    story += [Paragraph('2.3  Fórmula de Completude', S['h2'])]
    story.append(Paragraph('Para cada espécie:', S['body']))
    story.append(Paragraph(
        'completude (%) = (campos aplicáveis preenchidos) / (total de campos aplicáveis) × 100',
        S['code']))
    story.append(Paragraph(
        'Os valores são então agregados por grupo taxonômico como média, mínimo e '
        'máximo entre todas as espécies do grupo. A <b>amplitude</b> '
        '(máx − mín) indica a heterogeneidade interna do grupo.', S['body']))

    story += [Paragraph('2.4  Atribuição de Pesquisador', S['h2'])]
    story.append(Paragraph(
        'Cada linha agregada lista o pesquisador (<i>nome_completo</i>) '
        'responsável pelo grupo. A busca percorre a hierarquia taxonômica a partir '
        'do próprio rank da linha e sobe até encontrar um pesquisador responsável. '
        'Quando o pesquisador é encontrado em rank superior ao da linha, a célula '
        'é anotada com "(via &lt;rank&gt;)" para tornar a delegação visível.',
        S['body']))

    story += [Paragraph('2.5  Arquivos de Saída', S['h2'])]
    story.append(Paragraph('Os resultados são entregues em um arquivo ZIP contendo:', S['body']))
    story.append(output_table([
        ('completeness.xlsx',  'Seis abas: by_species, by_family, by_order, by_class, by_subclass, by_phylum. Cada aba inclui colunas de contexto taxonômico, contagem de espécies, completude média/mínima/máxima, amplitude e pesquisador responsável.'),
        ('by_family.pdf',      'Gráfico de barras horizontais de completude média por família, ordenado alfabeticamente, com barras de erro mín–máx. A família mais completa é destacada em vermelho.'),
        ('by_order.pdf',       'Mesmo gráfico agregado por ordem.'),
        ('by_class.pdf',       'Mesmo gráfico agregado por classe.'),
        ('by_subclass.pdf',    'Mesmo gráfico agregado por subclasse (omitido se não houver dados de subclasse).'),
        ('by_phylum.pdf',      'Mesmo gráfico agregado por filo (omitido em consultas de filo único).'),
    ], S))

    # ── 3. Completude da Lista ─────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('3. Completude da Lista de Espécies (GBIF)', S['h1']), rule()]
    story.append(Paragraph(
        'Esta análise compara a lista de espécies aceitas no CTFB com as espécies '
        'registradas no Brasil no Global Biodiversity Information Facility (GBIF), '
        'identificando espécies que ocorrem no Brasil mas estão ausentes do '
        'catálogo. A análise é executada em segundo plano e o progresso é '
        'exibido em tempo real na página de status.', S['body']))

    story += [Paragraph('3.1  Como Funciona', S['h2'])]
    story.append(Paragraph('A análise é dividida em quatro fases:', S['body']))

    phases_pt = [
        ('Fase 1 — Resolução do táxon',
         'O nome do táxon informado é resolvido para um identificador interno do '
         'GBIF (<i>usageKey</i>) via a API GBIF Species Match '
         '(api.gbif.org/v1/species/match). Um erro é retornado se o nome não for '
         'encontrado.'),
        ('Fase 2 — Coleta de chaves de espécies',
         'A API de Busca de Ocorrências do GBIF é consultada com os filtros '
         'country=BR e taxonKey=&lt;chave resolvida&gt;, usando facetas no campo '
         'speciesKey para recuperar a lista de todas as espécies com pelo menos '
         'um registro de ocorrência no Brasil. A paginação é aplicada '
         'automaticamente para táxons com mais de 50 000 espécies.'),
        ('Fase 3 — Resolução de nomes',
         'Cada chave de espécie é resolvida para um nome binomial canônico '
         '(gênero + epíteto específico) e sua taxonomia superior (família, ordem, '
         'classe, filo) via a API de Espécies do GBIF. Até 20 requisições '
         'paralelas são feitas simultaneamente, respeitando o limite de taxa do '
         'GBIF. Para táxons grandes, esta é a fase mais demorada.'),
        ('Fase 4 — Comparação com o CTFB',
         'As espécies do CTFB com taxonomicstatus = NOME_ACEITO e '
         'taxonrank = ESPECIE são extraídas e representadas como binômios '
         'canônicos em minúsculas (gênero + specificepithet). Binômios do GBIF '
         'não encontrados nesse conjunto são classificados como ausentes do '
         'catálogo.'),
    ]
    for title, body in phases_pt:
        story += [KeepTogether([
            Paragraph(f'<b>{title}</b>', S['h3']),
            Paragraph(body, S['body']),
        ])]

    story += [Paragraph('3.2  Método de Correspondência e Ressalvas', S['h2'])]
    story.append(Paragraph(
        'A correspondência é feita pelo <b>binômio canônico em minúsculas</b> '
        '(gênero + specificEpithet). Isso significa:', S['body']))
    for bullet in [
        'Espécies com binômios idênticos no GBIF e no CTFB são contadas como presentes, independentemente do autor ou ano.',
        'Discrepâncias nomenclaturais — como sinonímia de gênero, variações ortográficas ou tratamentos taxonômicos diferentes — farão uma espécie aparecer como "ausente" mesmo que esteja representada sob outro nome no CTFB.',
        'Táxons infraespecíficos (subespécies, variedades) são excluídos de ambos os lados da comparação.',
        'Recomenda-se revisão manual da lista de lacunas, especialmente para grupos com instabilidade nomenclatural conhecida.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    story += [Paragraph('3.3  Arquivo de Saída', S['h2'])]
    story.append(Paragraph(
        'Um único arquivo XLSX é gerado com três abas:', S['body']))
    story.append(output_table([
        ('Ausentes_no_CTFB',   'Todas as espécies GBIF (Brasil) ausentes no CTFB, ordenadas por filo → classe → ordem → família → nome. Colunas: phylum_gbif, classe_gbif, ordem_gbif, familia_gbif, nome_cientifico, gbif_species_key.'),
        ('Resumo_por_Familia', 'Resumo por família: número de espécies GBIF ausentes do CTFB, total de espécies GBIF na família e percentual ausente. Ordenado pelo número de espécies ausentes (decrescente).'),
        ('Presentes_no_CTFB',  'Espécies GBIF que foram correspondidas a um registro NOME_ACEITO no CTFB. Útil para verificação cruzada e compreensão da cobertura.'),
    ], S))

    story += [Paragraph('3.4  Tempo Estimado de Execução', S['h2'])]
    time_data = [
        [Paragraph('<b>Escala do táxon</b>', S['body']),
         Paragraph('<b>Espécies GBIF aprox.</b>', S['body']),
         Paragraph('<b>Tempo estimado</b>', S['body'])],
        [Paragraph('Ordem pequena (ex: Nematomorpha)', S['body']),
         Paragraph('< 200', S['body']),
         Paragraph('10–30 segundos', S['body'])],
        [Paragraph('Ordem média (ex: Araneae)', S['body']),
         Paragraph('~5 000', S['body']),
         Paragraph('2–5 minutos', S['body'])],
        [Paragraph('Ordem grande (ex: Coleoptera)', S['body']),
         Paragraph('~100 000', S['body']),
         Paragraph('15–30 minutos', S['body'])],
        [Paragraph('Filo completo (ex: Arthropoda)', S['body']),
         Paragraph('> 200 000', S['body']),
         Paragraph('1–3 horas', S['body'])],
    ]
    tt = Table(time_data, colWidths=[5.5*cm, 4.5*cm, 6*cm])
    tt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BLUE_MID),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(tt)
    story.append(Paragraph(
        'A página de status se atualiza automaticamente a cada 2 segundos e exibe '
        'uma barra de progresso. Você pode fechar a aba e retornar mais tarde; '
        'o processo continua no servidor até a conclusão ou até o próximo '
        'redeploy.', S['note']))

    # ── 4. Administração ───────────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('4. Administração', S['h1']), rule()]
    story.append(Paragraph(
        'Contas de administrador têm acesso ao Painel Admin pelo link no rodapé '
        'da página principal.', S['body']))

    story += [Paragraph('4.1  Gerenciamento de Usuários', S['h2'])]
    for item in [
        ('<b>Importação em lote</b> — cole uma lista de logins da <i>pesquisadores.xlsx</i>. '
         'Cada usuário é criado com o flag "deve definir senha no 1º acesso". '
         'Usuários não encontrados na planilha são rejeitados.'),
        ('<b>Adição individual</b> — crie um único usuário com senha imediatamente utilizável.'),
        ('<b>Exportar CSV</b> — baixe um backup de todas as contas de usuário incluindo '
         'senhas hasheadas. Recomendado antes de cada redeploy quando usando SQLite.'),
        ('<b>Restaurar CSV</b> — reimporte usuários de um CSV exportado anteriormente. '
         'Contas existentes são ignoradas; os hashes de senha são restaurados para '
         'que os usuários não precisem redefinir suas senhas.'),
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))

    story += [Paragraph('4.2  Persistência do Banco de Dados', S['h2'])]
    story.append(Paragraph('O sistema suporta dois backends de banco de dados:', S['body']))
    db_data = [
        [Paragraph('<b>Backend</b>', S['body']),
         Paragraph('<b>Persistência</b>', S['body']),
         Paragraph('<b>Como ativar</b>', S['body'])],
        [Paragraph('PostgreSQL', S['body']),
         Paragraph('Permanente — sobrevive a todos os redeployments.', S['body']),
         Paragraph('Defina a variável de ambiente DATABASE_URL com uma string de conexão postgresql:// (ex: pelo Railway).', S['body'])],
        [Paragraph('SQLite', S['body']),
         Paragraph('Efêmero — dados perdidos a cada redeploy.', S['body']),
         Paragraph('Padrão quando DATABASE_URL não está definida. Um banner de aviso é exibido no Painel Admin.', S['body'])],
    ]
    dbt = Table(db_data, colWidths=[3*cm, 4.5*cm, 8.5*cm])
    dbt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), BLUE_DARK),
        ('TEXTCOLOR',  (0,0), (-1,0), colors.white),
        ('FONTNAME',   (0,0), (-1,0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID', (0,0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING',   (0,0), (-1,-1), 6),
    ]))
    story.append(dbt)

    story += [Paragraph('4.3  Fontes de Dados', S['h2'])]
    story.append(Paragraph(
        'O sistema carrega duas planilhas do Google Sheets na inicialização. Se uma '
        'planilha estiver inacessível (ex: sem conexão), o sistema usa arquivos '
        'XLSX locais armazenados no diretório <i>data/</i> do servidor.', S['body']))
    story.append(output_table([
        ('pesquisadores.xlsx',     'Cadastro de pesquisadores: login, nome_completo, táxons, institution. Controla a autorização de acesso e a atribuição de pesquisador nas tabelas de saída.'),
        ('planilha_extendida.xlsx','Catálogo CTFB estendido com todos os campos Darwin Core e campos manuais. É a fonte de todos os cálculos de completude.'),
    ], S, col1='Arquivo', col2='Conteúdo'))

    # ── 5. Interpretação ───────────────────────────────────────────────────────
    story += [PageBreak(), Paragraph('5. Interpretando os Resultados', S['h1']), rule()]

    story += [Paragraph('5.1  Gráficos de Completude dos Dados', S['h2'])]
    story.append(Paragraph(
        'Cada gráfico PDF exibe uma barra horizontal por grupo taxonômico. O '
        'comprimento da barra representa a completude média (%). As barras de '
        'erro se estendem até os valores mínimo e máximo do grupo. A barra com '
        'a maior média é colorida em vermelho; as demais são azuis. Os valores '
        'são anotados à direita de cada barra.', S['body']))
    story.append(Paragraph(
        'Um grupo com 100% de média e amplitude zero está perfeitamente '
        'homogêneo — todas as espécies têm todos os campos aplicáveis '
        'preenchidos. Uma amplitude grande indica que algumas espécies são '
        'bem documentadas enquanto outras carecem de muitos campos, sinalizando '
        'onde o esforço curatorial deve ser concentrado.', S['body']))

    story += [Paragraph('5.2  Lista de Lacunas de Espécies', S['h2'])]
    story.append(Paragraph(
        'A aba <i>Ausentes_no_CTFB</i> lista espécies candidatas à inclusão no '
        'catálogo. Antes de agir sobre um registro, sempre considere:', S['body']))
    for bullet in [
        'Diferenças nomenclaturais — a espécie pode já estar no CTFB sob um binômio diferente (mas sinônimo).',
        'Escopo taxonômico — as ocorrências do GBIF incluem registros de todos os ambientes; algumas espécies podem ser marinhas e estar fora do escopo atual de cobertura do CTFB.',
        'Qualidade dos registros — alguns registros do GBIF são identificações incorretas ou carecem de precisão de coordenadas. Registros de alta incerteza devem ser verificados.',
        'Táxons infraespecíficos — a análise abrange apenas o nível de espécie; subespécies ausentes do CTFB não são sinalizadas.',
    ]:
        story.append(Paragraph(f'• {bullet}', S['bullet']))

    # ── Rodapé ─────────────────────────────────────────────────────────────────
    story += [
        Spacer(1, 1.5*cm),
        section_rule(),
        Paragraph(
            'Problemas ou dúvidas? Escreva para '
            '<font name="Courier">faunadobrasilctfb@gmail.com</font>',
            S['footer']),
        Spacer(1, 0.15*cm),
        Paragraph('Porcentômetro · CTFB · Abril de 2026 · Edição em português', S['footer']),
    ]

    doc.build(story)
    print(f'✓ Portuguese manual written to {path}')


if __name__ == '__main__':
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    build_english(os.path.join(out_dir, 'manual_en.pdf'))
    build_portuguese(os.path.join(out_dir, 'manual_pt.pdf'))
