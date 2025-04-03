import streamlit as st
import asyncio
import os
import sys
import logging
from PIL import Image
import time
import io
from contextlib import redirect_stdout
import tempfile
import queue
import markdown
from datetime import datetime
import threading
from bs4 import BeautifulSoup
import base64
import random
import pyperclip
import shutil
from pathlib import Path
import js as pjs
import json
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("deepresearch")

# Load environment variables first, before any imports that might use them
load_dotenv()

# Initialize session state to avoid circular import issues with API keys
if 'openai_api_key' not in st.session_state:
    st.session_state.openai_api_key = None
if 'tavily_api_key' not in st.session_state:
    st.session_state.tavily_api_key = None
if 'api_keys_set' not in st.session_state:
    st.session_state.api_keys_set = False

# Set API keys in environment if they exist in session state
if hasattr(st.session_state, 'openai_api_key') and st.session_state.openai_api_key:
    os.environ['OPENAI_API_KEY'] = st.session_state.openai_api_key

if hasattr(st.session_state, 'tavily_api_key') and st.session_state.tavily_api_key:
    os.environ['TAVILY_API_KEY'] = st.session_state.tavily_api_key

# ReportLab imports - purely Python, no system dependencies
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Add the current directory to the path so we can import from deep_ai
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import agent after setting environment variables
from deep_ai.agent import reporter_agent

import supabase
from supabase.client import Client, ClientOptions

# Initialize Supabase client via .env file
# supabase_url = os.environ.get("SUPABASE_URL", "") 
# supabase_key = os.environ.get("SUPABASE_KEY", "")

# Initialize Supabase client via Streamlit secrets
supabase_url = st.secrets["SUPABASE_URL"]
supabase_key = st.secrets["SUPABASE_KEY"]
supabase_client = supabase.create_client(supabase_url, supabase_key)

# Skip duplicate initialization if already done earlier in the file
if not hasattr(st.session_state, '_api_keys_initialized'):
    # Initialize API key session state
    if 'openai_api_key' not in st.session_state:
        st.session_state.openai_api_key = None
    if 'tavily_api_key' not in st.session_state:
        st.session_state.tavily_api_key = None
    if 'api_keys_set' not in st.session_state:
        st.session_state.api_keys_set = False
    # Mark as initialized
    st.session_state._api_keys_initialized = True

# Set page configuration
st.set_page_config(
    page_title="DeepResearch AI Report Generator",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Add this after initializing the Supabase client (around line 46)
def create_bucket_if_not_exists(bucket_name="deepresearch-reports"):
    """Create bucket if it doesn't exist"""
    try:
        # Check if the bucket exists
        logger.info(f"Checking if bucket '{bucket_name}' exists...")
        supabase_client.storage.get_bucket(bucket_name)
        logger.info(f"Bucket '{bucket_name}' already exists.")
    except Exception as e:
        # Create the bucket if it doesn't exist
        try:
            logger.info(f"Creating bucket '{bucket_name}'...")
            supabase_client.storage.create_bucket(bucket_name, {"public": False})
            logger.info(f"Successfully created bucket '{bucket_name}'")
        except Exception as e:
            # This is expected if the bucket exists but we don't have permission to get it directly
            logger.warning(f"Note: Using existing bucket '{bucket_name}', couldn't access directly: {str(e)}")
    
    # Let's check if we can list files in the bucket as a test
    try:
        logger.info(f"Testing access to bucket '{bucket_name}'...")
        files = supabase_client.storage.from_(bucket_name).list()
        logger.info(f"Successfully accessed bucket '{bucket_name}'. Files count: {len(files)}")
    except Exception as e:
        logger.warning(f"Warning: Cannot list files in bucket {bucket_name}: {str(e)}")
    
    return bucket_name

# Ensure the reports bucket exists on startup
create_bucket_if_not_exists()

# Define gradient colors from config
primary_color = "#FF3CAC"
secondary_color = "#243B55"
bg_color = "#141E30"
text_color = "#EAEAEA"

# Initialize session state variables for authentication
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False
if 'user' not in st.session_state:
    st.session_state.user = None

# Authentication functions
def sign_up(email, password, full_name):
    try:
        response = supabase_client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name
                }
            }
        })
        if response and response.user:
            st.session_state.authenticated = True
            st.session_state.user = response.user
            logger.info(f"User signed up successfully: {email}")
            st.rerun()
        return response
    except Exception as e:
        logger.error(f"Error signing up: {str(e)}")
        st.error(f"Error signing up: {str(e)}")
        return None

def sign_in(email, password):
    try:
        response = supabase_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if response and response.user:
            # Store user info directly in session state
            st.session_state.authenticated = True
            st.session_state.user = response.user
            logger.info(f"User logged in successfully: {email}")
            st.rerun()
        return response
    except Exception as e:
        logger.error(f"Error signing in: {str(e)}")
        st.error(f"Error signing in: {str(e)}")
        return None

def sign_out():
    try:
        user_email = st.session_state.user.email if st.session_state.user else "Unknown"
        supabase_client.auth.sign_out()
        # Clear authentication-related session state and API keys
        st.session_state.authenticated = False
        st.session_state.user = None
        st.session_state.api_keys_set = False
        st.session_state.openai_api_key = None
        st.session_state.tavily_api_key = None
        # Set a flag to trigger rerun on next render
        st.session_state.logout_requested = True
        logger.info(f"User logged out: {user_email}")
    except Exception as e:
        logger.error(f"Error signing out: {str(e)}")
        st.error(f"Error signing out: {str(e)}")

