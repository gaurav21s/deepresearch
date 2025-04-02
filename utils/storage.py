import os
import json
import tempfile
from datetime import datetime
import streamlit as st
from supabase.client import Client
import traceback

def create_bucket_if_not_exists(supabase_client, bucket_name="deepresearch-reports"):
    """Create bucket if it doesn't exist"""
    try:
        # Check if the bucket exists
        print(f"Checking if bucket '{bucket_name}' exists...")
        supabase_client.storage.get_bucket(bucket_name)
        print(f"Bucket '{bucket_name}' already exists.")
    except Exception as e:
        # Create the bucket if it doesn't exist
        try:
            print(f"Creating bucket '{bucket_name}'...")
            supabase_client.storage.create_bucket(bucket_name, {"public": False})
            print(f"Successfully created bucket '{bucket_name}'")
        except Exception as e:
            print(f"Note: Using existing bucket '{bucket_name}', couldn't access directly: {str(e)}")
    
    # Test bucket access
    try:
        print(f"Testing access to bucket '{bucket_name}'...")
        files = supabase_client.storage.from_(bucket_name).list()
        print(f"Successfully accessed bucket '{bucket_name}'. Files count: {len(files)}")
    except Exception as e:
        print(f"Warning: Cannot list files in bucket {bucket_name}: {str(e)}")
    
    return bucket_name

def save_report(supabase_client, user_id, topic, content):
    """Save a report to Supabase storage"""
    bucket_name = "deepresearch-reports"
    user_folder = f"{user_id}/"
    
    # Create a unique filename with timestamp
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = topic.replace(' ', '_').replace('/', '_')
    file_name = f"{safe_topic}_{ts}.md"
    file_path = f"{user_folder}{file_name}"
    
    # Create metadata
    metadata = {
        "topic": topic,
        "timestamp": ts,
        "filename": file_name,
        "user_id": user_id,
        "uploaded_at": datetime.now().strftime("%Y%m%d_%H%M%S")
    }
    
    try:
        # Upload content
        try:
            print(f"Uploading to {file_path}...")
            supabase_client.storage.from_(bucket_name).upload(
                path=file_path,
                file=content.encode('utf-8')
            )
        except Exception as upload_error:
            print(f"First upload attempt failed: {str(upload_error)}")
            print("Trying alternative method...")
            
            temp_file = os.path.join(tempfile.gettempdir(), "temp_upload.md")
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            with open(temp_file, 'rb') as f:
                supabase_client.storage.from_(bucket_name).upload(
                    path=file_path,
                    file=f
                )
            
            os.remove(temp_file)
        
        print("✅ File uploaded successfully!")
        
        # Upload metadata
        metadata_path = f"{user_folder}{file_name}.meta.json"
        try:
            print(f"Uploading metadata to {metadata_path}...")
            supabase_client.storage.from_(bucket_name).upload(
                path=metadata_path,
                file=json.dumps(metadata).encode('utf-8')
            )
        except Exception as meta_error:
            print(f"First metadata upload attempt failed: {str(meta_error)}")
            print("Trying alternative method for metadata...")
            
            temp_meta = os.path.join(tempfile.gettempdir(), "temp_meta.json")
            with open(temp_meta, 'w', encoding='utf-8') as f:
                json.dump(metadata, f)
            
            with open(temp_meta, 'rb') as f:
                supabase_client.storage.from_(bucket_name).upload(
                    path=metadata_path,
                    file=f
                )
            
            os.remove(temp_meta)
        
        print("✅ Metadata uploaded successfully!")
        return file_path
    except Exception as e:
        st.error(f"Error saving report: {str(e)}")
        traceback.print_exc()
        return None

def load_saved_reports(supabase_client, user_id):
    """Load all saved reports from Supabase storage"""
    bucket_name = "deepresearch-reports"
    user_folder = f"{user_id}/"
    
    try:
        response = supabase_client.storage.from_(bucket_name).list(path=user_folder)
        meta_files = [file for file in response if file["name"].endswith(".meta.json")]
        content_files = [file for file in response if not file["name"].endswith(".meta.json") and not file["name"].endswith(".folder")]
        
        print(f"Found {len(meta_files)} metadata files, {len(content_files)} content files")
        
        reports = []
        for meta_file in meta_files:
            meta_path = f"{user_folder}{meta_file['name']}"
            try:
                print(f"Reading metadata from {meta_path}...")
                data = supabase_client.storage.from_(bucket_name).download(meta_path)
                metadata = json.loads(data.decode('utf-8'))
                
                try:
                    ts = datetime.strptime(metadata["timestamp"], "%Y%m%d_%H%M%S")
                    reports.append({
                        "topic": metadata["topic"],
                        "timestamp": ts,
                        "filename": metadata["filename"],
                        "path": f"{user_folder}{metadata['filename']}"
                    })
                except (ValueError, KeyError) as e:
                    print(f"Error processing metadata timestamp: {str(e)}")
                    continue
            except Exception as e:
                print(f"Error reading metadata file {meta_file['name']}: {str(e)}")
                continue
                
        return sorted(reports, key=lambda x: x["timestamp"], reverse=True)
    except Exception as e:
        print(f"Error loading reports: {str(e)}")
        traceback.print_exc()
        return []

def get_report_content(supabase_client, user_id, filename):
    """Get report content from Supabase storage"""
    bucket_name = "deepresearch-reports"
    
    if "/" in filename:
        file_path = filename
    else:
        file_path = f"{user_id}/{filename}"
    
    print(f"DEBUG - get_report_content: User ID: {user_id}, Filename: {filename}")
    print(f"DEBUG - get_report_content: Full path: {file_path}")
    
    try:
        print(f"Downloading report from {file_path}...")
        
        # Test bucket access
        try:
            print(f"Testing bucket '{bucket_name}' access...")
            files = supabase_client.storage.from_(bucket_name).list()
            print(f"Bucket '{bucket_name}' contains {len(files)} files/folders")
            
            try:
                user_path = f"{user_id}/"
                user_files = supabase_client.storage.from_(bucket_name).list(path=user_path)
                print(f"User directory '{user_path}' contains {len(user_files)} files")
                print(f"Files in user directory: {[f['name'] for f in user_files]}")
            except Exception as user_list_error:
                print(f"Error listing user directory: {str(user_list_error)}")
        except Exception as bucket_error:
            print(f"Error accessing bucket: {str(bucket_error)}")
        
        data = supabase_client.storage.from_(bucket_name).download(file_path)
        content = data.decode('utf-8')
        print(f"Successfully downloaded report ({len(content)} bytes)")
        return content
    except Exception as e:
        print(f"ERROR - get_report_content: {str(e)}")
        st.error(f"Error retrieving report: {str(e)}")
        traceback.print_exc()
        return None

def delete_report(supabase_client, user_id, filename):
    """Delete a report and its metadata from Supabase storage"""
    bucket_name = "deepresearch-reports"
    
    if "/" in filename:
        file_path = filename
    else:
        file_path = f"{user_id}/{filename}"
    
    meta_path = f"{file_path}.meta.json"
    
    try:
        print(f"Deleting report: {file_path}...")
        supabase_client.storage.from_(bucket_name).remove([file_path])
        print("✅ Report deleted successfully")
        
        try:
            print(f"Deleting metadata: {meta_path}...")
            supabase_client.storage.from_(bucket_name).remove([meta_path])
            print("✅ Metadata deleted successfully")
        except Exception as e:
            print(f"Note: Could not delete metadata: {str(e)}")
        
        return True
    except Exception as e:
        st.error(f"Error deleting report: {str(e)}")
        traceback.print_exc()
        return False 