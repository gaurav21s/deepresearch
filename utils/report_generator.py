import streamlit as st
import queue
import threading
import time
import os
import tempfile
import markdown
from contextlib import redirect_stdout
from deep_ai.agent import reporter_agent
from utils.ui_components import show_success_message, show_error_message, show_warning_message, copy_to_clipboard
from utils.storage import save_report
from utils.pdf_generator import markdown_to_pdf_reportlab, show_pdf

class StdoutCapture:
    """Custom stdout capturing class that doesn't update UI directly"""
    def __init__(self, output_queue):
        self.output_queue = output_queue
    
    def write(self, text):
        if text.strip():  # Only process non-empty lines
            self.output_queue.put(text)
    
    def flush(self):
        pass

def generate_report(topic, user_id):
    """Generate a research report on the given topic"""
    # Create a queue for capturing output
    output_queue = queue.Queue()
    
    # Create a queue for the final report
    result_queue = queue.Queue()
    
    # Create a thread for report generation
    def generate_report_thread():
        try:
            # Capture stdout
            with redirect_stdout(StdoutCapture(output_queue)):
                # Generate the report
                report_content = reporter_agent(topic)
                result_queue.put(report_content)
        except Exception as e:
            print(f"Error in report generation thread: {str(e)}")
            result_queue.put(None)
    
    # Start the report generation thread
    report_thread = threading.Thread(target=generate_report_thread)
    report_thread.start()
    
    # Create a progress bar
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Initialize variables
    report_content = None
    last_progress = 0
    
    # Wait for the report to be generated
    while report_thread.is_alive() or not result_queue.empty():
        # Update progress bar
        current_progress = min(last_progress + 1, 90)
        progress_bar.progress(current_progress)
        last_progress = current_progress
        
        # Update status text
        status_text.text("Generating your research report...")
        
        # Check for output
        try:
            while True:
                output = output_queue.get_nowait()
                if output.strip():
                    print(output.strip())
        except queue.Empty:
            pass
        
        # Check if the result is available
        if report_content is None:
            try:
                report_content = result_queue.get_nowait()
            except queue.Empty:
                pass
        
        # Sleep briefly to prevent locking up the UI
        time.sleep(0.1)
        
        # If thread is no longer alive but we don't have report content yet,
        # wait a bit longer but eventually break out
        if not report_thread.is_alive() and report_content is None:
            try:
                report_content = result_queue.get(timeout=0.5)
            except queue.Empty:
                break
    
    # Thread is done, join it and get result if we haven't already
    report_thread.join(timeout=1.0)
    
    # One final check for the result
    if report_content is None:
        try:
            report_content = result_queue.get_nowait()
        except queue.Empty:
            pass
    
    # Update progress bar to 100%
    progress_bar.progress(100)
    status_text.text("Report generation complete!")
    
    return report_content

def handle_report_generation(topic, user_id):
    """Handle the report generation process"""
    if not topic:
        show_error_message("Please enter a research topic.")
        return
    
    # Generate the report
    report_content = generate_report(topic, user_id)
    
    if report_content:
        st.markdown("<h2 class='section-header'>Your Research Report</h2>", unsafe_allow_html=True)
        
        # Display the report content
        st.markdown("<div class='report-container'>" + 
                    markdown.markdown(report_content, extensions=['tables', 'fenced_code']) + 
                    "</div>", unsafe_allow_html=True)
        
        # Create PDF filename
        pdf_filename = f"{topic.replace(' ', '_')}_report.pdf"
        temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
        
        # Generate PDF
        with st.spinner("Preparing PDF for download..."):
            success = markdown_to_pdf_reportlab(report_content, topic, temp_pdf_path)
        
        if success:
            # Save to storage
            try:
                saved_path = save_report(user_id, topic, report_content)
                if saved_path:
                    show_success_message("Report automatically saved! ✅")
                else:
                    show_warning_message("Note: Unable to save report to cloud storage.")
            except Exception as save_error:
                show_warning_message("Note: Report generated but not saved to cloud storage. You can still download it.")
                print(f"Error saving to storage: {str(save_error)}")
            
            # Create columns for the PDF preview and download button
            col1, col2 = st.columns([3, 1])
            
            with col1:
                # Show a preview of the PDF
                with st.expander("Preview PDF", expanded=True):
                    show_pdf(temp_pdf_path)
            
            with col2:
                st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
                with open(temp_pdf_path, "rb") as pdf_file:
                    pdf_data = pdf_file.read()
                
                # Download PDF button
                st.download_button(
                    label="Download Report as PDF",
                    data=pdf_data,
                    file_name=pdf_filename,
                    mime="application/pdf",
                    key="download_pdf_main"
                )
                
                # Copy button
                if st.button("Copy Report", key="copy_report_main"):
                    if copy_to_clipboard(report_content):
                        show_success_message("Report copied to clipboard! ✨")
                    else:
                        show_warning_message("Could not copy to clipboard. Please try selecting and copying manually.")
            
            # Clean up the temp file
            os.remove(temp_pdf_path)
    else:
        show_error_message("Failed to generate the report. Please try again.")
        st.markdown("""
        <div style="background: rgba(255, 60, 172, 0.1); padding: 1.5rem; border-radius: 0.5rem; border: 1px solid rgba(255, 60, 172, 0.3);">
            <h3 style="color: #FF3CAC;">Possible reasons for failure:</h3>
            <ul>
                <li>The topic might be too complex or niche</li>
                <li>There might be connectivity issues with the research APIs</li>
                <li>The AI agent might have encountered an internal error</li>
            </ul>
            <p>Please try a different topic or try again later.</p>
        </div>
        """, unsafe_allow_html=True) 