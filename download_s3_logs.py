import boto3
import os
from botocore.client import Config

# S3 credentials and config
s3_endpoint = "https://axioagieqarn.compat.objectstorage.me-jeddah-1.oraclecloud.com"
s3_region = "me-jeddah-1"
s3_access_key_id = "04104cc3a5f6444db0ee5ccf07c6e11a342ce1bc"
s3_secret_access_key = "5aDeiF/diaBEkNmFEXS41FbUYPCLFkKeUU4IfyCs2ns="

# S3 Path details
bucket_name = "bucket-nonprod-dm-datalake"
prefix = "airflow_sit_logs/dag_id=dag_PopulateBridgeTable_Isolated/run_id=manual__2026-05-13T07:16:20.186414+00:00"
download_dir = "./downloaded_logs"

def download_s3_folder():
    # Initialize boto3 client with path style addressing
    s3_client = boto3.client(
        's3',
        endpoint_url=s3_endpoint,
        region_name=s3_region,
        aws_access_key_id=s3_access_key_id,
        aws_secret_access_key=s3_secret_access_key,
        config=Config(s3={'addressing_style': 'path'})
    )
    
    # Create local directory if it doesn't exist
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
        
    print(f"Fetching objects from s3://{bucket_name}/{prefix}")
    
    # List objects within the specified prefix
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    
    downloaded_count = 0
    try:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    object_key = obj['Key']
                    # Skip if it's just a directory marker
                    if object_key.endswith('/'):
                        continue
                    
                    # Determine local file path
                    # We will preserve the structure relative to the prefix
                    relative_path = os.path.relpath(object_key, prefix)
                    
                    # If the file is exactly the prefix (not likely given it's a directory structure, but just in case)
                    if relative_path == '.':
                        relative_path = os.path.basename(object_key)
                        
                    local_file_path = os.path.join(download_dir, relative_path)
                    
                    # Ensure local directory exists
                    local_file_dir = os.path.dirname(local_file_path)
                    if not os.path.exists(local_file_dir):
                        os.makedirs(local_file_dir)
                    
                    print(f"Downloading {object_key} to {local_file_path}")
                    s3_client.download_file(bucket_name, object_key, local_file_path)
                    downloaded_count += 1
                    
        if downloaded_count == 0:
            print("No files found to download.")
        else:
            print(f"Successfully downloaded {downloaded_count} files.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    download_s3_folder()
