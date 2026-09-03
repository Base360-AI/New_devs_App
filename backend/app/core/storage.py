"""
Storage helper functions for Supabase storage buckets
"""

import logging
from typing import Optional
from ..database import supabase

logger = logging.getLogger(__name__)

async def upload_to_storage(bucket_name: str, file_path: str, file_content: bytes, content_type: str) -> str:
    """
    Upload a file to Supabase storage and return the public URL
    
    Args:
        bucket_name: Name of the storage bucket
        file_path: Path within the bucket (e.g., "covers/guide-id/file.jpg")
        file_content: File content as bytes
        content_type: MIME type of the file
    
    Returns:
        Public URL of the uploaded file
    """
    try:
        # Upload file to storage
        response = supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": content_type}
        )
        
        # Get public URL
        public_url = supabase.storage.from_(bucket_name).get_public_url(file_path)
        
        return public_url
        
    except Exception as e:
        logger.error(f"Failed to upload to storage: {str(e)}")
        raise

async def delete_from_storage(bucket_name: str, file_path: str) -> bool:
    """
    Delete a file from Supabase storage
    
    Args:
        bucket_name: Name of the storage bucket
        file_path: Path within the bucket
    
    Returns:
        True if successful, False otherwise
    """
    try:
        response = supabase.storage.from_(bucket_name).remove([file_path])
        return True
    except Exception as e:
        logger.error("Failed to delete from storage: %s", type(e).__name__)
        return False

async def get_storage_url(bucket_name: str, file_path: str) -> str:
    """
    Get the public URL for a file in storage
    
    Args:
        bucket_name: Name of the storage bucket
        file_path: Path within the bucket
    
    Returns:
        Public URL of the file
    """
    return supabase.storage.from_(bucket_name).get_public_url(file_path)
