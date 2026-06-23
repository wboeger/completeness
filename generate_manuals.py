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

W, H = A4
MARGIN = 2.2 * cm
APP_URL = 'https://comfortable-emotion-production-e366.up.railway.app/'

BLUE_DARK  = colors.HexColor('#1a3a5c')
BLUE_MID   = colors.HexColor('#2980b9')
BLUE_LIGHT = colors.HexColor('#eaf4fd')
GREY_LIGHT = colors.HexColor('#f4f6f9')
GREY_MID   = colors.HexColor('#7f8c8d')
GREEN      = colors.HexColor('#27ae60')
ORANGE     = colors.HexColor('#e67e22')
RED        = colors.HexColor('#c0392b')

def make_styles():
    S = {}
    S['title'] = ParagraphStyle('title', fontName='Helvetica-Bold', fontSize=26,
                                 textColor=BLUE_DARK, leading=32, spaceAfter=6, alignment=TA_CENTER)
    S['subtitle'] = ParagraphStyle('subtitle', fontName='Helvetica', fontSize=13,
                                    textColor=GREY_MID, leading=18, spaceAfter=4, alignment=TA_CENTER)
    S['version'] = ParagraphStyle('version', fontName='Helvetica', fontSize=10,
                                   textColor=GREY_MID, leading=14, spaceAfter=2, alignment=TA_CENTER)
    S['h1'] = ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=16,
                              textColor=BLUE_DARK, leading=22, spaceBefore=18, spaceAfter=6)
    S['h2'] = ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=13,
                              textColor=BLUE_MID, leading=18, spaceBefore=14, spaceAfter=4)
    S['h3'] = ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=11,
                              textColor=BLUE_DARK, leading=16, spaceBefore=10, spaceAfter=3)
    S['body'] = ParagraphStyle('body', fontName='Helvetica', fontSize=10,
                                textColor=colors.black, leading=15, spaceAfter=6, alignment=TA_JUSTIFY)
    S['bullet'] = ParagraphStyle('bullet', fontName='Helvetica', fontSize=10,
                                  textColor=colors.black, leading=14, spaceAfter=3,
                                  leftIndent=14, firstLineIndent=-10)
    S['code'] = ParagraphStyle('code', fontName='Courier', fontSize=8.5,
                                textColor=colors.HexColor('#2c3e50'), leading=13,
                                spaceAfter=3, leftIndent=12, backColor=GREY_LIGHT, borderPad=4)
    S['note'] = ParagraphStyle('note', fontName='Helvetica-Oblique', fontSize=9.5,
                                textColor=colors.HexColor('#6d4a00'), leading=14,
                                spaceAfter=4, leftIndent=8)
    S['footer'] = ParagraphStyle('footer', fontName='Helvetica', fontSize=8,
                                  textColor=GREY_MID, alignment=TA_CENTER)
    S['url_label'] = ParagraphStyle('url_label', fontName='Helvetica-Bold', fontSize=9,
                                     textColor=colors.HexColor('#1a5276'),
                                     leading=13, spaceAfter=2, alignment=TA_CENTER)
    S['url_link'] = ParagraphStyle('url_link', fontName='Courier-Bold', fontSize=12,
                                    textColor=BLUE_MID, leading=18, spaceAfter=0, alignment=TA_CENTER)
    return S


def url_box(label, S):
    inner = Table(
        [[Paragraph(label, S['url_label'])],
         [Paragraph(f'<link href="{APP_URL}" color="#2980b9">{APP_URL}</link>', S['url_link'])]],
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

def _grid_style(header_color):
    return TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), header_color),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, 0), 9),
        ('ROWBACKGROUNDS',(0, 1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID',          (0, 0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN',        (0, 0), (-1,-1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1,-1), 4),
        ('BOTTOMPADDING', (0, 0), (-1,-1), 4),
        ('LEFTPADDING',   (0, 0), (-1,-1), 6),
    ])

def field_table(rows, S):
    header = [Paragraph('<b>Field</b>', S['body']), Paragraph('<b>Description</b>', S['body'])]
    data = [header] + [[Paragraph(f'<font name="Courier" size="8.5">{r[0]}</font>', S['body']),
                         Paragraph(r[1], S['body'])] for r in rows]
    t = Table(data, colWidths=[4.5*cm, 11.5*cm])
    t.setStyle(_grid_style(BLUE_DARK))
    return t

def field_table_pt(rows, S):
    header = [Paragraph('<b>Campo</b>', S['body']), Paragraph('<b>Descrição</b>', S['body'])]
    data = [header] + [[Paragraph(f'<font name="Courier" size="8.5">{r[0]}</font>', S['body']),
                         Paragraph(r[1], S['body'])] for r in rows]
    t = Table(data, colWidths=[4.5*cm, 11.5*cm])
    t.setStyle(_grid_style(BLUE_DARK))
    return t

def output_table(rows, S, col1='Sheet / File', col2='Contents'):
    header = [Paragraph(f'<b>{col1}</b>', S['body']), Paragraph(f'<b>{col2}</b>', S['body'])]
    data = [header] + [[Paragraph(f'<font name="Courier" size="8.5">{r[0]}</font>', S['body']),
                         Paragraph(r[1], S['body'])] for r in rows]
    t = Table(data, colWidths=[5*cm, 11*cm])
    t.setStyle(_grid_style(GREEN))
    return t

def steps_table(rows, S):
    t = Table(rows, colWidths=[1*cm, W - 2*MARGIN - 1.4*cm])
    t.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING',    (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING',   (0, 0), (0, -1),  0),
        ('LEFTPADDING',   (1, 0), (1, -1),  8),
        ('ROWBACKGROUNDS',(0, 0), (-1, -1), [colors.white, GREY_LIGHT]),
        ('BOX',           (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
        ('GRID',          (0, 0), (-1, -1), 0.4, colors.HexColor('#dce1e7')),
    ]))
    return t

def excl_table(rows, S):
    t = Table(rows, colWidths=[4.5*cm, 4.5*cm, 7*cm])
    t.setStyle(_grid_style(ORANGE))
    return t

def time_table(rows, S):
    t = Table(rows, colWidths=[5.5*cm, 4.5*cm, 6*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, 0), BLUE_MID),
        ('TEXTCOLOR',     (0, 0), (-1, 0), colors.white),
        ('FONTNAME',      (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('ROWBACKGROUNDS',(0, 1), (-1,-1), [colors.white, GREY_LIGHT]),
        ('GRID',          (0, 0), (-1,-1), 0.4, colors.HexColor('#dce1e7')),
        ('VALIGN',        (0, 0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1,-1), 5),
        ('BOTTOMPADDING', (0, 0), (-1,-1), 5),
        ('LEFTPADDING',   (0, 0), (-1,-1), 6),
    ]))
    return t