# Custom CSS for better markdown rendering and overall appearance
st.markdown("""
<style>
    /* Base styles */
    body {
        background-color: #141E30;
        background-image: linear-gradient(to bottom right, #141E30, #243B55);
        color: #EAEAEA;
        font-family: 'Inter', sans-serif;
    }
    
    /* Floating document icons animation */
    @keyframes float {
        0% { transform: translateY(0px) rotate(0deg); }
        50% { transform: translateY(-20px) rotate(5deg); }
        100% { transform: translateY(0px) rotate(0deg); }
    }
    
    .floating-icon {
        position: absolute;
        opacity: 0.7;
        z-index: -1;
        animation: float 8s ease-in-out infinite;
    }
    
    /* Gradient text */
    .gradient-text {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 50%, #2B86C5 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 800;
    }
    
    /* Main header styling */
    .main-header {
        font-size: 3.5rem;
        font-weight: 800;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    
    .sub-header {
        font-size: 1.2rem;
        opacity: 0.9;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    /* Section headers */
    .section-header {
        font-size: 1.8rem;
        color: #FF3CAC;
        margin-top: 2rem;
        margin-bottom: 1rem;
        font-weight: 600;
    }
    
    /* Status box with glass morphism effect */
    .status-box {
        padding: 1.5rem;
        border-radius: 1rem;
        margin: 1.5rem 0;
        height: 200px;
        overflow-y: auto;
        background: rgba(36, 59, 85, 0.6);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 60, 172, 0.2);
        font-family: 'JetBrains Mono', monospace;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    
    .progress-line {
        margin: 0;
        padding: 4px 0;
        color: #EAEAEA;
        font-size: 0.85rem;
    }
    
    /* Report container with glass morphism */
    .report-container {
        padding: 2rem;
        border-radius: 1rem;
        border: 1px solid rgba(255, 60, 172, 0.2);
        background: rgba(36, 59, 85, 0.4);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        margin: 1.5rem 0;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    
    .report-container h1 {
        color: #FF3CAC;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 0.8rem;
    }
    
    .report-container h2 {
        color: #EAEAEA;
        margin-top: 1.8rem;
    }
    
    .report-container h3 {
        color: #EAEAEA;
        opacity: 0.9;
        margin-top: 1.5rem;
    }
    
    .report-container p {
        color: #EAEAEA;
        margin: 1rem 0;
        line-height: 1.8;
    }
    
    .report-container ul, .report-container ol {
        color: #EAEAEA;
        margin: 1rem 0;
        padding-left: 1.8rem;
    }
    
    /* Custom button styling */
    .stButton > button {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 100%);
        color: white;
        border: none;
        border-radius: 0.5rem;
        padding: 0.6rem 1.2rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
    }
    
    /* Custom progress bar */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, #FF3CAC 0%, #784BA0 100%);
    }
    
    /* Custom form styling */
    .stTextInput > div > div > input {
        background-color: rgba(36, 59, 85, 0.6);
        border: 1px solid rgba(255, 60, 172, 0.3);
        border-radius: 0.5rem;
        color: #EAEAEA;
        padding: 1rem;
    }
    
    .stTextInput > div > div > input:focus {
        border: 1px solid #FF3CAC;
        box-shadow: 0 0 0 2px rgba(255, 60, 172, 0.2);
    }
    
    /* Sidebar styling */
    .css-1d391kg, .css-163ttbj, .css-1wrcr25 {
        background-color: rgba(20, 30, 48, 0.8);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background-color: rgba(36, 59, 85, 0.6);
        border-radius: 0.5rem;
    }
    
    /* Card component */
    .card {
        background: rgba(36, 59, 85, 0.4);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-radius: 1rem;
        padding: 1.5rem;
        border: 1px solid rgba(255, 60, 172, 0.2);
        margin-bottom: 1.5rem;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
    }
    
    .card:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }
    
    .card-icon {
        font-size: 2rem;
        margin-bottom: 1rem;
        color: #FF3CAC;
    }
    
    .card-title {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 0.5rem;
        color: #EAEAEA;
    }
    
    .card-text {
        font-size: 0.9rem;
        color: #EAEAEA;
        opacity: 0.8;
    }
    
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(36, 59, 85, 0.2);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(180deg, #FF3CAC 0%, #784BA0 100%);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(180deg, #FF3CAC 30%, #784BA0 100%);
    }
</style>
""", unsafe_allow_html=True)

# Try a completely different approach for floating icons
def add_floating_icons():
    # Create a fixed-position container with a higher z-index
    st.markdown("""
    <style>
    .icon-container {
        position: fixed;
        width: 100%;
        height: 100vh;
        top: 0;
        left: 0;
        pointer-events: none;
        z-index: 10;
        overflow: hidden;
    }
    
    .floating-document {
        position: absolute;
        font-size: 2rem;
        opacity: 0.1;
        animation: float-animation 10s ease-in-out infinite;
    }
    
    @keyframes float-animation {
        0% { transform: translate(0, 0) rotate(0deg); }
        50% { transform: translate(10px, -15px) rotate(5deg); }
        100% { transform: translate(0, 0) rotate(0deg); }
    }
    </style>
    

    <div class="icon-container">
        <div class="floating-document" style="top: 15%; left: 10%; animation-delay: 0s; font-size: 2rem;">📄</div>
        <div class="floating-document" style="top: 16%; left: 53%; animation-delay: 1s; font-size: 3rem;">📑</div>
        <div class="floating-document" style="top: 65%; left: 8%; animation-delay: 2s; font-size: 2.5rem;">📝</div>
        <div class="floating-document" style="top: 75%; left: 90%; animation-delay: 3s; font-size: 2rem;">📊</div>
        <div class="floating-document" style="top: 40%; left: 5%; animation-delay: 4s; font-size: 3rem;">📚</div>
        <div class="floating-document" style="top: 85%; left: 15%; animation-delay: 5s; font-size: 2rem;">📋</div>
        <div class="floating-document" style="top: 10%; left: 80%; animation-delay: 6s; font-size: 2.5rem;">🔍</div>
        <div class="floating-document" style="top: 55%; left: 75%; animation-delay: 7s; font-size: 2.8rem;">🤖</div>
        <div class="floating-document" style="top: 30%; left: 25%; animation-delay: 8s; font-size: 2.2rem;">🧠</div>
        <div class="floating-document" style="top: 70%; left: 60%; animation-delay: 9s; font-size: 2.4rem;">📈</div>
        <div class="floating-document" style="top: 20%; left: 70%; animation-delay: 10s; font-size: 2.7rem;">💻</div>
        <div class="floating-document" style="top: 60%; left: 39%; animation-delay: 11s; font-size: 2.3rem;">📱</div>
        <div class="floating-document" style="top: 80%; left: 40%; animation-delay: 12s; font-size: 2.6rem;">📡</div>
        <div class="floating-document" style="top: 35%; left: 85%; animation-delay: 13s; font-size: 2.1rem;">🌐</div>
        <div class="floating-document" style="top: 60%; left: 20%; animation-delay: 14s; font-size: 2.9rem;">⚙️</div>
        <div class="floating-document" style="top: 45%; left: 55%; animation-delay: 15s; font-size: 2.2rem;">📰</div>
        <div class="floating-document" style="top: 5%; left: 35%; animation-delay: 16s; font-size: 2.5rem;">📘</div>
        <div class="floating-document" style="top: 90%; left: 65%; animation-delay: 17s; font-size: 2.4rem;">🔬</div>
    </div>
    """, unsafe_allow_html=True)

# Add the floating icons
add_floating_icons()

# Add these functions after imports and before the sidebar code
def ensure_user_bucket(user_id):
    """Ensure user's bucket exists in Supabase storage"""
    bucket_id = f"user_{user_id}"
    try:
        # Check if bucket exists by attempting to list files
        supabase_client.storage.from_(bucket_id).list()
    except:
        # Create new bucket if it doesn't exist
        try:
            supabase_client.storage.create_bucket(
                bucket_id,
                {"public": False}  # Private bucket
            )
        except Exception as e:
            logger.error(f"Error creating bucket: {str(e)}")
            raise
    return bucket_id

