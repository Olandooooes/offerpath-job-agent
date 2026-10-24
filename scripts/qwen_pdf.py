"""Fixed-layout PDF output. No network, external renderer, or model call."""
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape


def build_pdf(profile, job, draft, synthetic=True):
    from pypdf import PdfReader
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    paths = (os.environ.get('OFFERPATH_CJK_FONT', ''),
             '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
             '/Library/Fonts/Arial Unicode.ttf',
             '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
             'C:/Windows/Fonts/msyh.ttc')
    font = next((p for p in paths if p and Path(p).is_file()), None)
    if not font:
        raise ValueError('请通过OFFERPATH_CJK_FONT指定支持中文的TrueType字体')
    if 'OfferPathQwenCJK' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('OfferPathQwenCJK', font))
    body = ParagraphStyle('body', fontName='OfferPathQwenCJK', fontSize=10.5, leading=17,
                          wordWrap='CJK', spaceAfter=8, textColor=colors.HexColor('#263e50'))
    heading = ParagraphStyle('heading', parent=body, fontSize=12, leading=19, spaceBefore=10,
                             textColor=colors.HexColor('#245d87'))
    title = ParagraphStyle('title', parent=body, fontSize=22, leading=28, spaceAfter=10)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=13, textColor=colors.HexColor('#71818c'))
    def p(value, style=body):
        return Paragraph(escape(value).replace('\n', '<br/>'), style)
    story = []
    if synthetic:
        story.append(p('合成体验资料 · 客户端提交草稿 · 不用于真实求职', small))
    story += [p(profile['name'], title), p('教育：' + profile.get('education', '')),
              p('技能：' + profile.get('skills', '')),
              p('求职意向：' + job['role'] + ' · ' + job['company'], heading), p(draft['summary'])]
    for item in draft['items']:
        story += [p(item['title'], heading), p(item['text'])]
    if synthetic:
        story += [Spacer(1, 10), p('本版材料由用户审阅确认后使用；记录保存不代表招聘方已收到。', small)]
    output = io.BytesIO()
    SimpleDocTemplate(output, pagesize=A4, topMargin=38, bottomMargin=38,
                      leftMargin=44, rightMargin=44).build(story)
    data = output.getvalue()
    doc = PdfReader(io.BytesIO(data))
    if len(doc.pages) != 1 or not 0 < len(data) <= 1_000_000 or len(doc.pages[0].extract_text() or '') < 30:
        raise ValueError('PDF未通过一页、大小或文字检查，请精简内容后重试')
    return data


def render_pdf(data):
    renderer = shutil.which('pdftoppm') or str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/pdftoppm')
    if not Path(renderer).is_file():
        raise ValueError('本机未安装PDF渲染器，请打开实际PDF检查')
    with tempfile.TemporaryDirectory(prefix='offerpath-qwen-pdf-') as directory:
        root = Path(directory)
        (root / 'resume.pdf').write_bytes(data)
        result = subprocess.run([renderer, '-scale-to', '1400', '-f', '1', '-singlefile', '-png', str(root / 'resume.pdf'), str(root / 'preview')], capture_output=True, timeout=20)
        if result.returncode or not (root / 'preview.png').is_file():
            raise ValueError('实际PDF渲染失败，请下载检查')
        return (root / 'preview.png').read_bytes()
