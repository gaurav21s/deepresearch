import streamlit as st
import supabase
from supabase.client import Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Supabase client
supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_KEY", "")
supabase_client = supabase.create_client(supabase_url, supabase_key)

def sign_up(email, password, full_name):
    """Handle user sign up"""
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
            st.rerun()
        return response
    except Exception as e:
        st.error(f"Error signing up: {str(e)}")
        return None

def sign_in(email, password):
    """Handle user sign in"""
    try:
        response = supabase_client.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        if response and response.user:
            st.session_state.authenticated = True
            st.session_state.user = response.user
            st.rerun()
        return response
    except Exception as e:
        st.error(f"Error signing in: {str(e)}")
        return None

def sign_out():
    """Handle user sign out"""
    try:
        supabase_client.auth.sign_out()
        st.session_state.authenticated = False
        st.session_state.user = None
        st.rerun()
    except Exception as e:
        st.error(f"Error signing out: {str(e)}")

def initialize_auth_state():
    """Initialize authentication state in session"""
    if 'authenticated' not in st.session_state:
        st.session_state.authenticated = False
    if 'user' not in st.session_state:
        st.session_state.user = None 