import os
import tempfile
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import markdown
from bs4 import BeautifulSoup
import streamlit as st
import base64

def register_fonts():
    """Register custom fonts for PDF generation"""
    try:
        # Register Roboto fonts
        pdfmetrics.registerFont(TTFont('Roboto-Regular', 'Roboto-Regular.ttf'))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', 'Roboto-Bold.ttf'))
        pdfmetrics.registerFont(TTFont('Roboto-Italic', 'Roboto-Italic.ttf'))
        pdfmetrics.registerFont(TTFont('Roboto-BoldItalic', 'Roboto-BoldItalic.ttf'))
        return True
    except Exception as e:
        print(f"Error registering fonts: {str(e)}")
        return False

def create_custom_styles():
    """Create custom styles for PDF generation"""
    styles = getSampleStyleSheet()
    
    # Custom title style
    styles.add(ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontName='Roboto-Bold',
        fontSize=24,
        spaceAfter=30,
        alignment=TA_CENTER
    ))
    
    # Custom heading style
    styles.add(ParagraphStyle(
        name='CustomHeading',
        parent=styles['Heading2'],
        fontName='Roboto-Bold',
        fontSize=18,
        spaceBefore=20,
        spaceAfter=10
    ))
    
    # Custom body style
    styles.add(ParagraphStyle(
        name='CustomBody',
        parent=styles['Normal'],
        fontName='Roboto-Regular',
        fontSize=12,
        leading=16,
        spaceBefore=6,
        spaceAfter=6,
        alignment=TA_JUSTIFY
    ))
    
    return styles

def markdown_to_pdf_reportlab(markdown_text, title, output_path):
    """Convert markdown text to PDF using ReportLab"""
    try:
        # Register fonts
        if not register_fonts():
            st.error("Failed to register fonts. Using default fonts.")
        
        # Create custom styles
        styles = create_custom_styles()
        
        # Convert markdown to HTML
        html_content = markdown.markdown(markdown_text)
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Create PDF document
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Build PDF content
        story = []
        
        # Add title
        title_style = styles['CustomTitle']
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 20))
        
        # Process HTML content
        for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'ul', 'ol', 'li', 'code', 'pre']):
            if element.name in ['h1', 'h2', 'h3']:
                level = int(element.name[1])
                style = styles[f'Heading{level}']
                story.append(Paragraph(element.get_text(), style))
                story.append(Spacer(1, 12))
            
            elif element.name == 'p':
                story.append(Paragraph(element.get_text(), styles['CustomBody']))
                story.append(Spacer(1, 6))
            
            elif element.name in ['ul', 'ol']:
                for li in element.find_all('li'):
                    bullet = '•' if element.name == 'ul' else f"{len(story) + 1}."
                    story.append(Paragraph(f"{bullet} {li.get_text()}", styles['CustomBody']))
                story.append(Spacer(1, 6))
            
            elif element.name == 'code':
                story.append(Paragraph(f"<code>{element.get_text()}</code>", styles['Code']))
            
            elif element.name == 'pre':
                story.append(Paragraph(f"<pre>{element.get_text()}</pre>", styles['Code']))
        
        # Build PDF
        doc.build(story)
        return True
        
    except Exception as e:
        st.error(f"Error generating PDF: {str(e)}")
        return False

def show_pdf(pdf_path):
    """Display PDF in Streamlit"""
    try:
        with open(pdf_path, "rb") as pdf_file:
            base64_pdf = base64.b64encode(pdf_file.read()).decode('utf-8')
            pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600" type="application/pdf"></iframe>'
            st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error displaying PDF: {str(e)}") 