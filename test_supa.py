import os
import json
from datetime import datetime
import traceback
from dotenv import load_dotenv
import supabase

# Load environment variables
load_dotenv()

# Get Supabase credentials
supabase_url = os.environ.get("SUPABASE_URL", "")
supabase_key = os.environ.get("SUPABASE_KEY", "")

# If credentials are not in environment, prompt user
if not supabase_url or not supabase_key:
    print("Supabase credentials not found in environment variables.")
    supabase_url = input("Enter your Supabase URL: ").strip()
    supabase_key = input("Enter your Supabase API key: ").strip()

# Initialize Supabase client
if supabase_url and supabase_key:
    try:
        print(f"Connecting to Supabase at: {supabase_url}")
        supabase_client = supabase.create_client(supabase_url, supabase_key)
        print("Successfully connected to Supabase!")
    except Exception as e:
        print(f"Error connecting to Supabase: {str(e)}")
        traceback.print_exc()
        exit(1)
else:
    print("Error: Supabase credentials are required.")
    exit(1)

# File path to upload
file_path = "/Users/Admin/Desktop/Project/deepresearch/saved_reports/21c40eb2-abb9-4899-9a68-b56b54e943ab/Deep_dive_equity_research_analysis_of_Zomato_company_20250331_133804.md"

# Get filename only to fix path issues
file_name = os.path.basename(file_path)
# Fix any spaces in the filename
if " " in file_name:
    print(f"Warning: Filename contains spaces: {file_name}")
    file_name = file_name.replace(" ", "_")
    print(f"Renamed to: {file_name}")

# Bucket name
bucket_name = "deepresearch-reports"

def create_bucket_if_not_exists(bucket_name):
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
    
    # Let's check if we can list files in the bucket as a test
    try:
        print(f"Testing access to bucket '{bucket_name}'...")
        files = supabase_client.storage.from_(bucket_name).list()
        print(f"Successfully accessed bucket '{bucket_name}'. Files count: {len(files)}")
    except Exception as e:
        print(f"Warning: Cannot list files in bucket {bucket_name}: {str(e)}")

def upload_file(file_path, user_id="test_user"):
    """Upload a file to Supabase storage"""
    print(f"Uploading file: {file_path}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}")
        return None
    
    # Get file name and create user folder path
    file_name = os.path.basename(file_path)
    # Ensure no spaces in filename
    file_name = file_name.replace(" ", "_")
    
    user_folder = f"{user_id}/"
    storage_path = f"{user_folder}{file_name}"
    
    # Read file content
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"File read successfully, size: {len(content)} bytes")
            
        # Get file metadata from filename
        # Extract topic and timestamp from filename
        name_parts = file_name.rsplit("_", 2)
        if len(name_parts) >= 3:
            topic = "_".join(name_parts[:-2]).replace("_", " ")
            timestamp_str = f"{name_parts[-2]}_{name_parts[-1].replace('.md', '')}"
            
            # Create metadata
            metadata = {
                "topic": topic,
                "timestamp": timestamp_str,
                "filename": file_name,
                "user_id": user_id,
                "uploaded_at": datetime.now().strftime("%Y%m%d_%H%M%S")
            }
            print(f"Metadata: {json.dumps(metadata, indent=2)}")
            
            # Upload file
            try:
                print(f"Uploading to {storage_path}...")
                # Try with simpler approach first
                try:
                    supabase_client.storage.from_(bucket_name).upload(
                        path=storage_path,
                        file=content.encode('utf-8')
                    )
                except Exception as upload_error:
                    print(f"First upload attempt failed: {str(upload_error)}")
                    print("Trying alternative method...")
                    
                    # Create a temporary file
                    temp_file = os.path.join(os.getcwd(), "temp_upload.md")
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # Upload from file
                    with open(temp_file, 'rb') as f:
                        supabase_client.storage.from_(bucket_name).upload(
                            path=storage_path,
                            file=f
                        )
                    
                    # Clean up temp file
                    os.remove(temp_file)
                
                print("✅ File uploaded successfully!")
                
                # Upload metadata
                metadata_path = f"{user_folder}{file_name}.meta.json"
                print(f"Uploading metadata to {metadata_path}...")
                
                # Try with simpler approach first for metadata
                try:
                    supabase_client.storage.from_(bucket_name).upload(
                        path=metadata_path,
                        file=json.dumps(metadata).encode('utf-8')
                    )
                except Exception as meta_error:
                    print(f"First metadata upload attempt failed: {str(meta_error)}")
                    print("Trying alternative method for metadata...")
                    
                    # Create a temporary file for metadata
                    temp_meta = os.path.join(os.getcwd(), "temp_meta.json")
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
                
                print("✅ Metadata uploaded successfully!")
                
                return storage_path
                
            except Exception as e:
                print(f"Error uploading file: {str(e)}")
                traceback.print_exc()
                return None
        else:
            print("Error: Invalid filename format, cannot extract metadata")
            return None
            
    except Exception as e:
        print(f"Error reading file: {str(e)}")
        return None