def db_table(rows, S):
    t = Table(rows, colWidths=[3*cm, 4*cm, 9*cm])
    t.setStyle(_grid_style(BLUE_DARK))
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

    # Cover
    story += [
        Spacer(1, 2*cm),
        Paragraph('Porcentômetro', S['title']),
        Paragraph('Completeness Assessment System', S['subtitle']),
        Paragraph('Catálogo Taxonômico da Fauna do Brasil (CTFB)', S['subtitle']),
        Spacer(1, 0.4*cm), rule(), Spacer(1, 0.3*cm),
        Paragraph('User Manual — English', S['version']),
        Paragraph('Version 2.1 · April 2026', S['version']),
        Spacer(1, 1.2*cm),
        url_box('Access the application at:', S),
        Spacer(1, 2*cm),
        Paragraph(
            'The <b>Porcentômetro</b> is a web tool developed for the '
            '<i>Catálogo Taxonômico da Fauna do Brasil</i> (CTFB). It provides two '
            'complementary analyses: (1) <b>Data Completeness</b> — how thoroughly '
            'mandatory fields are filled in for catalogued species; and (2) '
            '<b>Species-List Completeness</b> — a comparison of CTFB records against '
            'the Global Biodiversity Information Facility (GBIF) to identify species '
            'known from Brazil that are absent from the catalogue.', S['body']),
        PageBreak(),
    ]

    # 1. Accessing
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
        'have a password assigned yet. On first login the system detects this and '
        'redirects you to a password-creation screen. Follow the steps below:',
        S['body']))
    story.append(steps_table([
        [Paragraph('<b>1</b>', S['body']),
         Paragraph('Open the URL and type your username. Leave the password field '
                   '<b>empty</b> and click <i>Login</i> (any value is ignored at this stage).',
                   S['body'])],
        [Paragraph('<b>2</b>', S['body']),
         Paragraph('The system redirects you to the <b>Set Password</b> screen with a '
                   'welcome message.', S['body'])],
        [Paragraph('<b>3</b>', S['body']),
         Paragraph('Enter a new password of <b>at least 6 characters</b>, retype it, '
                   'then click <i>Set password and continue</i>.', S['body'])],
        [Paragraph('<b>4</b>', S['body']),
         Paragraph('If the entries match and are long enough, you are immediately logged '
                   'in and taken to the main page.', S['body'])],
        [Paragraph('<b>5</b>', S['body']),
         Paragraph('From this point on, use your username and the new password for every '
                   'subsequent login.', S['body'])],
    ], S))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'If the passwords do not match or are shorter than 6 characters, an error '
        'is shown on the same screen and you may try again. No data is lost.',
        S['note']))

    story += [Paragraph('1.3  Forgotten Password', S['h2'])]
    story.append(Paragraph(
        'If you forget your password, you cannot reset it yourself. Two recovery options:',
        S['body']))
    for b in [
        '<b>Contact your administrator</b> — next to your account in the Admin Dashboard the '
        'administrator can either <i>Reset password</i> (clears it and sets the "must set '
        'password" flag, so your next login follows the first-access flow) or <i>Set '
        'password</i> directly to a new working password they give you, which you can change '
        'afterwards (see §1.5).',
        '<b>Write to support</b> — e-mail '
        '<font name="Courier">faunadobrasilctfb@gmail.com</font> with your username. '
        'The team will ask an administrator to reset your account.',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [Paragraph('1.4  Main Page', S['h2'])]
    story.append(Paragraph(
        'After login the main page shows the analysis-type cards. Click one, enter a '
        'taxon name in the text field (or click a chip from your authorised taxa list '
        'to fill it automatically), then press the action button. The footer also offers '
        'a <i>Manual</i> link (opens this manual in your language) and a <i>Change '
        'password</i> link (see §1.5).', S['body']))
    story.append(Paragraph(
        'The login page and the main page both display the date of the catalogue copy '
        'currently in use (and the researcher-registry date). The catalogue is refreshed '
        'automatically from the official JBRJ Fauna do Brasil source — see §4.4.',
        S['note']))

    story += [Paragraph('1.5  Changing Your Password', S['h2'])]
    story.append(Paragraph(
        'Once logged in you can change your own password at any time. Click <i>Change '
        'password</i> in the main-page footer, enter your current password, then the new '
        'password twice (at least 6 characters) and confirm. The change takes effect '
        'immediately and is used on every subsequent login. This works both for passwords '
        'you created yourself and for a password an administrator set for you.', S['body']))

    # 2. Data Completeness
    story += [PageBreak(), Paragraph('2. Data Completeness Analysis', S['h1']), rule()]
    story.append(Paragraph(
        'This analysis evaluates the fraction of mandatory fields filled in for each '
        'accepted species (<i>taxonomicstatus = ACCEPTED</i>, <i>taxonrank = SPECIES</i> '
        'or <i>SUBSPECIES</i>) within the requested taxon. '
        '<b>Subspecies rule:</b> when a species has one or more accepted subspecies, '
        'the species-level row is excluded and only its subspecies are used as analysis '
        'units. Results are aggregated by family, order, class, sub-class, and phylum. '
        'When the input taxon is a family, an additional breakdown by genus is produced.',
        S['body']))
    story.append(Paragraph(
        'The analysis runs in the background on the server. After you submit, a status '
        'page is shown with a progress indicator and refreshes automatically; when the '
        'analysis finishes it redirects to the results page. Large taxa (e.g. Hexapoda, '
        'Coleoptera) may take several minutes — you can leave the tab open and the page '
        'will advance on its own. If anything fails, the error is shown on the status '
        'page instead of interrupting the application.', S['note']))

    story += [Paragraph('2.1  The 15 Evaluated Fields', S['h2'])]
    story.append(Paragraph(
        'The following fields are evaluated for every species (subject to ecological '
        'exclusion rules in §2.2):', S['body']))
    story.append(field_table([
        ('bibliographicreference', 'Primary bibliographic reference for the taxon.'),
        ('country',                'Country of occurrence (Brazil = BR).'),
        ('establishmentmeans',     'Native, invasive, introduced, etc.'),
        ('endemicbrazil',          'Whether the species is endemic to Brazil.'),
        ('environment',            'Environment type: epicontinental, marinho, or both.'),
        ('locality',               'Occurrence locality description.'),
        ('epicontinentaldomain',   'Phytogeographic domain (freshwater / terrestrial species).'),
        ('marinedomain',           'Marine biogeographic province (marine species).'),
        ('lifeform',               'Life-form / feeding guild.'),
        ('habitat',                'Habitat description.'),
        ('vernacularname',         'Common name in Portuguese.'),
        ('vernacularnamelanguage', 'Language of the common name.'),
        ('vernacularnamelocality', 'Region to which the common name applies.'),
        ('animalhostnames',        'Animal host species (see §2.2 for exclusion rules).'),
        ('vegetalhostnames',       'Plant host species (see §2.2 for exclusion rules).'),
    ], S))

    story += [Spacer(1, 0.4*cm), Paragraph('2.2  Ecological Exclusion Rules', S['h2'])]
    story.append(Paragraph(
        'Certain fields are excluded from both the numerator and the denominator '
        'when they are biologically inapplicable. The applicable denominator therefore '
        'varies per species. Lifeform detection uses substring matching to handle '
        'compound values (e.g. <font name="Courier" size="9">herbivoro;vida livre individual</font>).', S['body']))

    story += [Paragraph('Domain and country fields', S['h3'])]
    story.append(excl_table([
        [Paragraph('<b>Field excluded</b>', S['body']),
         Paragraph('<b>Condition</b>', S['body']),
         Paragraph('<b>Rationale</b>', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">marinedomain</font>', S['body']),
         Paragraph('environment = <i>epicontinental</i>', S['body']),
         Paragraph('A freshwater/terrestrial species has no marine biogeographic province.', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">epicontinentaldomain</font>', S['body']),
         Paragraph('environment = <i>marinho</i>', S['body']),
         Paragraph('A strictly marine species has no continental phytogeographic domain.', S['body'])],
        [Paragraph('one of the two domain fields', S['body']),
         Paragraph('environment = <i>vazio</i> or blank', S['body']),
         Paragraph('Always exactly ONE domain slot per species. For unknown environment, '
                   'the filled domain is kept; if both or neither are filled, '
                   '<i>marinedomain</i> is dropped by default. '
                   'Additionally, <i>environment</i> itself is treated as not filled when its value is "vazio".', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">country</font>', S['body']),
         Paragraph('endemicbrazil = <i>SIM</i>', S['body']),
         Paragraph('Species endemic to Brazil always occur in Brazil — the field adds no information.', S['body'])],
    ], S))
    story.append(Spacer(1, 0.25*cm))

    story += [Paragraph('Host fields', S['h3'])]
    story.append(Paragraph(
        'The treatment of <font name="Courier" size="9">animalhostnames</font> and '
        '<font name="Courier" size="9">vegetalhostnames</font> depends on the '
        '<font name="Courier" size="9">lifeform</font> value (substring match applied '
        'to handle compound lifeform strings):', S['body']))

    host_data = [
        [Paragraph('<b>lifeform value</b>', S['body']),
         Paragraph('<b>Treatment</b>', S['body'])],
        [Paragraph('contains <i>endoparasito</i> or <i>ectoparasito</i>', S['body']),
         Paragraph('Both columns are merged into <b>one combined host slot</b>. '
                   'The slot counts as filled if <i>either</i> column is non-empty; '
                   'blank if both are empty. The denominator gains 1 (not 2).', S['body'])],
        [Paragraph('contains <i>herbivoro</i> (non-parasite)', S['body']),
         Paragraph('<font name="Courier" size="8.5">animalhostnames</font> is excluded '
                   '(herbivores feed on plants). '
                   '<font name="Courier" size="8.5">vegetalhostnames</font> is evaluated normally.', S['body'])],
        [Paragraph('contains <i>vida livre individual</i> (non-parasite)', S['body']),
         Paragraph('Both host columns are excluded — free-living species do not have hosts.', S['body'])],
        [Paragraph('blank / not filled', S['body']),
         Paragraph('Both host columns are excluded — lifeform unknown, host relationship undefined.', S['body'])],
        [Paragraph('any other value (e.g. <i>predador, colonial, sessil</i>)', S['body']),
         Paragraph('Both <font name="Courier" size="8.5">animalhostnames</font> and '
                   '<font name="Courier" size="8.5">vegetalhostnames</font> are '
                   '<b>included normally</b> in the denominator.', S['body'])],
    ]
    ht = Table(host_data, colWidths=[5*cm, 11*cm])
    ht.setStyle(_grid_style(BLUE_MID))
    story.append(ht)

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        'Examples: (1) A freshwater beetle (<i>environment = epicontinental</i>) is '
        'scored over 14 fields — <i>marinedomain</i> removed. (2) An endoparasite '
        'is scored over 14 fields — the two host columns are replaced by one combined '
        'slot. (3) A free-living predator (<i>lifeform = predador</i>) is scored over '
        '15 fields — both host columns count normally. (4) A species with '
        '<i>lifeform = vida livre individual</i> is scored over 13 fields — both host '
        'columns excluded. (5) A Brazilian endemic (<i>endemicbrazil = SIM</i>) is '
        'scored over one fewer field — <i>country</i> removed.', S['note']))

    story += [Paragraph('2.3  Completeness Formula', S['h2'])]
    story.append(Paragraph('For each species / subspecies the score is:', S['body']))
    story.append(Paragraph(
        'completeness (%) = (filled applicable fields) / (applicable fields) × 100',
        S['code']))
    story.append(Paragraph(
        'Results are aggregated per taxonomic group as mean, minimum, and maximum '
        'completeness across all units in that group. '
        '<b>Amplitude</b> (max − min) measures within-group heterogeneity.',
        S['body']))

    story += [Paragraph('2.4  Subspecies Rule', S['h2'])]
    story.append(Paragraph(
        'When a species has at least one accepted subspecies '
        '(<i>taxonrank = SUBSPECIES, taxonomicstatus = ACCEPTED</i>), the '
        'species-level row is <b>excluded</b> from the analysis and its accepted '
        'subspecies are used as the analysis units instead. This ensures that the '
        'completeness is measured at the finest accepted resolution available for '
        'each lineage.', S['body']))

    story += [Paragraph('2.5  Researcher Attribution', S['h2'])]
    story.append(Paragraph(
        'Each aggregated row lists the researcher (<i>nome_completo</i>) responsible '
        'for that group. The lookup starts at the group\'s own rank and climbs the '
        'hierarchy until a responsible researcher is found. When resolved above the '
        'row\'s rank, the cell is annotated with "(via &lt;rank&gt;)" to make '
        'delegation transparent.', S['body']))

    story += [Paragraph('2.6  Output Files', S['h2'])]
    story.append(Paragraph('Results are packaged in a ZIP file containing:', S['body']))
    story.append(output_table([
        ('completeness_per_species.xlsx',
         'One row per species / subspecies: taxon_analisado, taxonomic context, '
         'taxonrank, completeness (%), filled_count, total_applicable, pesquisador.'),
        ('completeness_by_genus.xlsx',
         'Aggregation by genus (only when the input taxon is a family): '
         'n_spp_ctfb, mean/min/max completeness, amplitude, pesquisador.'),
        ('completeness_by_family.xlsx',
         'Aggregation by family: same columns as above.'),
        ('completeness_by_order.xlsx',   'Aggregation by order.'),
        ('completeness_by_class.xlsx',   'Aggregation by class.'),
        ('completeness_by_subclass.xlsx','Aggregation by subclass (omitted if no subclass data).'),
        ('completeness_by_phylum.xlsx',  'Aggregation by phylum (omitted for single-phylum queries).'),
        ('completeness_histograms_genus.pdf',
         'Horizontal bar chart of mean completeness by genus '
         '(only when input is a family), with min–max error bars.'),
        ('completeness_histograms_family.pdf',
         'Horizontal bar chart by family. The highest-mean bar is coloured red.'),
        ('completeness_histograms_order.pdf',    'Same chart by order.'),
        ('completeness_histograms_class.pdf',    'Same chart by class.'),
        ('completeness_histograms_subclass.pdf', 'Same chart by subclass.'),
        ('completeness_histograms_phylum.pdf',   'Same chart by phylum.'),
    ], S))

    # 3. GBIF
    story += [PageBreak(), Paragraph('3. Species-List Completeness (GBIF)', S['h1']), rule()]
    story.append(Paragraph(
        'This analysis compares the CTFB accepted species list against species '
        'recorded in Brazil on GBIF, identifying species that occur in Brazil '
        'but are absent from the catalogue. The job runs in the background; '
        'the status page auto-refreshes every 2 seconds.', S['body']))

    story += [Paragraph('3.1  How It Works — Four Phases', S['h2'])]
    for title, body in [
        ('Phase 1 — Taxon resolution',
         'The taxon name is resolved to a GBIF internal identifier (<i>usageKey</i>) '
         'via the GBIF Species Match API (api.gbif.org/v1/species/match). '
         'An error is returned if the name is not recognised.'),
        ('Phase 2 — Species key collection',
         'The GBIF Occurrence Search API is queried with filters country=BR and '
         'taxonKey=&lt;resolved key&gt;, using facets on speciesKey to retrieve all '
         'species with at least one occurrence record in Brazil. Pagination is applied '
         'automatically for taxa with more than 50 000 species.'),
        ('Phase 3 — Name resolution',
         'Each species key is resolved to a canonical binomial (genus + specific '
         'epithet) and its higher taxonomy (family, order, class, phylum) via the '
         'GBIF Species API. Up to 20 parallel requests run simultaneously. '
         'Fossil / extinct species (<i>extinct = true</i> in GBIF) are excluded at '
         'this stage.'),
        ('Phase 4 — Comparison with CTFB',
         'CTFB species with <i>taxonomicstatus = ACCEPTED</i> and '
         '<i>taxonrank = SPECIES</i> are extracted as lowercase canonical binomials. '
         'Each GBIF binomial is classified as: <b>present</b> (matched to an accepted '
         'name), <b>synonym</b> (matched to a synonym in CTFB), or '
         '<b>absent</b> (not found in any form).'),
    ]:
        story.append(KeepTogether([
            Paragraph(f'<b>{title}</b>', S['h3']),
            Paragraph(body, S['body']),
        ]))

    story += [Paragraph('3.2  Matching and Caveats', S['h2'])]
    story.append(Paragraph(
        'Matching is performed on the <b>lowercase canonical binomial</b>. '
        'Key caveats:', S['body']))
    for b in [
        'Species with identical binomials in GBIF and CTFB are counted as present, regardless of author or year.',
        'A GBIF name matched to a CTFB synonym (non-ACCEPTED record with the same binomial) is classified as <i>Sinonimos_no_CTFB</i>, not as absent.',
        'Nomenclatural discrepancies — genus synonymy, spelling variants, different taxonomic treatments — cause a species to appear "absent" even if represented under a different name in CTFB. Manual review is recommended.',
        'Infraspecific taxa (subspecies, varieties) are excluded from both sides of the comparison.',
        'Fossil taxa are excluded (GBIF <i>extinct = true</i>).',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [Paragraph('3.3  Output File', S['h2'])]
    story.append(Paragraph('A single XLSX file with four sheets:', S['body']))
    story.append(output_table([
        ('Ausentes_no_CTFB',
         'GBIF species (Brazil, non-fossil) absent from CTFB in any form. '
         'Columns: phylum_gbif, classe_gbif, ordem_gbif, familia_gbif, '
         'nome_cientifico, gbif_species_key. Sorted phylum → class → order → family → name.'),
        ('Sinonimos_no_CTFB',
         'GBIF species whose binomial matches a synonym (non-ACCEPTED) record in CTFB. '
         'Same columns as Ausentes_no_CTFB.'),
        ('Resumo_por_Familia',
         'Summary per family: total GBIF species, absent count, synonym count, '
         'present count. Sorted by absent count descending.'),
        ('Presentes_no_CTFB',
         'GBIF species matched to a CTFB ACCEPTED record. Useful for coverage '
         'cross-checking.'),
    ], S))

    story += [Paragraph('3.4  Expected Run Time', S['h2'])]
    story.append(time_table([
        [Paragraph('<b>Taxon scale</b>', S['body']),
         Paragraph('<b>Approx. GBIF species</b>', S['body']),
         Paragraph('<b>Estimated time</b>', S['body'])],
        [Paragraph('Small order (e.g. Nematomorpha)', S['body']), Paragraph('< 200', S['body']),    Paragraph('10–30 seconds', S['body'])],
        [Paragraph('Medium order (e.g. Araneae)',     S['body']), Paragraph('~5 000', S['body']),   Paragraph('2–5 minutes', S['body'])],
        [Paragraph('Large order (e.g. Coleoptera)',   S['body']), Paragraph('~100 000', S['body']), Paragraph('15–30 minutes', S['body'])],
        [Paragraph('Full phylum (e.g. Arthropoda)',   S['body']), Paragraph('> 200 000', S['body']),Paragraph('1–3 hours', S['body'])],
    ], S))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'You may close the tab and return later; the job continues server-side until '
        'completion or the next redeployment.', S['note']))

    # 4. Administration
    story += [PageBreak(), Paragraph('4. Administration', S['h1']), rule()]
    story.append(Paragraph(
        'Administrator accounts access the Admin Dashboard via the link at the bottom '
        'of the main page.', S['body']))

    story += [Paragraph('4.1  User Management', S['h2'])]
    for item in [
        '<b>Bulk import</b> — paste a list of usernames from <i>pesquisadores.xlsx</i>. '
        'Each user is created with the "must set password" flag. '
        'Usernames not found in the spreadsheet are rejected.',
        '<b>Individual add</b> — create a single user with an immediately usable password.',
        '<b>Export CSV</b> — download a backup of all user accounts including hashed passwords. '
        'Commit this file (<i>users_backup.csv</i>) to the repository before every redeployment '
        'so that users are automatically restored on startup.',
        '<b>Restore CSV</b> — re-import users from a previously exported CSV. '
        'Existing accounts are skipped; hashed passwords are restored.',
        '<b>Reset password</b> — clears a user\'s password and sets the '
        '"must set password" flag. The user follows the first-access flow on next login.',
        '<b>Set password</b> — set a specific, immediately usable password for a user '
        'directly (no first-access flow). Useful for users who already completed first '
        'access. The user can change it afterwards (§1.5).',
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))
    story.append(Paragraph(
        '<b>Automatic seed on startup:</b> at every startup the application reads '
        '<font name="Courier">users_backup.csv</font> from the project root and inserts '
        'any user that does not yet exist in the database (existing accounts and passwords '
        'are never overwritten). Export and commit this file after adding or changing users '
        'to guarantee they survive redeployments.', S['note']))

    story += [Paragraph('4.2  Database Persistence', S['h2'])]
    story.append(db_table([
        [Paragraph('<b>Backend</b>', S['body']),
         Paragraph('<b>Persistence</b>', S['body']),
         Paragraph('<b>How to activate</b>', S['body'])],
        [Paragraph('PostgreSQL', S['body']),
         Paragraph('Permanent — survives all redeployments.', S['body']),
         Paragraph('Set DATABASE_URL to a postgresql:// connection string (e.g. from Railway).', S['body'])],
        [Paragraph('SQLite on a volume', S['body']),
         Paragraph('Permanent — stored on a mounted persistent volume.', S['body']),
         Paragraph('Default: the database file lives in the <i>data/</i> directory. When that '
                   'directory is a mounted volume (e.g. Railway volume at /app/data), it survives '
                   'redeployments. The Admin Dashboard confirms "SQLite on a persistent volume".', S['body'])],
        [Paragraph('SQLite (ephemeral)', S['body']),
         Paragraph('Ephemeral — lost on each redeployment.', S['body']),
         Paragraph('Occurs only if the <i>data/</i> directory is not on a persistent volume. '
                   'A warning banner appears on the Admin Dashboard.', S['body'])],
    ], S))

    story += [Paragraph('4.3  Data Sources', S['h2'])]
    story.append(Paragraph(
        'Two datasets are loaded on startup, both from the official JBRJ Fauna do Brasil '
        'APIs. The <b>catalogue</b> is downloaded directly; the <b>researcher registry</b> '
        'is built by merging the live JBRJ contribution report with a curated Google Sheet '
        '(see §4.4). Each result is cached to the <i>data/</i> directory after a successful '
        'load, and the cached copy is used automatically if a source is temporarily '
        'unreachable.', S['body']))
    story.append(output_table([
        ('planilha_extendida.csv',
         'Extended CTFB catalogue (Darwin Core + manual fields). Downloaded from the '
         'JBRJ Fauna do Brasil PostgREST API '
         '(<font name="Courier" size="8">fauna.jbrj.gov.br/rest/mv_planilha_extendida</font>), '
         'paginated in pages of 5 000 records. Source for all completeness calculations.'),
        ('pesquisadores.xlsx',
         'Researcher registry: login, nome_completo, táxons, institution, email. '
         'login / nome_completo / e-mail and the assigned taxa come from the JBRJ '
         'contribution report; <i>institution</i> comes from the curated Google Sheet. '
         'Drives authorisation and researcher attribution.'),
    ], S, col1='File', col2='Contents'))

    story += [Paragraph('4.4  Keeping the Data Up to Date', S['h2'])]
    story.append(Paragraph(
        'Both the catalogue and the researcher registry are served from a recent copy of '
        'the official JBRJ sources, kept current automatically — no manual upload is '
        'required.', S['body']))
    for item in [
        '<b>On every startup, and again daily at 03:00 (America/São_Paulo)</b>, a scheduled '
        'job re-downloads the catalogue and the researcher contribution report and reloads '
        'both into memory, so a long-running instance never drifts out of date. '
        '(The scheduler can be disabled with the <i>ENABLE_SCHEDULER=0</i> environment '
        'variable.)',
        '<b>Catalogue</b> — downloaded in full from the Fauna do Brasil API. The download '
        'is atomic and fail-safe: the new file replaces the previous one only after a '
        'complete, successful download; if the API is unreachable or returns no rows, the '
        'last good cached copy is kept and analyses continue uninterrupted.',
        '<b>Researcher registry</b> — login, nome_completo, e-mail and the taxa assigned '
        'to each researcher are taken from the JBRJ contribution report '
        '(<font name="Courier" size="8">mv_relatorio_contribuicao_usuarios</font>); the '
        '<i>institution</i> field and any researcher not present in the report are merged '
        'in from the curated Google Sheet. If a researcher has no taxa in the report, the '
        'taxa from the sheet are kept as a fallback.',
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))
    story.append(Paragraph(
        'The dates of the catalogue and researcher-registry copies currently in use are '
        'shown to every user on both the login page and the main page (e.g. '
        '<i>Catalogue: 2026-06-22 · Researchers: 2026-06-22</i>), so you can always '
        'confirm how fresh the data is.', S['note']))

    # 5. Interpreting
    story += [PageBreak(), Paragraph('5. Interpreting Results', S['h1']), rule()]

    story += [Paragraph('5.1  Data Completeness Charts', S['h2'])]
    story.append(Paragraph(
        'Each PDF shows a horizontal bar per taxon. Bar length = mean completeness (%). '
        'Error bars extend to the minimum and maximum within the group. The highest-mean '
        'bar is coloured red; all others are blue. Percentages are annotated to the right.',
        S['body']))
    story.append(Paragraph(
        'A group with 100% mean and zero amplitude is perfectly homogeneous. '
        'Wide amplitude signals that some species are well-documented while others '
        'lack many fields — indicating where curatorial effort should be directed.',
        S['body']))

    story += [Paragraph('5.2  Species Gap List', S['h2'])]
    story.append(Paragraph(
        'The <i>Ausentes_no_CTFB</i> sheet lists candidate species for inclusion. '
        'Before acting on any entry, consider:', S['body']))
    for b in [
        'Nomenclatural differences — the species may already be in CTFB under a synonymous binomial (check <i>Sinonimos_no_CTFB</i> first).',
        'Taxonomic scope — some GBIF records may refer to marine species outside CTFB\'s current coverage.',
        'Record quality — some GBIF records are misidentified or poorly georeferenced. High-uncertainty records should be verified.',
        'Subspecific taxa — the GBIF comparison covers species level only.',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [
        Spacer(1, 1.5*cm), section_rule(),
        Paragraph('Problems or questions? Write to '
                  '<font name="Courier">faunadobrasilctfb@gmail.com</font>', S['footer']),
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

    # Capa
    story += [
        Spacer(1, 2*cm),
        Paragraph('Porcentômetro', S['title']),
        Paragraph('Sistema de Avaliação da Completude', S['subtitle']),
        Paragraph('Catálogo Taxonômico da Fauna do Brasil (CTFB)', S['subtitle']),
        Spacer(1, 0.4*cm), rule(), Spacer(1, 0.3*cm),
        Paragraph('Manual do Usuário — Português', S['version']),
        Paragraph('Versão 2.1 · Abril de 2026', S['version']),
        Spacer(1, 1.2*cm),
        url_box('Acesse a aplicação em:', S),
        Spacer(1, 2*cm),
        Paragraph(
            'O <b>Porcentômetro</b> é uma ferramenta web desenvolvida para o '
            '<i>Catálogo Taxonômico da Fauna do Brasil</i> (CTFB). Oferece dois tipos '
            'de análise complementares: (1) <b>Completude dos Dados</b> — grau de '
            'preenchimento dos campos obrigatórios das espécies catalogadas; e '
            '(2) <b>Completude da Lista de Espécies</b> — comparação dos registros '
            'do CTFB com o Global Biodiversity Information Facility (GBIF) para '
            'identificar espécies do Brasil ausentes no catálogo.', S['body']),
        PageBreak(),
    ]

    # 1. Acesso
    story += [Paragraph('1. Acesso ao Sistema', S['h1']), rule()]
    story.append(url_box('Acesse a aplicação em qualquer navegador moderno:', S))
    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        'Você verá a tela de login. Informe seu usuário e senha. Se este for seu '
        'primeiro acesso após ser cadastrado por um administrador, o sistema '
        'pedirá que você crie sua própria senha antes de continuar.', S['body']))

    story += [Paragraph('1.1  Autorização de Acesso', S['h2'])]
    story.append(Paragraph(
        'Cada usuário está associado a um ou mais táxons da planilha de pesquisadores '
        '(<i>pesquisadores.xlsx</i>). Você pode analisar qualquer táxon de sua área '
        'de responsabilidade e todos os grupos subordinados. Usuários vinculados a '
        '<i>Animalia</i> têm acesso a todo o catálogo. Administradores podem analisar '
        'qualquer táxon.', S['body']))

    story += [Paragraph('1.2  Primeiro Acesso — Criação de Senha', S['h2'])]
    story.append(Paragraph(
        'Usuários cadastrados pelo administrador via importação em lote <b>não possuem '
        'senha definida</b>. No primeiro acesso o sistema detecta isso e redireciona '
        'para a tela de criação de senha. Siga os passos:', S['body']))
    story.append(steps_table([
        [Paragraph('<b>1</b>', S['body']),
         Paragraph('Abra a URL e informe seu login. Deixe o campo de senha <b>em branco</b> '
                   '(ou qualquer valor — será ignorado) e clique em <i>Entrar</i>.', S['body'])],
        [Paragraph('<b>2</b>', S['body']),
         Paragraph('O sistema redireciona para a tela <b>Definir Senha</b> com uma '
                   'mensagem de boas-vindas.', S['body'])],
        [Paragraph('<b>3</b>', S['body']),
         Paragraph('Digite uma nova senha com <b>no mínimo 6 caracteres</b>, repita-a '
                   'e clique em <i>Definir senha e entrar</i>.', S['body'])],
        [Paragraph('<b>4</b>', S['body']),
         Paragraph('Se as senhas coincidirem e atenderem ao tamanho mínimo, você é '
                   'autenticado e redirecionado para a página principal.', S['body'])],
        [Paragraph('<b>5</b>', S['body']),
         Paragraph('Nos acessos seguintes, use seu login e a senha recém-criada.',
                   S['body'])],
    ], S))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'Se as senhas não coincidirem ou forem curtas demais, uma mensagem de erro '
        'é exibida na mesma tela. Nenhum dado é perdido.', S['note']))

    story += [Paragraph('1.3  Senha Esquecida', S['h2'])]
    story.append(Paragraph(
        'Não é possível redefinir a senha esquecida por conta própria. Duas opções:', S['body']))
    for b in [
        '<b>Contate o administrador</b> — ao lado da sua conta no Painel Admin, ele pode '
        '<i>Redefinir senha</i> (apaga a senha e ativa o flag "deve definir senha", de modo '
        'que no próximo acesso você segue o fluxo do primeiro acesso) ou <i>Definir senha</i> '
        'diretamente para uma nova senha que ele lhe informa, a qual você pode alterar depois '
        '(ver §1.5).',
        '<b>Escreva para o suporte</b> — envie e-mail para '
        '<font name="Courier">faunadobrasilctfb@gmail.com</font> com seu nome de '
        'usuário. A equipe solicitará ao administrador que redefina seu acesso.',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [Paragraph('1.4  Página Principal', S['h2'])]
    story.append(Paragraph(
        'Após o login, a página principal exibe os cartões de seleção de análise. '
        'Clique no cartão desejado, informe o nome do táxon (ou clique em um dos '
        'botões de táxons autorizados para preenchimento automático) e pressione '
        'o botão de ação. O rodapé também oferece um link <i>Manual</i> (abre este '
        'manual no seu idioma) e um link <i>Alterar senha</i> (ver §1.5).', S['body']))
    story.append(Paragraph(
        'A tela de login e a página principal exibem a data da cópia do catálogo em uso '
        '(e a data do cadastro de pesquisadores). O catálogo é atualizado automaticamente '
        'a partir da fonte oficial da Fauna do Brasil (JBRJ) — ver §4.4.', S['note']))

    story += [Paragraph('1.5  Alterando Sua Senha', S['h2'])]
    story.append(Paragraph(
        'Após autenticado, você pode alterar sua própria senha a qualquer momento. Clique '
        'em <i>Alterar senha</i> no rodapé da página principal, informe a senha atual e, em '
        'seguida, a nova senha duas vezes (no mínimo 6 caracteres) e confirme. A alteração '
        'tem efeito imediato e passa a ser usada em todos os acessos seguintes. Funciona '
        'tanto para senhas que você mesmo criou quanto para uma senha definida por um '
        'administrador.', S['body']))

    # 2. Completude dos Dados
    story += [PageBreak(), Paragraph('2. Análise de Completude dos Dados', S['h1']), rule()]
    story.append(Paragraph(
        'Esta análise avalia a fração de campos obrigatórios preenchidos para cada '
        'espécie aceita (<i>taxonomicstatus = ACCEPTED</i>, '
        '<i>taxonrank = SPECIES</i> ou <i>SUBSPECIES</i>) dentro do táxon solicitado. '
        '<b>Regra de subespécies:</b> quando uma espécie possui subespécies aceitas, '
        'a linha da espécie é excluída e apenas as subespécies são usadas como '
        'unidades de análise. Os resultados são agregados por família, ordem, classe, '
        'subclasse e filo. Quando o táxon de entrada é uma família, é gerada também '
        'uma agregação por gênero.', S['body']))
    story.append(Paragraph(
        'A análise é executada em segundo plano no servidor. Após enviar, uma página de '
        'status é exibida com um indicador de progresso e se atualiza automaticamente; ao '
        'concluir, redireciona para a página de resultados. Táxons grandes (ex: Hexapoda, '
        'Coleoptera) podem levar vários minutos — você pode deixar a aba aberta e a página '
        'avança sozinha. Se algo falhar, o erro é exibido na página de status, sem '
        'interromper a aplicação.', S['note']))

    story += [Paragraph('2.1  Os 15 Campos Avaliados', S['h2'])]
    story.append(Paragraph(
        'Os campos a seguir são avaliados para cada espécie (sujeitos às regras de '
        'exclusão ecológica da §2.2):', S['body']))
    story.append(field_table_pt([
        ('bibliographicreference', 'Referência bibliográfica primária do táxon.'),
        ('country',                'País de ocorrência (Brasil = BR).'),
        ('establishmentmeans',     'Nativa, invasora, introduzida, etc.'),
        ('endemicbrazil',          'Indica se a espécie é endêmica do Brasil.'),
        ('environment',            'Tipo de ambiente: epicontinental, marinho ou ambos.'),
        ('locality',               'Descrição da localidade de ocorrência.'),
        ('epicontinentaldomain',   'Domínio fitogeográfico (espécies dulcícolas/terrestres).'),
        ('marinedomain',           'Província biogeográfica marinha (espécies marinhas).'),
        ('lifeform',               'Forma de vida / guilda alimentar.'),
        ('habitat',                'Descrição do habitat.'),
        ('vernacularname',         'Nome popular em português.'),
        ('vernacularnamelanguage', 'Idioma do nome popular.'),
        ('vernacularnamelocality', 'Região à qual o nome popular se refere.'),
        ('animalhostnames',        'Espécies hospedeiras animais (ver §2.2 para regras de exclusão).'),
        ('vegetalhostnames',       'Espécies hospedeiras vegetais (ver §2.2 para regras de exclusão).'),
    ], S))

    story += [Spacer(1, 0.4*cm), Paragraph('2.2  Regras de Exclusão Ecológica', S['h2'])]
    story.append(Paragraph(
        'Determinados campos são excluídos do numerador e do denominador quando '
        'são biologicamente inaplicáveis. O denominador efetivo varia por espécie. '
        'A detecção de lifeform usa correspondência por substring para lidar com '
        'valores compostos (ex: <font name="Courier" size="9">herbivoro;vida livre individual</font>).',
        S['body']))

    story += [Paragraph('Campos de domínio geográfico e país', S['h3'])]
    story.append(excl_table([
        [Paragraph('<b>Campo excluído</b>', S['body']),
         Paragraph('<b>Condição</b>', S['body']),
         Paragraph('<b>Justificativa</b>', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">marinedomain</font>', S['body']),
         Paragraph('environment = <i>epicontinental</i>', S['body']),
         Paragraph('Espécies dulcícolas/terrestres não possuem província biogeográfica marinha.', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">epicontinentaldomain</font>', S['body']),
         Paragraph('environment = <i>marinho</i>', S['body']),
         Paragraph('Espécies estritamente marinhas não possuem domínio fitogeográfico continental.', S['body'])],
        [Paragraph('um dos dois campos de domínio', S['body']),
         Paragraph('environment = <i>vazio</i> ou em branco', S['body']),
         Paragraph('Sempre exatamente UM slot de domínio por espécie. Para ambiente desconhecido, '
                   'mantém o domínio que estiver preenchido; se ambos ou nenhum estiver preenchido, '
                   '<i>marinedomain</i> é removido por padrão. '
                   'Além disso, o próprio campo <i>environment</i> é tratado como não preenchido '
                   'quando seu valor é "vazio".', S['body'])],
        [Paragraph('<font name="Courier" size="8.5">country</font>', S['body']),
         Paragraph('endemicbrazil = <i>SIM</i>', S['body']),
         Paragraph('Espécies endêmicas do Brasil sempre ocorrem no Brasil — o campo não acrescenta informação.', S['body'])],
    ], S))
    story.append(Spacer(1, 0.25*cm))

    story += [Paragraph('Campos de hospedeiro', S['h3'])]
    story.append(Paragraph(
        'O tratamento de <font name="Courier" size="9">animalhostnames</font> e '
        '<font name="Courier" size="9">vegetalhostnames</font> depende do valor de '
        '<font name="Courier" size="9">lifeform</font> (correspondência por substring '
        'aplicada para lidar com valores compostos):', S['body']))

    host_data_pt = [
        [Paragraph('<b>Valor de lifeform</b>', S['body']),
         Paragraph('<b>Tratamento</b>', S['body'])],
        [Paragraph('contém <i>endoparasito</i> ou <i>ectoparasito</i>', S['body']),
         Paragraph('Os dois campos são fundidos em <b>um único slot de hospedeiro</b>. '
                   'O slot é preenchido se <i>qualquer um</i> não estiver vazio; '
                   'vazio se ambos estiverem em branco. O denominador ganha 1 slot (não 2).', S['body'])],
        [Paragraph('contém <i>herbivoro</i> (não-parasito)', S['body']),
         Paragraph('<font name="Courier" size="8.5">animalhostnames</font> é excluído '
                   '(herbívoros se alimentam de plantas). '
                   '<font name="Courier" size="8.5">vegetalhostnames</font> é avaliado normalmente.', S['body'])],
        [Paragraph('contém <i>vida livre individual</i> (não-parasito)', S['body']),
         Paragraph('Ambos os campos de hospedeiro são excluídos — espécies de vida livre não possuem hospedeiros.', S['body'])],
        [Paragraph('em branco / não preenchido', S['body']),
         Paragraph('Ambos os campos de hospedeiro são excluídos — lifeform desconhecido, relação com hospedeiro indefinida.', S['body'])],
        [Paragraph('qualquer outro valor (ex: <i>predador, colonial, sessil</i>)', S['body']),
         Paragraph('Ambos <font name="Courier" size="8.5">animalhostnames</font> e '
                   '<font name="Courier" size="8.5">vegetalhostnames</font> são '
                   '<b>incluídos normalmente</b> no denominador.', S['body'])],
    ]
    ht_pt = Table(host_data_pt, colWidths=[5*cm, 11*cm])
    ht_pt.setStyle(_grid_style(BLUE_MID))
    story.append(ht_pt)

    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(
        'Exemplos: (1) Um besouro de água doce (<i>environment = epicontinental</i>) '
        'é avaliado em 14 campos — <i>marinedomain</i> removido. '
        '(2) Um endoparasito é avaliado em 14 campos — os dois campos de hospedeiro '
        'são substituídos por um único slot combinado. '
        '(3) Um predador de vida livre (<i>lifeform = predador</i>) é avaliado em '
        '15 campos — ambos os campos de hospedeiro contam normalmente. '
        '(4) Uma espécie com <i>lifeform = vida livre individual</i> é avaliada em '
        '13 campos — ambos os campos de hospedeiro excluídos. '
        '(5) Um endêmico do Brasil (<i>endemicbrazil = SIM</i>) é avaliado em um '
        'campo a menos — <i>country</i> removido.', S['note']))

    story += [Paragraph('2.3  Fórmula de Completude', S['h2'])]
    story.append(Paragraph('Para cada espécie / subespécie:', S['body']))
    story.append(Paragraph(
        'completude (%) = (campos aplicáveis preenchidos) / (total de campos aplicáveis) × 100',
        S['code']))
    story.append(Paragraph(
        'Os valores são agregados por grupo taxonômico como média, mínimo e máximo. '
        '<b>Amplitude</b> (máx − mín) mede a heterogeneidade interna do grupo.',
        S['body']))

    story += [Paragraph('2.4  Regra de Subespécies', S['h2'])]
    story.append(Paragraph(
        'Quando uma espécie possui pelo menos uma subespécie aceita '
        '(<i>taxonrank = SUBSPECIES, taxonomicstatus = ACCEPTED</i>), a linha '
        'da espécie é <b>excluída</b> da análise e suas subespécies aceitas são '
        'usadas como unidades de análise. Isso garante que a completude seja medida '
        'na resolução mais fina disponível para cada linhagem.', S['body']))

    story += [Paragraph('2.5  Atribuição de Pesquisador', S['h2'])]
    story.append(Paragraph(
        'Cada linha agregada lista o pesquisador (<i>nome_completo</i>) responsável '
        'pelo grupo. A busca começa no rank da própria linha e sobe na hierarquia '
        'até encontrar um responsável. Quando resolvido em rank superior, a célula '
        'é anotada com "(via &lt;rank&gt;)".', S['body']))

    story += [Paragraph('2.6  Arquivos de Saída', S['h2'])]
    story.append(Paragraph('Os resultados são entregues em um arquivo ZIP contendo:', S['body']))
    story.append(output_table([
        ('completeness_per_species.xlsx',
         'Uma linha por espécie / subespécie: taxon_analisado, contexto taxonômico, '
         'taxonrank, completude (%), filled_count, total_applicable, pesquisador.'),
        ('completeness_by_genus.xlsx',
         'Agregação por gênero (apenas quando o táxon de entrada é uma família): '
         'n_spp_ctfb, completude média/mín/máx, amplitude, pesquisador.'),
        ('completeness_by_family.xlsx',  'Agregação por família: mesmas colunas.'),
        ('completeness_by_order.xlsx',   'Agregação por ordem.'),
        ('completeness_by_class.xlsx',   'Agregação por classe.'),
        ('completeness_by_subclass.xlsx','Agregação por subclasse (omitido se não houver dados).'),
        ('completeness_by_phylum.xlsx',  'Agregação por filo (omitido em consultas de filo único).'),
        ('completeness_histograms_genus.pdf',
         'Gráfico de barras horizontais por gênero (apenas quando o táxon de entrada '
         'é uma família), com barras de erro mín–máx.'),
        ('completeness_histograms_family.pdf',
         'Gráfico por família. A barra de maior média é destacada em vermelho.'),
        ('completeness_histograms_order.pdf',    'Mesmo gráfico por ordem.'),
        ('completeness_histograms_class.pdf',    'Mesmo gráfico por classe.'),
        ('completeness_histograms_subclass.pdf', 'Mesmo gráfico por subclasse.'),
        ('completeness_histograms_phylum.pdf',   'Mesmo gráfico por filo.'),
    ], S, col1='Arquivo', col2='Conteúdo'))

    # 3. Completude da Lista
    story += [PageBreak(), Paragraph('3. Completude da Lista de Espécies (GBIF)', S['h1']), rule()]
    story.append(Paragraph(
        'Esta análise compara a lista de espécies aceitas no CTFB com as espécies '
        'registradas no Brasil no GBIF, identificando espécies que ocorrem no Brasil '
        'mas estão ausentes do catálogo. A análise é executada em segundo plano; '
        'a página de status se atualiza automaticamente a cada 2 segundos.',
        S['body']))

    story += [Paragraph('3.1  Como Funciona — Quatro Fases', S['h2'])]
    for title, body in [
        ('Fase 1 — Resolução do táxon',
         'O nome do táxon é resolvido para um identificador interno do GBIF '
         '(<i>usageKey</i>) via a API GBIF Species Match '
         '(api.gbif.org/v1/species/match). Um erro é retornado se o nome não for '
         'reconhecido.'),
        ('Fase 2 — Coleta de chaves de espécies',
         'A API de Busca de Ocorrências do GBIF é consultada com country=BR e '
         'taxonKey=&lt;chave resolvida&gt;, usando facetas em speciesKey para '
         'recuperar todas as espécies com pelo menos um registro no Brasil. '
         'A paginação é aplicada automaticamente para táxons com mais de 50 000 '
         'espécies.'),
        ('Fase 3 — Resolução de nomes',
         'Cada chave de espécie é resolvida para um binômio canônico (gênero + '
         'epíteto específico) e sua taxonomia superior via a API de Espécies do '
         'GBIF. Até 20 requisições paralelas são feitas simultaneamente. '
         'Espécies fósseis/extintas (<i>extinct = true</i> no GBIF) são excluídas '
         'nesta fase.'),
        ('Fase 4 — Comparação com o CTFB',
         'As espécies do CTFB com <i>taxonomicstatus = ACCEPTED</i> e '
         '<i>taxonrank = SPECIES</i> são extraídas como binômios canônicos em '
         'minúsculas. Cada binômio do GBIF é classificado como: <b>presente</b> '
         '(corresponde a um nome aceito), <b>sinônimo</b> (corresponde a um '
         'sinônimo no CTFB) ou <b>ausente</b> (não encontrado de nenhuma forma).'),
    ]:
        story.append(KeepTogether([
            Paragraph(f'<b>{title}</b>', S['h3']),
            Paragraph(body, S['body']),
        ]))

    story += [Paragraph('3.2  Método de Correspondência e Ressalvas', S['h2'])]
    story.append(Paragraph(
        'A correspondência é feita pelo <b>binômio canônico em minúsculas</b>. '
        'Pontos importantes:', S['body']))
    for b in [
        'Espécies com binômios idênticos no GBIF e no CTFB são contadas como presentes, independentemente do autor ou ano.',
        'Um nome do GBIF que corresponde a um sinônimo (registro não-ACCEPTED) no CTFB é classificado em <i>Sinonimos_no_CTFB</i>, não como ausente.',
        'Discrepâncias nomenclaturais — sinonímia de gênero, variações ortográficas, tratamentos taxonômicos distintos — farão uma espécie aparecer como "ausente" mesmo que esteja representada sob outro nome no CTFB. Recomenda-se revisão manual.',
        'Táxons infraespecíficos (subespécies, variedades) são excluídos de ambos os lados.',
        'Espécies fósseis são excluídas (<i>extinct = true</i> no GBIF).',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [Paragraph('3.3  Arquivo de Saída', S['h2'])]
    story.append(Paragraph('Um único arquivo XLSX com quatro abas:', S['body']))
    story.append(output_table([
        ('Ausentes_no_CTFB',
         'Espécies GBIF (Brasil, não-fósseis) ausentes do CTFB em qualquer forma. '
         'Colunas: phylum_gbif, classe_gbif, ordem_gbif, familia_gbif, '
         'nome_cientifico, gbif_species_key. Ordenado por filo → classe → ordem → família → nome.'),
        ('Sinonimos_no_CTFB',
         'Espécies GBIF cujo binômio corresponde a um sinônimo (não-ACCEPTED) no CTFB. '
         'Mesmas colunas de Ausentes_no_CTFB.'),
        ('Resumo_por_Familia',
         'Resumo por família: total de espécies GBIF, ausentes, sinônimos e presentes. '
         'Ordenado por número de ausentes (decrescente).'),
        ('Presentes_no_CTFB',
         'Espécies GBIF correspondidas a um registro ACCEPTED no CTFB. '
         'Útil para verificação de cobertura.'),
    ], S, col1='Aba', col2='Conteúdo'))

    story += [Paragraph('3.4  Tempo Estimado de Execução', S['h2'])]
    story.append(time_table([
        [Paragraph('<b>Escala do táxon</b>', S['body']),
         Paragraph('<b>Espécies GBIF aprox.</b>', S['body']),
         Paragraph('<b>Tempo estimado</b>', S['body'])],
        [Paragraph('Ordem pequena (ex: Nematomorpha)', S['body']), Paragraph('< 200', S['body']),    Paragraph('10–30 segundos', S['body'])],
        [Paragraph('Ordem média (ex: Araneae)',         S['body']), Paragraph('~5 000', S['body']),   Paragraph('2–5 minutos', S['body'])],
        [Paragraph('Ordem grande (ex: Coleoptera)',     S['body']), Paragraph('~100 000', S['body']), Paragraph('15–30 minutos', S['body'])],
        [Paragraph('Filo completo (ex: Arthropoda)',    S['body']), Paragraph('> 200 000', S['body']),Paragraph('1–3 horas', S['body'])],
    ], S))
    story.append(Spacer(1, 0.2*cm))
    story.append(Paragraph(
        'Você pode fechar a aba e retornar mais tarde; o processo continua no '
        'servidor até a conclusão ou o próximo redeploy.', S['note']))

    # 4. Administração
    story += [PageBreak(), Paragraph('4. Administração', S['h1']), rule()]
    story.append(Paragraph(
        'Contas de administrador têm acesso ao Painel Admin pelo link no rodapé '
        'da página principal.', S['body']))

    story += [Paragraph('4.1  Gerenciamento de Usuários', S['h2'])]
    for item in [
        '<b>Importação em lote</b> — cole uma lista de logins da <i>pesquisadores.xlsx</i>. '
        'Cada usuário é criado com o flag "deve definir senha". '
        'Logins não encontrados na planilha são rejeitados.',
        '<b>Adição individual</b> — crie um único usuário com senha imediatamente utilizável.',
        '<b>Exportar CSV</b> — baixe um backup de todas as contas incluindo senhas hasheadas. '
        'Faça commit deste arquivo (<i>users_backup.csv</i>) no repositório antes de cada '
        'redeploy para que os usuários sejam restaurados automaticamente na inicialização.',
        '<b>Restaurar CSV</b> — reimporte usuários de um CSV exportado anteriormente. '
        'Contas existentes são ignoradas; os hashes de senha são restaurados.',
        '<b>Redefinir senha</b> — apaga a senha de um usuário e ativa o flag '
        '"deve definir senha". No próximo acesso o usuário segue o fluxo do primeiro acesso.',
        '<b>Definir senha</b> — define diretamente uma senha específica e imediatamente '
        'utilizável para um usuário (sem fluxo de primeiro acesso). Útil para usuários que já '
        'concluíram o primeiro acesso. O usuário pode alterá-la depois (§1.5).',
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))
    story.append(Paragraph(
        '<b>Seed automático na inicialização:</b> a cada inicialização o sistema lê '
        '<font name="Courier">users_backup.csv</font> da raiz do projeto e insere '
        'os usuários que ainda não existem no banco (contas e senhas existentes nunca '
        'são sobrescritas). Exporte e faça commit deste arquivo após adicionar ou '
        'alterar usuários para garantir que sobrevivam aos redeployments.', S['note']))

    story += [Paragraph('4.2  Persistência do Banco de Dados', S['h2'])]
    story.append(db_table([
        [Paragraph('<b>Backend</b>', S['body']),
         Paragraph('<b>Persistência</b>', S['body']),
         Paragraph('<b>Como ativar</b>', S['body'])],
        [Paragraph('PostgreSQL', S['body']),
         Paragraph('Permanente — sobrevive a todos os redeployments.', S['body']),
         Paragraph('Defina DATABASE_URL com uma string postgresql:// (ex: pelo Railway).', S['body'])],
        [Paragraph('SQLite em volume', S['body']),
         Paragraph('Permanente — armazenado em um volume persistente montado.', S['body']),
         Paragraph('Padrão: o arquivo do banco fica no diretório <i>data/</i>. Quando esse '
                   'diretório é um volume montado (ex: volume Railway em /app/data), sobrevive aos '
                   'redeployments. O Painel Admin confirma "SQLite em volume persistente".', S['body'])],
        [Paragraph('SQLite (efêmero)', S['body']),
         Paragraph('Efêmero — dados perdidos a cada redeploy.', S['body']),
         Paragraph('Ocorre apenas se o diretório <i>data/</i> não estiver em um volume persistente. '
                   'Um banner de aviso aparece no Painel Admin.', S['body'])],
    ], S))

    story += [Paragraph('4.3  Fontes de Dados', S['h2'])]
    story.append(Paragraph(
        'Dois conjuntos de dados são carregados na inicialização, ambos a partir das APIs '
        'oficiais da Fauna do Brasil (JBRJ). O <b>catálogo</b> é baixado diretamente; o '
        '<b>cadastro de pesquisadores</b> é montado mesclando o relatório de contribuição '
        'ao vivo da JBRJ com uma planilha curada do Google Sheets (ver §4.4). Cada '
        'resultado é armazenado em cache no diretório <i>data/</i> após um carregamento '
        'bem-sucedido, e a cópia em cache é usada automaticamente se uma fonte estiver '
        'temporariamente indisponível.', S['body']))
    story.append(output_table([
        ('planilha_extendida.csv',
         'Catálogo CTFB estendido (Darwin Core + campos manuais). Baixado da API '
         'PostgREST da Fauna do Brasil (JBRJ) '
         '(<font name="Courier" size="8">fauna.jbrj.gov.br/rest/mv_planilha_extendida</font>), '
         'paginado em páginas de 5 000 registros. Fonte de todos os cálculos de completude.'),
        ('pesquisadores.xlsx',
         'Cadastro de pesquisadores: login, nome_completo, táxons, institution, email. '
         'login / nome_completo / e-mail e os táxons atribuídos vêm do relatório de '
         'contribuição da JBRJ; o campo <i>institution</i> vem da planilha curada do '
         'Google Sheets. Controla autorização e atribuição de pesquisador.'),
    ], S, col1='Arquivo', col2='Conteúdo'))

    story += [Paragraph('4.4  Mantendo os Dados Atualizados', S['h2'])]
    story.append(Paragraph(
        'Tanto o catálogo quanto o cadastro de pesquisadores são servidos a partir de '
        'cópias recentes das fontes oficiais da JBRJ, mantidas atualizadas automaticamente '
        '— nenhum upload manual é necessário.', S['body']))
    for item in [
        '<b>A cada inicialização e, novamente, diariamente às 03:00 (America/São_Paulo)</b>, '
        'uma tarefa agendada rebaixa o catálogo e o relatório de contribuição de '
        'pesquisadores e recarrega ambos na memória, de modo que uma instância em execução '
        'prolongada nunca fique desatualizada. (O agendador pode ser desativado com a '
        'variável de ambiente <i>ENABLE_SCHEDULER=0</i>.)',
        '<b>Catálogo</b> — baixado integralmente da API da Fauna do Brasil. O download é '
        'atômico e à prova de falhas: o novo arquivo substitui o anterior apenas após um '
        'download completo e bem-sucedido; se a API estiver indisponível ou não retornar '
        'registros, a última cópia válida em cache é mantida e as análises continuam sem '
        'interrupção.',
        '<b>Cadastro de pesquisadores</b> — login, nome_completo, e-mail e os táxons '
        'atribuídos a cada pesquisador vêm do relatório de contribuição da JBRJ '
        '(<font name="Courier" size="8">mv_relatorio_contribuicao_usuarios</font>); o campo '
        '<i>institution</i> e qualquer pesquisador ausente do relatório são mesclados a '
        'partir da planilha curada do Google Sheets. Se um pesquisador não tiver táxons no '
        'relatório, os táxons da planilha são mantidos como fallback.',
    ]:
        story.append(Paragraph(f'• {item}', S['bullet']))
    story.append(Paragraph(
        'As datas das cópias do catálogo e do cadastro de pesquisadores em uso são '
        'exibidas a todos os usuários tanto na tela de login quanto na página principal '
        '(ex: <i>Catálogo: 2026-06-22 · Pesquisadores: 2026-06-22</i>), para que você '
        'sempre confirme o quão atualizados estão os dados.', S['note']))

    # 5. Interpretação
    story += [PageBreak(), Paragraph('5. Interpretando os Resultados', S['h1']), rule()]

    story += [Paragraph('5.1  Gráficos de Completude', S['h2'])]
    story.append(Paragraph(
        'Cada PDF exibe uma barra horizontal por grupo taxonômico. O comprimento '
        'da barra representa a completude média (%). As barras de erro se estendem '
        'até os valores mínimo e máximo do grupo. A barra de maior média é colorida '
        'em vermelho; as demais são azuis. Os valores são anotados à direita.',
        S['body']))
    story.append(Paragraph(
        'Um grupo com 100% de média e amplitude zero está perfeitamente homogêneo. '
        'Uma amplitude grande indica que algumas espécies são bem documentadas '
        'enquanto outras carecem de muitos campos — sinalizando onde concentrar '
        'o esforço curatorial.', S['body']))

    story += [Paragraph('5.2  Lista de Lacunas de Espécies', S['h2'])]
    story.append(Paragraph(
        'A aba <i>Ausentes_no_CTFB</i> lista espécies candidatas à inclusão no '
        'catálogo. Antes de agir sobre um registro, considere:', S['body']))
    for b in [
        'Diferenças nomenclaturais — a espécie pode já estar no CTFB sob um binômio sinônimo (verifique primeiro a aba <i>Sinonimos_no_CTFB</i>).',
        'Escopo taxonômico — alguns registros do GBIF podem referir-se a espécies marinhas fora do escopo atual do CTFB.',
        'Qualidade dos registros — alguns registros do GBIF são identificações incorretas ou carecem de precisão geográfica. Registros de alta incerteza devem ser verificados.',
        'Táxons infraespecíficos — a comparação com o GBIF abrange apenas o nível de espécie.',
    ]:
        story.append(Paragraph(f'• {b}', S['bullet']))

    story += [
        Spacer(1, 1.5*cm), section_rule(),
        Paragraph('Problemas ou dúvidas? Escreva para '
                  '<font name="Courier">faunadobrasilctfb@gmail.com</font>', S['footer']),
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
