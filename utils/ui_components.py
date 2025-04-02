import streamlit as st
import time
import pyperclip
from datetime import datetime
import os
import tempfile
from utils.pdf_generator import markdown_to_pdf_reportlab

def add_floating_icons():
    """Add floating icons to the UI"""
    st.markdown("""
    <style>
    .floating-icons {
        position: fixed;
        bottom: 20px;
        right: 20px;
        z-index: 1000;
        display: flex;
        flex-direction: column;
        gap: 10px;
    }
    .floating-icon {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 100%);
        color: white;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    .floating-icon:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 12px rgba(0, 0, 0, 0.2);
    }
    </style>
    """, unsafe_allow_html=True)

def add_custom_styles():
    """Add custom styles to the UI"""
    st.markdown("""
    <style>
    /* Main header styling */
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    
    /* Subheader styling */
    .sub-header {
        font-size: 1.2rem;
        color: #EAEAEA;
        margin-bottom: 2rem;
    }
    
    /* Gradient text */
    .gradient-text {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    /* Section header */
    .section-header {
        color: #FF3CAC;
        margin-bottom: 1rem;
    }
    
    /* Report container */
    .report-container {
        background: rgba(36, 59, 85, 0.4);
        padding: 2rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(255, 60, 172, 0.2);
        margin-bottom: 2rem;
    }
    
    /* Card styling */
    .card {
        background: rgba(36, 59, 85, 0.4);
        padding: 1.5rem;
        border-radius: 0.5rem;
        border: 1px solid rgba(255, 60, 172, 0.2);
        margin-bottom: 1rem;
    }
    
    .card-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    .card-title {
        color: #FF3CAC;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    
    .card-text {
        color: #EAEAEA;
        font-size: 0.9rem;
    }
    
    /* Button styling */
    div[data-testid="stButton"] > button[kind="secondary"]:has(div:contains("✨ New Report")) {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 100%);
        color: white;
        border: none;
        font-weight: bold;
        width: 100%;
    }
    
    div[data-testid="stButton"] > button[kind="secondary"]:has(div:contains("✨ New Report")):hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(255, 60, 172, 0.4);
        transition: all 0.3s ease;
    }
    </style>
    """, unsafe_allow_html=True)

def copy_to_clipboard(text):
    """Copy text to clipboard"""
    try:
        pyperclip.copy(text)
        return True
    except Exception as e:
        print(f"Error copying to clipboard: {str(e)}")
        return False

def format_timestamp(timestamp):
    """Format timestamp for display"""
    if isinstance(timestamp, datetime):
        return timestamp.strftime("%Y-%m-%d %H:%M")
    return timestamp

def show_success_message(message, duration=1):
    """Show a success message"""
    st.success(message)
    time.sleep(duration)

def show_error_message(message, duration=1):
    """Show an error message"""
    st.error(message)
    time.sleep(duration)

def show_warning_message(message, duration=1):
    """Show a warning message"""
    st.warning(message)
    time.sleep(duration)

def create_action_buttons(content, title, timestamp=None):
    """Create action buttons for report actions"""
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        # Download as markdown
        st.download_button(
            "Download as Markdown",
            content,
            file_name=f"{title}.md",
            mime="text/markdown",
            key="download_md"
        )
    
    with col2:
        # Generate and download PDF
        if st.button("Generate PDF", key="gen_pdf"):
            with st.spinner("Generating PDF..."):
                # Create PDF filename
                pdf_filename = f"{title.replace(' ', '_')}_report.pdf"
                temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
                
                # Generate PDF
                success = markdown_to_pdf_reportlab(content, title, temp_pdf_path)
                
                if success:
                    with open(temp_pdf_path, "rb") as pdf_file:
                        pdf_data = pdf_file.read()
                        
                    st.download_button(
                        label="Download PDF",
                        data=pdf_data,
                        file_name=pdf_filename,
                        mime="application/pdf",
                        key="download_pdf"
                    )
                    
                    # Clean up
                    os.remove(temp_pdf_path)
                else:
                    show_error_message("Failed to generate PDF. Please try again.")
    
    with col3:
        # Copy button
        if st.button("Copy Report", key="copy_report"):
            if copy_to_clipboard(content):
                show_success_message("Report copied to clipboard! ✨")
            else:
                show_warning_message("Could not copy to clipboard. Please try selecting and copying manually.")
    
    with col4:
        # New Report button
        if st.button("New Report", key="new_report"):
            # Clean up all view-related session state
            for key in ['view_report_content', 'view_report_title', 'view_report_timestamp']:
                if key in st.session_state:
                    del st.session_state[key]
            print("New Report button clicked - returning to generator")
            st.rerun() 