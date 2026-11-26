from pathlib import Path
import html,re
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

def build_book_pdf(source):
    source=Path(source)
    for name,file in [('Book','arial.ttf'),('Book-Bold','arialbd.ttf'),('Book-Italic','ariali.ttf'),('Book-BoldItalic','arialbi.ttf')]:
        if name not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
    pdfmetrics.registerFontFamily('Book',normal='Book',bold='Book-Bold',italic='Book-Italic',boldItalic='Book-BoldItalic')
    text=source.read_bytes().decode('utf-8');output=source.with_suffix('.pdf')
    styles={
      'p':ParagraphStyle('body',fontName='Book',fontSize=11,leading=16,spaceAfter=7,textColor=colors.HexColor('#172334')),
      'h1':ParagraphStyle('title',fontName='Book-Bold',fontSize=20,leading=25,spaceBefore=8,spaceAfter=15,keepWithNext=True),
      'h2':ParagraphStyle('chapter',fontName='Book-Bold',fontSize=14.5,leading=20,spaceBefore=16,spaceAfter=10,keepWithNext=True),
      'h3':ParagraphStyle('sub',fontName='Book-Bold',fontSize=11.6,leading=16,spaceBefore=10,spaceAfter=6,keepWithNext=True),
      'cell':ParagraphStyle('cell',fontName='Book',fontSize=8.3,leading=11.2,spaceAfter=0),
    }
    def inline(value):
        value=html.escape(value)
        value=re.sub(r'\[([^]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#185b82">\1</link>',value)
        value=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',value)
        value=re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)',r'<i>\1</i>',value)
        return re.sub(r'`([^`]+)`',r'\1',value)
    story=[];paragraph=[];lines=text.splitlines();i=0
    def flush():
        if paragraph:
            story.append(Paragraph(inline(' '.join(paragraph)),styles['p']));paragraph.clear()
    while i<len(lines):
        line=lines[i].strip();i+=1
        if not line:flush();continue
        if line in ['---','***','___']:flush();story.append(Spacer(1,5*mm));continue
        if line.startswith('|')and line.endswith('|'):
            flush();rows=[]
            while True:
                cells=[c.strip()for c in line.strip('|').split('|')]
                if not all(re.fullmatch(r':?-{2,}:?',c)for c in cells):rows.append(cells)
                if i>=len(lines)or not lines[i].strip().startswith('|'):break
                line=lines[i].strip();i+=1
            if rows:
                n=max(map(len,rows));data=[[Paragraph(inline(c),styles['cell'])for c in row+['']*(n-len(row))]for row in rows]
                table=Table(data,colWidths=[(A4[0]-36*mm)/n]*n,repeatRows=1,hAlign='LEFT')
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eef2f5')),('BOX',(0,0),(-1,-1),.4,colors.HexColor('#a8b4bf')),('INNERGRID',(0,0),(-1,-1),.25,colors.HexColor('#c8d0d7')),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
                story.extend([table,Spacer(1,4*mm)])
            continue
        heading=re.match(r'^(#{1,6})\s+(.*)$',line)
        if heading:
            flush();key='h1'if len(heading[1])==1 else'h2'if len(heading[1])==2 else'h3'
            story.append(Paragraph(inline(heading[2]),styles[key]));continue
        bullet=re.match(r'^([-*]|\d+[.])\s+(.*)$',line)
        if bullet:
            flush();story.append(Paragraph(inline(bullet[2]),styles['p'],bulletText=bullet[1]if bullet[1][0].isdigit()else'\u2022'));continue
        if line.startswith('>'):
            flush();story.append(Paragraph(inline(line.lstrip('>').strip()),styles['p']));continue
        paragraph.append(line)
    flush()
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('Book',8);canvas.setFillColor(colors.HexColor('#647385'))
        canvas.drawCentredString(A4[0]/2,10*mm,str(doc.page));canvas.restoreState()
    doc=SimpleDocTemplate(str(output),pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=16*mm,bottomMargin=17*mm,title=next((l.lstrip('#').strip()for l in lines if l.strip()),source.stem),author='Jo aus Österreich (FiatMoneyEater)')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output