def download_file(file_path, user_id="test_user"):
    """Download a file from Supabase storage"""
    try:
        # Determine if path is full or just filename
        if "/" not in file_path:  # Just a filename
            storage_path = f"{user_id}/{file_path}"
        else:  # Full path
            storage_path = file_path
            
        print(f"Downloading file from {storage_path}...")
        
        # Download the file
        data = supabase_client.storage.from_(bucket_name).download(storage_path)
        
        # Create download directory if it doesn't exist
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        # Save to local file
        local_path = os.path.join(download_dir, os.path.basename(storage_path))
        with open(local_path, 'wb') as f:
            f.write(data)
            
        print(f"✅ File downloaded to: {local_path}")
        
        # Check if metadata file exists and download it too
        try:
            meta_path = f"{storage_path}.meta.json"
            print(f"Downloading metadata from {meta_path}...")
            
            meta_data = supabase_client.storage.from_(bucket_name).download(meta_path)
            meta_local_path = os.path.join(download_dir, os.path.basename(meta_path))
            
            with open(meta_local_path, 'wb') as f:
                f.write(meta_data)
                
            print(f"✅ Metadata downloaded to: {meta_local_path}")
            
            # Print metadata content
            metadata = json.loads(meta_data.decode('utf-8'))
            print(f"Metadata content: {json.dumps(metadata, indent=2)}")
            
        except Exception as e:
            print(f"Note: Could not download metadata: {str(e)}")
            
        return local_path
        
    except Exception as e:
        print(f"Error downloading file: {str(e)}")
        traceback.print_exc()
        return None

def list_files(user_id="test_user"):
    """List files in user folder"""
    user_folder = f"{user_id}/"
    
    try:
        print(f"Listing files in {user_folder}...")
        files = supabase_client.storage.from_(bucket_name).list(path=user_folder)
        print(f"Found {len(files)} files:")
        for file in files:
            print(f"  - {file['name']}")
        
        # Filter metadata files
        meta_files = [file for file in files if file["name"].endswith(".meta.json")]
        content_files = [file for file in files if not file["name"].endswith(".meta.json") and not file["name"].endswith(".folder")]
        
        print(f"\nFound {len(content_files)} content files:")
        for content_file in content_files:
            print(f"  - {content_file['name']}")
        
        print(f"\nFound {len(meta_files)} metadata files:")
        for meta_file in meta_files:
            try:
                # Download metadata
                meta_path = f"{user_folder}{meta_file['name']}"
                print(f"Downloading metadata from {meta_path}...")
                data = supabase_client.storage.from_(bucket_name).download(meta_path)
                metadata = json.loads(data.decode('utf-8'))
                print(f"  - {meta_file['name']}: {metadata['topic']}")
            except Exception as e:
                print(f"  - Error reading {meta_file['name']}: {str(e)}")
        
        return files
    except Exception as e:
        print(f"Error listing files: {str(e)}")
        traceback.print_exc()
        return []

def delete_file(file_path, user_id="test_user"):
    """Delete a file from Supabase storage"""
    try:
        # Determine if path is full or just filename
        if "/" not in file_path:  # Just a filename
            storage_path = f"{user_id}/{file_path}"
        else:  # Full path
            storage_path = file_path
            
        print(f"Deleting file: {storage_path}...")
        
        # Delete the file
        supabase_client.storage.from_(bucket_name).remove([storage_path])
        print("✅ File deleted successfully!")
        
        # Try to delete metadata too
        try:
            meta_path = f"{storage_path}.meta.json"
            print(f"Deleting metadata: {meta_path}...")
            supabase_client.storage.from_(bucket_name).remove([meta_path])
            print("✅ Metadata deleted successfully!")
        except Exception as e:
            print(f"Note: Could not delete metadata: {str(e)}")
            
        return True
    except Exception as e:
        print(f"Error deleting file: {str(e)}")
        traceback.print_exc()
        return False

def test_user_id_input():
    """Prompt for user ID"""
    default_user_id = "test_user"
    user_input = input(f"Enter user ID (default: {default_user_id}): ").strip()
    return user_input if user_input else default_user_id

def main():
    """Main function"""
    print("=== Supabase Storage Test ===")
    
    # Ensure bucket exists
    create_bucket_if_not_exists(bucket_name)
    
    # Ask for user ID
    user_id = test_user_id_input()
    print(f"Using user ID: {user_id}")
    
    # Ask for user operation
    print("\nChoose operation:")
    print("1. Upload file")
    print("2. List files")
    print("3. Download file")
    print("4. Delete file")
    print("5. Upload and list")
    
    choice = input("Enter choice (1-5): ").strip()
    
    if choice == "1" or choice == "5":
        # Upload file
        print("\n--- Uploading File ---")
        storage_path = upload_file(file_path, user_id)
        if storage_path:
            print(f"File uploaded to: {storage_path}")
    
    if choice == "2" or choice == "5":
        # List files
        print("\n--- Listing Files ---")
        list_files(user_id)
        
    if choice == "3":
        # Download file
        print("\n--- Downloading File ---")
        file_to_download = input("Enter file name or path to download: ").strip()
        if file_to_download:
            download_file(file_to_download, user_id)
        else:
            print("No file specified for download")
            
    if choice == "4":
        # Delete file
        print("\n--- Deleting File ---")
        file_to_delete = input("Enter file name or path to delete: ").strip()
        if file_to_delete:
            delete_file(file_to_delete, user_id)
        else:
            print("No file specified for deletion")

if __name__ == "__main__":
    main() 