def save_report(user_id, topic, content):
    """Save a report to Supabase storage"""
    bucket_name = "deepresearch-reports"
    
    # Create a directory path for this user
    user_folder = f"{user_id}/"
    
    # Create a unique filename with timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(' ', '_').replace('/', '_')  # Basic sanitize
    file_name = f"{safe_topic}_{ts}.md"
    
    # Full path including user folder
    file_path = f"{user_folder}{file_name}"
    
    # Create metadata
    metadata = {
        "topic": topic,
        "timestamp": ts,
        "filename": file_name,
        "user_id": user_id,
        "uploaded_at": datetime.now().strftime("%Y%m%d_%H%M%S")
    }
    
    # Upload content to Supabase Storage
    try:
        # Try to upload the report directly
        try:
            logger.info(f"Uploading report to {file_path}...")
            supabase_client.storage.from_(bucket_name).upload(
                path=file_path,
                file=content.encode('utf-8')
            )
        except Exception as upload_error:
            logger.warning(f"First upload attempt failed: {str(upload_error)}")
            logger.info("Trying alternative method...")
            
            # Create a temporary file
            temp_file = os.path.join(tempfile.gettempdir(), "temp_upload.md")
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Upload from file
            with open(temp_file, 'rb') as f:
                supabase_client.storage.from_(bucket_name).upload(
                    path=file_path,
                    file=f
                )
            
            # Clean up temp file
            os.remove(temp_file)
        
        logger.info("✅ File uploaded successfully!")
        
        # Upload metadata as a separate JSON file
        metadata_path = f"{user_folder}{file_name}.meta.json"
        try:
            logger.info(f"Uploading metadata to {metadata_path}...")
            supabase_client.storage.from_(bucket_name).upload(
                path=metadata_path,
                file=json.dumps(metadata).encode('utf-8')
            )
        except Exception as meta_error:
            logger.warning(f"First metadata upload attempt failed: {str(meta_error)}")
            logger.info("Trying alternative method for metadata...")
            
            # Create a temporary file for metadata
            temp_meta = os.path.join(tempfile.gettempdir(), "temp_meta.json")
            with open(temp_meta, 'w', encoding='utf-8') as f:
                json.dump(metadata, f)
            
            # Upload from file
            with open(temp_meta, 'rb') as f:
                supabase_client.storage.from_(bucket_name).upload(
                    path=metadata_path,
                    file=f
                )
            
            # Clean up temp file
            os.remove(temp_meta)
        
        logger.info(f"✅ Metadata uploaded successfully for report: {topic}")
        
        return file_path
    except Exception as e:
        logger.error(f"Error saving report '{topic}': {str(e)}")
        st.error(f"Error saving report: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def load_saved_reports(user_id):
    """Load all saved reports from Supabase storage"""
    bucket_name = "deepresearch-reports"
    user_folder = f"{user_id}/"
    
    try:
        # List all files in the user's folder
        logger.info(f"Listing files for user {user_id}...")
        response = supabase_client.storage.from_(bucket_name).list(path=user_folder)
        
        # Filter metadata files
        meta_files = [file for file in response if file["name"].endswith(".meta.json")]
        content_files = [file for file in response if not file["name"].endswith(".meta.json") and not file["name"].endswith(".folder")]
        
        logger.info(f"Found {len(meta_files)} metadata files, {len(content_files)} content files for user {user_id}")
        
        reports = []
        for meta_file in meta_files:
            # Download and parse metadata
            meta_path = f"{user_folder}{meta_file['name']}"
            try:
                logger.debug(f"Reading metadata from {meta_path}...")
                data = supabase_client.storage.from_(bucket_name).download(meta_path)
                metadata = json.loads(data.decode('utf-8'))
                
                # Format timestamp for display
                try:
                    ts = datetime.strptime(metadata["timestamp"], "%Y%m%d_%H%M%S")
                    reports.append({
                        "topic": metadata["topic"],
                        "timestamp": ts,
                        "filename": metadata["filename"],
                        "path": f"{user_folder}{metadata['filename']}"  # Storage path with user folder
                    })
                except (ValueError, KeyError) as e:
                    logger.error(f"Error processing metadata timestamp for {meta_file['name']}: {str(e)}")
                    continue  # Skip malformed metadata
            except Exception as e:
                logger.error(f"Error reading metadata file {meta_file['name']}: {str(e)}")
                continue
                
        return sorted(reports, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        logger.error(f"Error loading reports for user {user_id}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def get_report_content(user_id, filename):
    """Get report content from Supabase storage"""
    bucket_name = "deepresearch-reports"
    
    # Handle both full paths and just filenames
    if "/" in filename:  # Full path provided
        file_path = filename
    else:  # Just filename provided
        file_path = f"{user_id}/{filename}"
    
    logger.info(f"Retrieving report for user {user_id}, path: {file_path}")
    
    try:
        logger.info(f"Downloading report from {file_path}...")
        
        # Test bucket access first
        try:
            logger.debug(f"Testing bucket '{bucket_name}' access...")
            files = supabase_client.storage.from_(bucket_name).list()
            logger.debug(f"Bucket '{bucket_name}' contains {len(files)} files/folders")
            
            # Try listing user directory
            try:
                user_path = f"{user_id}/"
                user_files = supabase_client.storage.from_(bucket_name).list(path=user_path)
                logger.debug(f"User directory '{user_path}' contains {len(user_files)} files")
                logger.debug(f"Files in user directory: {[f['name'] for f in user_files]}")
            except Exception as user_list_error:
                logger.warning(f"Error listing user directory: {str(user_list_error)}")
        except Exception as bucket_error:
            logger.warning(f"Error accessing bucket: {str(bucket_error)}")
        
        # Now try to download the file
        data = supabase_client.storage.from_(bucket_name).download(file_path)
        content = data.decode('utf-8')
        logger.info(f"Successfully downloaded report ({len(content)} bytes)")
        return content
    except Exception as e:
        logger.error(f"Error retrieving report {file_path}: {str(e)}")
        st.error(f"Error retrieving report: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def delete_report(user_id, filename):
    """Delete a report and its metadata from Supabase storage"""
    bucket_name = "deepresearch-reports"
    
    # Handle both full paths and just filenames
    if "/" in filename:  # Full path provided
        file_path = filename
    else:  # Just filename provided
        file_path = f"{user_id}/{filename}"
    
    meta_path = f"{file_path}.meta.json"
    
    logger.info(f"Attempting to delete report for user {user_id}: {file_path}")
    
    try:
        # Delete the report file
        logger.info(f"Deleting report: {file_path}...")
        supabase_client.storage.from_(bucket_name).remove([file_path])
        logger.info("✅ Report deleted successfully")
        
        # Try to delete metadata too
        try:
            logger.info(f"Deleting metadata: {meta_path}...")
            supabase_client.storage.from_(bucket_name).remove([meta_path])
            logger.info("✅ Metadata deleted successfully")
        except Exception as e:
            logger.warning(f"Could not delete metadata: {str(e)}")
        
        return True
    except Exception as e:
        logger.error(f"Error deleting report {file_path}: {str(e)}")
        st.error(f"Error deleting report: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def add_table_of_contents(markdown_text):
    """
    Parse markdown and add a table of contents at the beginning
    """
    # Convert markdown to HTML to parse headings
    html_content = markdown.markdown(markdown_text)
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all headings
    headings = soup.find_all(['h1', 'h2', 'h3'])
    
    if not headings:
        return markdown_text
    
    # Generate TOC
    toc = ["# Table of Contents\n"]
    
    for heading in headings:
        # Get heading level (h1 = 1, h2 = 2, etc.)
        level = int(heading.name[1])
        
        # Create indentation based on heading level
        indent = "  " * (level - 1)
        
        # Create a link-friendly ID
        heading_id = heading.text.lower().replace(" ", "-").replace(".", "")
        
        # Add to TOC
        toc.append(f"{indent}- {heading.text}\n")
    
    # Add TOC to the beginning of the document
    toc.append("\n---\n\n")  # Separator
    return "".join(toc) + markdown_text


def markdown_to_pdf_reportlab(markdown_text, topic, filename):
    """
    Convert markdown to PDF with professional formatting using ReportLab
    """
    try:
        # Add table of contents to the markdown
        markdown_text_with_toc = add_table_of_contents(markdown_text)
        
        # Parse markdown with BeautifulSoup to extract structure
        html_content = markdown.markdown(
            markdown_text_with_toc, 
            extensions=['tables', 'fenced_code', 'codehilite', 'nl2br']
        )
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Create PDF document
        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=65,
            bottomMargin=70
        )
        
        # Try to register a nice font if available
        try:
            pdfmetrics.registerFont(TTFont('Roboto', 'Roboto-Regular.ttf'))
            pdfmetrics.registerFont(TTFont('Roboto-Bold', 'Roboto-Bold.ttf'))
            pdfmetrics.registerFont(TTFont('Roboto-Italic', 'Roboto-Italic.ttf'))
            pdfmetrics.registerFont(TTFont('Roboto-BoldItalic', 'Roboto-BoldItalic.ttf'))
            font_family = 'Roboto'
        except Exception as font_error:
            logger.warning(f"Could not load Roboto fonts: {str(font_error)}. Using Helvetica.")
            # Fallback to default Helvetica
            font_family = 'Helvetica'
        
        # Create styles
        styles = getSampleStyleSheet()
        
        # Instead of adding new styles with the same names, modify existing ones
        # Predefined styles in getSampleStyleSheet: Normal, Heading1-6, Title, Bullet, Definition, Code, BodyText
        
        # Modify Title style
        styles['Title'].fontName = f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold'
        styles['Title'].fontSize = 24
        styles['Title'].leading = 28
        styles['Title'].alignment = TA_CENTER
        styles['Title'].spaceAfter = 20
        styles['Title'].textColor = colors.HexColor('#FF3CAC')
        
        # Modify Heading1 style - Ensure center alignment
        styles['Heading1'].fontName = f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold'
        styles['Heading1'].fontSize = 18
        styles['Heading1'].leading = 22
        styles['Heading1'].alignment = TA_CENTER  # Center aligned
        styles['Heading1'].spaceAfter = 10
        styles['Heading1'].spaceBefore = 20
        styles['Heading1'].textColor = colors.HexColor('#FF3CAC')
        
        # Modify Heading2 style
        styles['Heading2'].fontName = f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold'
        styles['Heading2'].fontSize = 16
        styles['Heading2'].leading = 20
        styles['Heading2'].spaceAfter = 8
        styles['Heading2'].spaceBefore = 15
        styles['Heading2'].textColor = colors.HexColor('#784BA0')
        
        # Modify Heading3 style
        styles['Heading3'].fontName = f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold'
        styles['Heading3'].fontSize = 14
        styles['Heading3'].leading = 18
        styles['Heading3'].spaceAfter = 6
        styles['Heading3'].spaceBefore = 10
        styles['Heading3'].textColor = colors.HexColor('#333333')
        
        # Modify Normal style
        styles['Normal'].fontName = font_family if font_family == 'Roboto' else 'Helvetica'
        styles['Normal'].fontSize = 11
        styles['Normal'].leading = 14
        styles['Normal'].spaceAfter = 8
        styles['Normal'].alignment = TA_JUSTIFY
        
        # Modify Code style
        styles['Code'].fontName = 'Courier'
        styles['Code'].fontSize = 9
        styles['Code'].leading = 12
        styles['Code'].backColor = colors.HexColor('#f5f5f5')
        styles['Code'].textColor = colors.HexColor('#333333')
        
        # Add only new styles that don't exist in the default stylesheet
        styles.add(ParagraphStyle(
            name='ReportTitle',  # Custom style with unique name
            fontName=f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold',
            fontSize=24,
            leading=28,
            alignment=TA_CENTER,
            spaceAfter=20,
            textColor=colors.HexColor('#FF3CAC')
        ))
        
        styles.add(ParagraphStyle(
            name='TopicTitle',  # New style specifically for the topic
            fontName=f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold',
            fontSize=20,
            leading=24,
            alignment=TA_CENTER,
            spaceAfter=10,
            textColor=colors.HexColor('#784BA0')
        ))
        
        styles.add(ParagraphStyle(
            name='ListItem',  # New style
            fontName=font_family if font_family == 'Roboto' else 'Helvetica',
            fontSize=11,
            leading=14,
            leftIndent=20
        ))
        
        styles.add(ParagraphStyle(
            name='Caption',  # New style
            fontName=f'{font_family}-Italic' if font_family == 'Roboto' else 'Helvetica-Oblique',
            fontSize=10,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor('#666666')
        ))
        
        # Create story (list of flowables)
        story = []
        
        # Add cover page - use ReportTitle style instead of Title
        story.append(Spacer(1, 3*inch))
        story.append(Paragraph('Research Report', styles['ReportTitle']))
        story.append(Spacer(1, 0.5*inch))
        # Use the new TopicTitle style for better centering of the topic
        story.append(Paragraph(topic, styles['TopicTitle']))
        story.append(Spacer(1, 2*inch))
        story.append(Paragraph(f"Generated by DeepResearch AI", styles['Caption']))
        story.append(Paragraph(datetime.now().strftime("%B %d, %Y"), styles['Caption']))
        story.append(PageBreak())
        
        # Process markdown elements
        in_list = False
        list_items = []
        in_code_block = False
        code_content = ""
        
        # Function to handle lists when we're done with them
        def process_list():
            nonlocal list_items, in_list
            if list_items:
                data = [[Paragraph(item, styles['ListItem'])] for item in list_items]
                # Create a borderless table for layout
                t = Table(data, colWidths=[400])
                t.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 15),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                story.append(t)
                list_items = []
                in_list = False
        
        # Process each element
        for element in soup.descendants:
            if element.name == 'h1':
                # Close any open lists
                process_list()
                # Add a page break before each h1 heading
                story.append(PageBreak())
                story.append(Paragraph(element.text, styles['Heading1']))
            elif element.name == 'h2':
                process_list()
                # Add a page break before each h2 heading
                story.append(PageBreak())
                story.append(Paragraph(element.text, styles['Heading2']))
            elif element.name == 'h3':
                process_list()
                story.append(Paragraph(element.text, styles['Heading3']))
            elif element.name == 'p':
                process_list()
                # Check if this is a code block (wrapped in pre)
                if element.parent and element.parent.name == 'pre':
                    continue  # We'll handle code blocks separately
                story.append(Paragraph(element.text, styles['Normal']))
            elif element.name == 'pre':
                process_list()
                # Extract code from pre tags
                code_text = element.get_text()
                # Wrap in a code style
                code_para = Paragraph(code_text.replace('<', '&lt;').replace('>', '&gt;'), styles['Code'])
                # Add some padding around the code block
                story.append(Spacer(1, 0.1*inch))
                story.append(code_para)
                story.append(Spacer(1, 0.1*inch))
            elif element.name == 'ul' or element.name == 'ol':
                # Start a new list (handled by li elements)
                in_list = True
            elif element.name == 'li' and in_list:
                # Add to current list
                list_items.append(element.text)
            elif element.name == 'code':
                # Inline code, handled by parent paragraph
                pass
            elif element.name == 'strong' or element.name == 'em':
                # Inline formatting, handled by parent paragraph
                pass
            elif element.name == 'table':
                process_list()
                # Simple table implementation
                rows = []
                is_header = True
                
                for tr in element.find_all('tr'):
                    row = []
                    for td in tr.find_all(['td', 'th']):
                        # Add cell content as paragraph
                        row.append(Paragraph(td.text, styles['Normal']))
                    rows.append(row)
                    is_header = False
                
                # Create table
                if rows:
                    col_width = 450 / len(rows[0])
                    t = Table(rows, colWidths=[col_width] * len(rows[0]))
                    
                    # Style the table
                    table_style = [
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f2f2f2')),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#333333')),
                        ('FONTNAME', (0, 0), (-1, 0), f'{font_family}-Bold' if font_family == 'Roboto' else 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('TOPPADDING', (0, 0), (-1, 0), 12),
                    ]
                    t.setStyle(TableStyle(table_style))
                    story.append(t)
            elif element.name == 'blockquote':
                process_list()
                quote_text = element.get_text()
                quote_style = ParagraphStyle(
                    'Blockquote',
                    parent=styles['Normal'],
                    leftIndent=30,
                    rightIndent=30,
                    fontName=f'{font_family}-Italic' if font_family == 'Roboto' else 'Helvetica-Oblique',
                    textColor=colors.HexColor('#555555')
                )
                story.append(Paragraph(quote_text, quote_style))
            elif element.name == 'hr':
                process_list()
                story.append(Spacer(1, 0.2*inch))
                
        # Close any open lists at the end
        process_list()
        
        # Build PDF
        doc.build(story)
        logger.info(f"PDF successfully built: {filename}")
        
        return True
    except Exception as e:
        logger.error(f"Error generating PDF for '{topic}': {str(e)}")
        st.error(f"Error generating PDF: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False


# Alternative implementation without JavaScript
def copy_to_clipboard(text):
    """Copy text to clipboard using pyperclip with fallback"""
    try:
        # Try using pyperclip
        pyperclip.copy(text)
        return True
    except Exception as e:
        # print(f"Pyperclip error: {e}")
        logger.error(f"Pyperclip error: {e}")
        # If pyperclip fails, provide instructions to manually copy
        st.code(text, language="markdown")
        st.info("Please use Ctrl+A to select all text, then Ctrl+C to copy manually.")
        return False

# Sidebar with authentication
with st.sidebar:
    st.markdown("<h1 style='text-align: center;'><span class='gradient-text'>DeepResearch AI</span></h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; margin-bottom: 2rem;'>AI-powered research report generator</p>", unsafe_allow_html=True)
    
    if not st.session_state.authenticated:
        tab1, tab2 = st.tabs(["Login", "Sign Up"])
        
        with tab1:
            st.subheader("Login")
            login_email = st.text_input("Email", key="login_email")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_button = st.button("Login")
            
            if login_button:
                if login_email and login_password:
                    sign_in(login_email, login_password)
                else:
                    st.warning("Please enter both email and password.")
        
        with tab2:
            st.subheader("Sign Up")
            signup_email = st.text_input("Email", key="signup_email")
            signup_password = st.text_input("Password", type="password", key="signup_password")
            signup_name = st.text_input("Full Name", key="signup_name")
            signup_button = st.button("Sign Up")
            
            if signup_button:
                if signup_email and signup_password and signup_name:
                    response = sign_up(signup_email, signup_password, signup_name)
                    if response and response.user:
                        st.success("Sign up successful! Please check your email to confirm your account.")
                    else:
                        st.error("Sign up failed. Please try again.")
                else:
                    st.warning("Please fill in all fields.")
    else:
        user = st.session_state.user
        if user:
            st.success(f"Logged in as: {user.email}")
            st.button("Logout", on_click=sign_out, key="logout_button")
            
            # Display user information
            st.subheader("Your Profile")
            st.write(f"User ID: {user.id}")
            
            # API Keys Management
            with st.expander("Manage API Keys", expanded=False):
                if st.session_state.api_keys_set:
                    st.success("API keys are set ✓")
                    
                    # Show masked keys
                    if st.session_state.openai_api_key:
                        masked_openai = st.session_state.openai_api_key[:5] + "..." + st.session_state.openai_api_key[-4:]
                        st.code(f"OpenAI API Key: {masked_openai}", language="text")
                    
                    if st.session_state.tavily_api_key:
                        masked_tavily = st.session_state.tavily_api_key[:5] + "..." + st.session_state.tavily_api_key[-4:]
                        st.code(f"Tavily API Key: {masked_tavily}", language="text")
                    
                    # Button to update keys
                    if st.button("Update API Keys"):
                        st.session_state.api_keys_set = False
                        st.rerun()
                else:
                    st.warning("API keys not configured")
                    if st.button("Configure API Keys"):
                        st.rerun()
                
                # API key resources
                st.markdown("**Get API Keys:**")
                st.markdown("- [OpenAI API Keys](https://platform.openai.com/api-keys)")
                st.markdown("- [Tavily API Keys](https://app.tavily.com/home)")
            
            # New Report button in sidebar
            if st.button("New Report", key="new_report_sidebar"):
                # Clear any report viewing state
                for key in ['view_report_content', 'view_report_title', 'view_report_timestamp']:
                    if key in st.session_state:
                        del st.session_state[key]
                
                # Reset view_report_in_main flag if it exists
                if hasattr(st.session_state, 'view_report_in_main'):
                    st.session_state.view_report_in_main = False
                    st.session_state.selected_report_index = None
                
                st.rerun()
            
            # Architecture Diagram Dropdown
            # with st.expander("View Architecture", expanded=False):
            #     try:
            #         image = Image.open("langgraph.png")
            #         st.image(image, caption="Agent Workflow", use_container_width=True)
            #     except FileNotFoundError:
            #         st.warning("langgraph.png not found.")
            
            # Saved Reports Section
            st.subheader("📚 Saved Reports")
            saved = load_saved_reports(user.id)
            if saved:
                titles = [f"{r['topic']} ({r['timestamp']:%Y-%m-%d %H:%M})" for r in saved]
                sel_title = st.radio("Select:", titles, key="report_select")
                sel_idx = titles.index(sel_title)
                sel_data = saved[sel_idx]
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("View", key=f"view_{sel_idx}"):
                        try:
                            logger.info(f"User {user.id} viewing report: {sel_data['filename']}")
                            content = get_report_content(user.id, sel_data["filename"])
                            logger.info(f"Content retrieval result: {'SUCCESS' if content else 'FAILED'}")
                            if content:
                                logger.info(f"Content loaded successfully, length: {len(content)} bytes")
                                st.session_state.view_report_content = content
                                st.session_state.view_report_title = sel_data["topic"]
                                st.session_state.view_report_timestamp = sel_data["timestamp"]
                                st.success("Report loaded successfully!")
                                logger.info("Session state updated for report view")
                                st.rerun()
                            else:
                                logger.error(f"Failed to load report content for {sel_data['filename']}")
                                st.error("Failed to load report. Content is empty or null.")
                        except Exception as e:
                            logger.error(f"Exception in view report handler: {str(e)}")
                            st.error(f"Error loading report: {str(e)}")
                            import traceback
                            logger.error(traceback.format_exc())
                with col2:
                    if st.button("Delete", key=f"del_{sel_idx}"):
                        logger.info(f"User {user.id} deleting report: {sel_data['filename']}")
                        if delete_report(user.id, sel_data["filename"]):
                            logger.info(f"Report successfully deleted: {sel_data['filename']}")
                            st.success("Report deleted")
                            time.sleep(1)
                            st.rerun()
                        else:
                            logger.error(f"Failed to delete report: {sel_data['filename']}")
                            st.error("Failed to delete report")
            else:
                st.info("No saved reports.")
            
            # How it works section
            st.markdown("<h3 style='color: #FF3CAC; margin-top: 2rem;'>How it works</h3>", unsafe_allow_html=True)
            
            # Create feature cards
            st.markdown("""
            <div class="card">
                <div class="card-icon">🧠</div>
                <div class="card-title">Plan</div>
                <div class="card-text">AI agent plans the report structure based on your topic</div>
            </div>
            
            <div class="card">
                <div class="card-icon">🔍</div>
                <div class="card-title">Research</div>
                <div class="card-text">Gathers relevant information from trusted sources</div>
            </div>
            
            <div class="card">
                <div class="card-icon">✍️</div>
                <div class="card-title">Generate</div>
                <div class="card-text">Creates a comprehensive, well-structured report</div>
            </div>
            
            <div class="card">
                <div class="card-icon">📥</div>
                <div class="card-title">Download</div>
                <div class="card-text">Export your report as a professionally formatted PDF</div>
            </div>
            """, unsafe_allow_html=True)
            
            # About section
            st.markdown("<h3 style='color: #FF3CAC; margin-top: 2rem;'>About</h3>", unsafe_allow_html=True)
            st.markdown("""
            <div style="background: rgba(36, 59, 85, 0.4); padding: 1rem; border-radius: 0.5rem; border: 1px solid rgba(255, 60, 172, 0.2);">
                This app uses advanced AI agents built with LangGraph to create 
                detailed research reports on any topic.
            </div>
            """, unsafe_allow_html=True)

# Main content - Only show if authenticated
if st.session_state.authenticated:
   
    st.markdown("<h1 class='main-header'><span class='gradient-text'>Transform Your Research</span></h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Generate in-depth AI-powered reports on any topic—planned, researched, and written in minutes.</p>", unsafe_allow_html=True)

    # Display saved report in main area if requested
    if hasattr(st.session_state, 'view_report_in_main') and st.session_state.view_report_in_main and st.session_state.selected_report_index is not None:
        saved_reports = load_saved_reports(user.id)
        if saved_reports and 0 <= st.session_state.selected_report_index < len(saved_reports):
            report = saved_reports[st.session_state.selected_report_index]
            
            # Display the report header
            st.markdown(f"<h1 class='section-header'>Saved Report: {report['topic']}</h1>", unsafe_allow_html=True)
            st.markdown(f"<p>Generated on: {report['timestamp'].strftime('%Y-%m-%d %H:%M')}</p>", unsafe_allow_html=True)
            
            # Read and display the report content
            report_content = get_report_content(user.id, report['filename'])
            
            # Display the report in a nice container
            st.markdown("<div class='report-container'>" + 
                        markdown.markdown(report_content, extensions=['tables', 'fenced_code']) + 
                        "</div>", unsafe_allow_html=True)
            
            # Add action buttons
            col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
            
            with col1:
                # Download as markdown
                st.download_button(
                    "Download as Markdown",
                    report_content,
                    file_name=f"{report['topic']}.md",
                    mime="text/markdown",
                    key=f"download_md_main"
                )
                
            with col2:
                # Generate and download PDF
                if st.button("Generate PDF", key="gen_pdf_saved"):
                    with st.spinner("Generating PDF..."):
                        # Create PDF filename
                        pdf_filename = f"{report['topic'].replace(' ', '_')}_report.pdf"
                        temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
                        
                        # Generate PDF
                        success = markdown_to_pdf_reportlab(report_content, report['topic'], temp_pdf_path)
                        
                        if success:
                            with open(temp_pdf_path, "rb") as pdf_file:
                                pdf_data = pdf_file.read()
                                
                            st.download_button(
                                label="Download PDF",
                                data=pdf_data,
                                file_name=pdf_filename,
                                mime="application/pdf",
                                key="download_saved_pdf"
                            )
                            
                            # Clean up
                            os.remove(temp_pdf_path)
                        else:
                            st.error("Failed to generate PDF. Please try again.")
                            
            with col3:
                # Copy button with fixed functionality
                if st.button("Copy Report", key="copy_saved_report"):
                    if copy_to_clipboard(report_content):
                        st.success("Report copied to clipboard! ✨")
                        time.sleep(1)
                    else:
                        st.warning("Could not copy to clipboard. Please try selecting and copying manually.")
                        time.sleep(1)
            
            with col4:
                # New Report button
                if st.button("New Report", key="new_report_saved"):
                    st.session_state.view_report_in_main = False
                    st.session_state.selected_report_index = None
                    st.rerun()
            
            # Don't show the form when viewing a saved report
            st.stop()

    # Display report content if available (from sidebar view button)
    elif 'view_report_content' in st.session_state and 'view_report_title' in st.session_state:
        # Display the report header
        st.markdown(f"<h1 class='section-header'>Report: {st.session_state.view_report_title}</h1>", unsafe_allow_html=True)
        
        # Show timestamp if available
        if hasattr(st.session_state, 'view_report_timestamp'):
            timestamp_str = st.session_state.view_report_timestamp.strftime("%Y-%m-%d %H:%M")
            st.markdown(f"<p>Generated on: {timestamp_str}</p>", unsafe_allow_html=True)
        
        # Display the report in a nice container
        st.markdown("<div class='report-container'>" + 
                    markdown.markdown(st.session_state.view_report_content, extensions=['tables', 'fenced_code']) + 
                    "</div>", unsafe_allow_html=True)
        
        # Add action buttons
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            # Download as markdown
            st.download_button(
                "Download as Markdown",
                st.session_state.view_report_content,
                file_name=f"{st.session_state.view_report_title}.md",
                mime="text/markdown",
                key="download_md_view"
            )
            
        with col2:
            # Generate and download PDF
            if st.button("Generate PDF", key="gen_pdf_view"):
                with st.spinner("Generating PDF..."):
                    # Create PDF filename
                    pdf_filename = f"{st.session_state.view_report_title.replace(' ', '_')}_report.pdf"
                    temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
                    
                    # Generate PDF
                    success = markdown_to_pdf_reportlab(st.session_state.view_report_content, st.session_state.view_report_title, temp_pdf_path)
                    
                    if success:
                        with open(temp_pdf_path, "rb") as pdf_file:
                            pdf_data = pdf_file.read()
                            
                        st.download_button(
                            label="Download PDF",
                            data=pdf_data,
                            file_name=pdf_filename,
                            mime="application/pdf",
                            key="download_view_pdf"
                        )
                        
                        # Clean up
                        os.remove(temp_pdf_path)
                    else:
                        st.error("Failed to generate PDF. Please try again.")
                        
        with col3:
            # Copy button with fixed functionality
            if st.button("Copy Report", key="copy_view_report"):
                if copy_to_clipboard(st.session_state.view_report_content):
                    st.success("Report copied to clipboard! ✨")
                    time.sleep(1)
                else:
                    st.warning("Could not copy to clipboard. Please try selecting and copying manually.")
                    time.sleep(1)
        
        with col4:
            # New Report button
            if st.button("New Report", key="new_report_view"):
                # Clean up all view-related session state
                for key in ['view_report_content', 'view_report_title', 'view_report_timestamp']:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        
        # Don't show the form when viewing a report
        st.stop()

    # Check API keys only when trying to generate a new report
    if not st.session_state.api_keys_set:
        st.markdown("<h1 class='main-header'><span class='gradient-text'>API Keys Required</span></h1>", unsafe_allow_html=True)
        st.markdown("<p class='sub-header'>To generate new research reports, you need to provide API keys for OpenAI and Tavily.</p>", unsafe_allow_html=True)
        
        # Create a form for API keys
        with st.form("api_keys_form"):
            openai_key = st.text_input("OpenAI API Key", type="password", value=st.session_state.openai_api_key or "", 
                                      help="Get your OpenAI API key from https://platform.openai.com/api-keys")
            
            tavily_key = st.text_input("Tavily API Key", type="password", value=st.session_state.tavily_api_key or "",
                                      help="Get your Tavily API key from https://app.tavily.com/home")
            
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("<a href='https://platform.openai.com/api-keys' target='_blank'>Get OpenAI API Key</a>", unsafe_allow_html=True)
            with col2:
                st.markdown("<a href='https://app.tavily.com/home' target='_blank'>Get Tavily API Key</a>", unsafe_allow_html=True)
            
            submit_keys = st.form_submit_button("Save API Keys")
            
            if submit_keys:
                if openai_key and tavily_key:
                    # Set environment variables
                    os.environ['OPENAI_API_KEY'] = openai_key
                    os.environ['TAVILY_API_KEY'] = tavily_key
                    
                    # Store in session state
                    st.session_state.openai_api_key = openai_key
                    st.session_state.tavily_api_key = tavily_key
                    st.session_state.api_keys_set = True
                    
                    logger.info(f"API keys set successfully for user: {st.session_state.user.id}")
                    st.success("API keys saved successfully!")
                    st.rerun()
                else:
                    logger.warning(f"Missing API keys for user: {st.session_state.user.id}")
                    st.error("Please provide both API keys to continue.")
        
        # Display instructions
        st.markdown("""
        <div style="background: rgba(36, 59, 85, 0.4); padding: 1.5rem; border-radius: 0.5rem; border: 1px solid rgba(255, 60, 172, 0.2); margin-top: 2rem;">
            <h3 style="color: #FF3CAC;">How to get your API keys:</h3>
            <h4>OpenAI API Key:</h4>
            <ol>
                <li>Visit <a href="https://platform.openai.com/api-keys" target="_blank">https://platform.openai.com/api-keys</a></li>
                <li>Sign in to your OpenAI account (or create one if needed)</li>
                <li>Click on "Create new secret api key"</li>
                <li>Copy the generated key and paste it above</li>
            </ol>
            <h4>Tavily API Key:</h4>
            <ol>
                <li>Visit <a href="https://app.tavily.com/home" target="_blank">https://app.tavily.com/home</a></li>
                <li>Sign in to your Tavily account (or create one if needed)</li>
                <li>Navigate to your API settings</li>
                <li>Copy your API key (Generous Free Tier Available) and paste it above</li>
            </ol>
            <p>Your API keys are stored securely in your session and only used to generate reports. And cleared after you log out.</p>
        </div>
        """, unsafe_allow_html=True)
        
        # Stop execution here until keys are provided
        st.stop()

    # Input form for new report generation
    with st.form("report_form"):
        st.markdown("<h3 style='color: #FF3CAC; margin-bottom: 0.1rem;'>What would you like to research?</h3>", unsafe_allow_html=True)
        topic = st.text_input(
            label="Research Topic",  # Add a proper label
            label_visibility="collapsed",  # Hide the label but maintain accessibility
            placeholder="e.g., The Impact of Artificial Intelligence on Healthcare"
        )
        
        submit_button = st.form_submit_button("Generate Report")

    st.markdown("</div>", unsafe_allow_html=True)

    # Custom stdout capturing class that doesn't update UI directly
    class StdoutCapture:
        def __init__(self, output_queue):
            self.output_queue = output_queue
        
        def write(self, text):
            if text.strip():  # Only process non-empty lines
                # Add to queue instead of updating UI directly
                self.output_queue.put(text)


    # Function to run the agent asynchronously
    async def run_agent(topic, output_queue, progress_queue):
        report_content = ""
        
        # Create a custom stdout capture object
        stdout_capture = StdoutCapture(output_queue)
        
        # Use contextlib to redirect stdout
        with redirect_stdout(stdout_capture):
            try:
                # Verify API keys are in environment
                if not os.environ.get('OPENAI_API_KEY'):
                    error_msg = "OpenAI API key not found in environment."
                    logger.error(error_msg)
                    output_queue.put(f"ERROR: {error_msg}")
                    progress_queue.put(("status", "❌ Error: OpenAI API key not set"))
                    return None
                    
                if not os.environ.get('TAVILY_API_KEY'):
                    error_msg = "Tavily API key not found in environment."
                    logger.error(error_msg)
                    output_queue.put(f"ERROR: {error_msg}")
                    progress_queue.put(("status", "❌ Error: Tavily API key not set"))
                    return None
                
                logger.info(f"Starting report generation for topic: {topic}")
                events = reporter_agent.astream(
                    {'topic': topic},
                    {"recursion_limit": 50},
                    stream_mode="values",
                )
                
                steps = 0
                total_estimated_steps = 10  # Rough estimate
                
                async for event in events:
                    for k, v in event.items():
                        if k != "__end__":
                            steps += 1
                            progress_value = min(steps / total_estimated_steps, 0.95)
                            # Send progress update via queue
                            progress_queue.put(("progress", progress_value))

                        if k == 'final_report':
                            report_content = v
                            progress_queue.put(("progress", 1.0))
                            progress_queue.put(("report", v))
                            logger.info(f"Report generation completed successfully for topic: {topic}")
            except Exception as e:
                error_message = f"Error generating report: {str(e)}"
                logger.error(error_message)
                output_queue.put(error_message)
                progress_queue.put(("status", f"❌ {error_message}"))
                return None
                
        return report_content


    # Function to process a single report generation run
    def process_report(topic, output_queue, progress_queue, result_queue):
        """Process the report generation in a separate thread with its own event loop"""
        try:
            # Ensure API keys are set in the environment
            if not os.environ.get('OPENAI_API_KEY') and st.session_state.openai_api_key:
                os.environ['OPENAI_API_KEY'] = st.session_state.openai_api_key
                logger.info("Setting OpenAI API key from session state")
                
            if not os.environ.get('TAVILY_API_KEY') and st.session_state.tavily_api_key:
                os.environ['TAVILY_API_KEY'] = st.session_state.tavily_api_key
                logger.info("Setting Tavily API key from session state")
                
            logger.info(f"Starting report generation process for topic: {topic}")
            
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the agent in the event loop
            report_content = loop.run_until_complete(
                run_agent(topic, output_queue, progress_queue)
            )
            
            # Close the loop when done
            loop.close()
            
            # Put the result in the queue to communicate back to the main thread
            if report_content:
                logger.info(f"Report generation successful for topic: {topic}")
                result_queue.put(report_content)
                return True
            else:
                logger.warning(f"Report generation failed for topic: {topic}")
                return False
        except Exception as e:
            logger.error(f"Error in report generation process: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False


    # Display PDF in Streamlit
    def show_pdf(file_path):
        with open(file_path, "rb") as f:
            base64_pdf = base64.b64encode(f.read()).decode('utf-8')
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="800" type="application/pdf"></iframe>'
        st.markdown(pdf_display, unsafe_allow_html=True)


    # Add animated loading indicators
    def show_loading_animation():
        loading_animations = [
            "🔍 Researching sources...",
            "📚 Analyzing information...",
            "🧠 Synthesizing content...",
            "📝 Drafting sections...",
            "✏️ Refining language...",
            "📊 Creating structure...",
            "🔗 Connecting ideas...",
        ]
        return random.choice(loading_animations)


    # Process form submission
    if submit_button and topic:
        # First verify API keys are still set in environment
        if not os.environ.get('OPENAI_API_KEY') or not os.environ.get('TAVILY_API_KEY'):
            if st.session_state.openai_api_key and st.session_state.tavily_api_key:
                # If they're in session state but not in environment, set them
                os.environ['OPENAI_API_KEY'] = st.session_state.openai_api_key
                os.environ['TAVILY_API_KEY'] = st.session_state.tavily_api_key
                logger.info("API keys restored from session state")
            else:
                # If not in session state, show error
                logger.error(f"API keys missing for user {st.session_state.user.id} before report generation")
                st.error("API keys are missing. Please set your OpenAI and Tavily API keys in the sidebar.")
                st.stop()

        logger.info(f"Report generation form submitted for topic: '{topic}'")
        st.markdown("<h5 class='section-header'>This may take a few minutes...</h5>", unsafe_allow_html=True)
        
        # Progress tracking
        status_text = st.empty()
        
        # Create a progress bar with custom styling
        progress_bar = st.progress(0)
        
        # Create a status area for detailed progress messages
        st.markdown("<h3 style='color: #FF3CAC; margin-top: 1.5rem;'>Progress Details:</h3>", unsafe_allow_html=True)
        status_container = st.container()
        status_box = status_container.empty()
        status_box.markdown("<div class='status-box'></div>", unsafe_allow_html=True)
        
        # Create a placeholder for the report content
        report_placeholder = st.empty()
        
        # Create queues for inter-thread communication
        output_queue = queue.Queue()
        progress_queue = queue.Queue()
        result_queue = queue.Queue()  # New queue to get the final report
        
        # Create a separate thread for report generation
        report_thread = threading.Thread(
            target=process_report,
            args=(topic, output_queue, progress_queue, result_queue)
        )
        report_thread.daemon = True  # Make thread a daemon so it exits when main thread exits
        report_thread.start()
        
        # Monitor the thread and update the UI
        output_lines = []
        report_content = None
        
        # Show spinner while processing
        with st.spinner("Generating your report..."):
            last_animation_time = time.time()
            current_animation = show_loading_animation()
            
            while report_thread.is_alive() or (not report_content):
                # Update loading animation every 3 seconds
                current_time = time.time()
                if current_time - last_animation_time > 3:
                    current_animation = show_loading_animation()
                    last_animation_time = current_time
                    status_text.markdown(f"<h6 style='text-align: center;'>{current_animation}</h6>", unsafe_allow_html=True)
                
                # Check for progress updates
                try:
                    while True:
                        update_type, update_value = progress_queue.get_nowait()

                        if update_type == "progress":
                            progress_bar.progress(update_value)
                        elif update_type == "status":
                            status_text.markdown(f"<h3 style='text-align: center;'>{update_value}</h3>", unsafe_allow_html=True)
                        elif update_type == "report":
                            # We're getting the report through the progress queue
                            report_content = update_value
                            report_placeholder.markdown(
                                f"<div class='report-container'>{markdown.markdown(update_value, extensions=['tables', 'fenced_code'])}</div>", 
                                unsafe_allow_html=True
                            )
                except queue.Empty:
                    pass
                
                # Check for stdout updates
                new_lines_added = False
                try:
                    while True:
                        output = output_queue.get_nowait()
                        if output.strip():  # Only process non-empty lines
                            output_lines.append(output.strip())
                            new_lines_added = True
                except queue.Empty:
                    pass
                
                # Update status box if we have new content
                if output_lines and (new_lines_added or time.time() % 1 < 0.5):  # Refresh every half second
                    formatted_lines = []
                    for line in output_lines[-30:]:  # Show last 30 lines only
                        if "---" in line:  # This is a status line
                            formatted_lines.append(f"<p class='progress-line'><b>{line}</b></p>")
                        else:
                            formatted_lines.append(f"<p class='progress-line'>{line}</p>")
                    
                    status_box.markdown(
                        "<div class='status-box'>" + "".join(formatted_lines) + "</div>", 
                        unsafe_allow_html=True
                    )
                
                # Check if the result is available (backup method)
                if report_content is None:  # Only check if we haven't gotten it yet
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
        
        # Check if we have a report
        if report_content:
            st.markdown("<h2 class='section-header'>Your Research Report</h2>", unsafe_allow_html=True)
            
            # Display the report content in a nice text box with proper formatting
            st.markdown("<div class='report-container'>" + 
                        markdown.markdown(report_content, extensions=['tables', 'fenced_code']) + 
                        "</div>", unsafe_allow_html=True)
            
            # Create PDF filename
            pdf_filename = f"{topic.replace(' ', '_')}_report.pdf"
            temp_pdf_path = os.path.join(tempfile.gettempdir(), pdf_filename)
            
            # Generate PDF using ReportLab
            with st.spinner("Preparing PDF for download..."):
                logger.info(f"Generating PDF for topic: {topic}")
                success = markdown_to_pdf_reportlab(report_content, topic, temp_pdf_path)
                if success:
                    logger.info(f"PDF generated successfully for topic: {topic}")
                else:
                    logger.error(f"PDF generation failed for topic: {topic}")
            
            if success:
                # Save to Supabase storage
                try:
                    saved_path = save_report(st.session_state.user.id, topic, report_content)
                    if saved_path:
                        logger.info(f"Report successfully saved to storage for user {st.session_state.user.id}, topic: {topic}")
                        st.success(f"Report automatically saved! ✅")
                    else:
                        logger.warning(f"Unable to save report to cloud storage for user {st.session_state.user.id}, topic: {topic}")
                        st.warning("Note: Unable to save report to cloud storage.")
                except Exception as save_error:
                    logger.error(f"Error saving report to storage: {str(save_error)}")
                    st.warning(f"Note: Report generated but not saved to cloud storage. You can still download it.")
                    logger.error(f"Detailed error saving to storage: {str(save_error)}")
                
                # Create columns for the PDF preview and download button
                col1, col2 = st.columns([1, 1])
                with col1:
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
                    
                with col2:
                    # Copy button with fixed functionality
                    copy_button = st.button("Copy Report", key="copy_report_main")
                    if copy_button:
                        if copy_to_clipboard(report_content):
                            st.success("Report copied to clipboard! ✨")
                            time.sleep(1)
                        else:
                            st.warning("Could not copy to clipboard. Please try selecting and copying manually.")
                            time.sleep(1)
            
                # Clean up the temp file
                os.remove(temp_pdf_path)

        else:
            st.error("Failed to generate the report. Please try again.")
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

else:
    # Show a welcome message for non-authenticated users
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1 class='gradient-text'>Welcome to DeepResearch AI</h1>
        <p style="font-size: 1.2rem; margin: 2rem 0;">
            Please login or sign up to access the AI-powered research report generator.
        </p>
    </div>
    """, unsafe_allow_html=True)

# Add a footer
st.markdown("""
<div style="position: fixed; bottom: 0; left: 0; right: 0; background: rgba(20, 30, 48, 0.8); backdrop-filter: blur(10px); padding: 1rem; text-align: center; border-top: 1px solid rgba(255, 60, 172, 0.2);">
    <p style="margin: 0; font-size: 0.8rem; opacity: 0.7;">© 2025 DeepResearch AI • Powered by LangGraph and Tavily</p>
</div>
""", unsafe_allow_html=True)

def save_new_report(topic, content):
    """Save a new report to Supabase storage"""
    if st.session_state.authenticated:
        try:
            file_path = save_report(st.session_state.user.id, topic, content)
            if file_path:
                st.success(f"Report saved: {topic}")
                return True
            else:
                st.error("Failed to save report. Please try again.")
                return False
        except Exception as e:
            st.error(f"Error saving report: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    else:
        st.warning("Please log in to save reports")
        return False
