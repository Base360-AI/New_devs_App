"""
Persistent Session Management - Backend Implementation

This module provides server-side session tracking and validation to support
persistent authentication that survives app switching and network issues.

Features:
- Server-side session tracking with database storage
- Device-based session validation
- Session fingerprinting for security
- Automatic session cleanup
- Multi-device session management
"""

import logging
import hashlib
import json
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer
from sqlalchemy import Column, String, DateTime, Boolean, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session as DBSession

from ..database import supabase
from ..models.auth import AuthenticatedUser
from .auth import authenticate_request
from .token_encryption import TokenEncryptionService
from ..config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

class PersistentSession(Base):
    """Database model for persistent sessions"""
    __tablename__ = "persistent_sessions"
    
    session_id = Column(String(255), primary_key=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=True, index=True)
    device_id = Column(String(255), nullable=False, index=True)
    device_fingerprint = Column(Text, nullable=True)
    access_token_hash = Column(String(255), nullable=False)
    refresh_token_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_activity = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_user_device', 'user_id', 'device_id'),
        Index('idx_tenant_active', 'tenant_id', 'is_active'),
        Index('idx_expires_active', 'expires_at', 'is_active'),
    )

class PersistentSessionManager:
    """Manages persistent sessions with security and cleanup"""
    
    # Session configuration
    SESSION_DURATION = timedelta(days=7)  # Sessions last 7 days
    MAX_SESSIONS_PER_USER = 10  # Maximum active sessions per user
    CLEANUP_INTERVAL = timedelta(hours=1)  # Run cleanup every hour
    
    # Initialize token encryption service
    _encryption_service = None
    
    @classmethod
    def get_encryption_service(cls) -> TokenEncryptionService:
        """Get or create token encryption service instance"""
        if cls._encryption_service is None:
            cls._encryption_service = TokenEncryptionService(settings.token_encryption_key)
        return cls._encryption_service
    
    @staticmethod
    def hash_token(token: str) -> str:
        """DEPRECATED: Create secure hash of token for storage
        
        This method is deprecated and kept only for backward compatibility.
        Use encrypt_token() instead for new sessions.
        """
        return hashlib.sha256(token.encode()).hexdigest()
    
    @classmethod
    def encrypt_token(cls, token: str) -> Dict[str, str]:
        """Encrypt a token using AES-256-GCM
        
        Returns:
            Dictionary with 'encrypted_value', 'iv', 'tag' keys
        """
        encryption_service = cls.get_encryption_service()
        encrypted_value, iv, tag = encryption_service.encrypt_token(token)
        return {
            'encrypted_value': encrypted_value,
            'iv': iv,
            'tag': tag
        }
    
    @classmethod
    def decrypt_token(cls, encrypted_data: Dict[str, str]) -> str:
        """Decrypt a token using AES-256-GCM
        
        Args:
            encrypted_data: Dictionary with 'encrypted_value', 'iv', 'tag' keys
            
        Returns:
            Decrypted token string
        """
        encryption_service = cls.get_encryption_service()
        return encryption_service.decrypt_token(
            encrypted_data['encrypted_value'],
            encrypted_data['iv'],
            encrypted_data['tag']
        )
    
    @staticmethod
    def generate_device_fingerprint(user_agent: str = None, ip_address: str = None) -> str:
        """Generate device fingerprint for additional security"""
        fingerprint_data = {
            'user_agent': user_agent or '',
            'timestamp': datetime.utcnow().isoformat(),
        }
        fingerprint_string = json.dumps(fingerprint_data, sort_keys=True)
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()
    
    @staticmethod
    async def create_session(
        user_id: str,
        tenant_id: str,
        device_id: str,
        access_token: str,
        refresh_token: str = None,
        user_agent: str = None,
        ip_address: str = None,
        db: DBSession = None
    ) -> PersistentSession:
        """Create a new persistent session"""
        try:
            logger.info(f"Creating persistent session for user {user_id}, tenant {tenant_id}")
            
            if not db:
                # In a real implementation, you'd use dependency injection
                # For now, we'll use Supabase for session storage
                pass
            
            # Generate cryptographically secure session ID
            session_id = secrets.token_urlsafe(32)
            
            # Create device fingerprint
            device_fingerprint = PersistentSessionManager.generate_device_fingerprint(
                user_agent, ip_address
            )
            
            # Calculate expiration
            expires_at = datetime.utcnow() + PersistentSessionManager.SESSION_DURATION
            
            # Encrypt tokens for secure storage
            access_token_encrypted = PersistentSessionManager.encrypt_token(access_token)
            refresh_token_encrypted = PersistentSessionManager.encrypt_token(refresh_token) if refresh_token else None
            
            # Create session record with encrypted tokens
            session_data = {
                'session_id': session_id,
                'user_id': user_id,
                'tenant_id': tenant_id,
                'device_id': device_id,
                'device_fingerprint': device_fingerprint,
                # Store encrypted token data as JSON
                'access_token_hash': json.dumps(access_token_encrypted),
                'refresh_token_hash': json.dumps(refresh_token_encrypted) if refresh_token_encrypted else None,
                'created_at': datetime.utcnow().isoformat(),
                'last_activity': datetime.utcnow().isoformat(),
                'expires_at': expires_at.isoformat(),
                'is_active': True,
                'user_agent': user_agent,
                'ip_address': ip_address,
            }
            
            # Store in Supabase (using persistent_sessions table if it exists)
            try:
                result = supabase.service.table('persistent_sessions').insert(session_data).execute()
                if result and getattr(result, 'data', None):
                    logger.info(f"Persistent session created successfully: {session_id}")
                    await PersistentSessionManager.cleanup_user_sessions(user_id)
                    return result.data[0]
            except Exception as db_err:
                logger.warning(f"persistent_sessions DB table write skipped: {db_err}")

            return session_data
            
        except Exception as e:
            logger.error(f"Error creating persistent session: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create session: {str(e)}"
            )
    
    @staticmethod
    async def validate_session(
        session_id: str,
        device_id: str,
        user_id: str,
        access_token: str = None
    ) -> Dict[str, Any]:
        """Validate a persistent session"""
        try:
            logger.info(f"Validating persistent session: {session_id}")
            
            # Get session from database
            result = supabase.service.table('persistent_sessions').select(
                '*'
            ).eq('session_id', session_id).eq('is_active', True).execute()
            
            if not result.data:
                logger.warning(f"Session not found: {session_id}")
                return {'valid': False, 'reason': 'session_not_found'}
            
            session = result.data[0]
            
            # Validate session ownership
            if session['user_id'] != user_id:
                logger.warning(f"Session user mismatch: {session_id}")
                return {'valid': False, 'reason': 'user_mismatch'}
            
            # Validate device
            if session['device_id'] != device_id:
                logger.warning(f"Session device mismatch: {session_id}")
                return {'valid': False, 'reason': 'device_mismatch'}
            
            # Check expiration
            expires_at = datetime.fromisoformat(session['expires_at'].replace('Z', '+00:00'))
            if datetime.utcnow() > expires_at:
                logger.warning(f"Session expired: {session_id}")
                # Mark session as inactive
                await PersistentSessionManager.deactivate_session(session_id)
                return {'valid': False, 'reason': 'session_expired'}
            
            # Validate access token if provided
            if access_token:
                try:
                    # Try to decrypt stored token for comparison
                    stored_token_data = json.loads(session['access_token_hash'])
                    decrypted_token = PersistentSessionManager.decrypt_token(stored_token_data)
                    if decrypted_token != access_token:
                        logger.warning(f"Session token mismatch: {session_id}")
                        return {'valid': False, 'reason': 'token_mismatch'}
                except (json.JSONDecodeError, KeyError, Exception) as e:
                    # Fallback to hash comparison for backward compatibility with old sessions
                    logger.debug(f"Falling back to hash comparison for session {session_id}: {e}")
                    token_hash = PersistentSessionManager.hash_token(access_token)
                    if session['access_token_hash'] != token_hash:
                        logger.warning(f"Session token mismatch (hash): {session_id}")
                        return {'valid': False, 'reason': 'token_mismatch'}
            
            # Update last activity
            await PersistentSessionManager.update_session_activity(session_id)
            
            logger.info(f"Session validated successfully: {session_id}")
            return {
                'valid': True,
                'session': session,
                'tenant_id': session['tenant_id'],
                'device_id': session['device_id']
            }
            
        except Exception as e:
            logger.error(f"Error validating session {session_id}: {str(e)}")
            return {'valid': False, 'reason': 'validation_error', 'error': str(e)}
    
    @staticmethod
    async def update_session_activity(session_id: str) -> bool:
        """Update session last activity timestamp"""
        try:
            result = supabase.service.table('persistent_sessions').update({
                'last_activity': datetime.utcnow().isoformat()
            }).eq('session_id', session_id).eq('is_active', True).execute()
            
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error updating session activity {session_id}: {str(e)}")
            return False
    
    @staticmethod
    async def update_session_token(
        session_id: str,
        new_access_token: str,
        new_refresh_token: str = None
    ) -> bool:
        """Update session tokens after refresh"""
        try:
            # Encrypt new tokens
            access_token_encrypted = PersistentSessionManager.encrypt_token(new_access_token)
            
            update_data = {
                'access_token_hash': json.dumps(access_token_encrypted),
                'last_activity': datetime.utcnow().isoformat()
            }
            
            if new_refresh_token:
                refresh_token_encrypted = PersistentSessionManager.encrypt_token(new_refresh_token)
                update_data['refresh_token_hash'] = json.dumps(refresh_token_encrypted)
            
            result = supabase.service.table('persistent_sessions').update(
                update_data
            ).eq('session_id', session_id).eq('is_active', True).execute()
            
            logger.info(f"Session tokens updated: {session_id}")
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error updating session tokens {session_id}: {str(e)}")
            return False
    
    @staticmethod
    async def deactivate_session(session_id: str) -> bool:
        """Deactivate a specific session"""
        try:
            result = supabase.service.table('persistent_sessions').update({
                'is_active': False,
                'last_activity': datetime.utcnow().isoformat()
            }).eq('session_id', session_id).execute()
            
            logger.info(f"Session deactivated: {session_id}")
            return len(result.data) > 0
            
        except Exception as e:
            logger.error(f"Error deactivating session {session_id}: {str(e)}")
            return False
    
    @staticmethod
    async def deactivate_user_sessions(user_id: str, exclude_session_id: str = None) -> int:
        """Deactivate all sessions for a user (except optionally one)"""
        try:
            query = supabase.service.table('persistent_sessions').update({
                'is_active': False,
                'last_activity': datetime.utcnow().isoformat()
            }).eq('user_id', user_id).eq('is_active', True)
            
            if exclude_session_id:
                query = query.neq('session_id', exclude_session_id)
            
            result = query.execute()
            
            deactivated_count = len(result.data)
            logger.info(f"Deactivated {deactivated_count} sessions for user {user_id}")
            return deactivated_count
            
        except Exception as e:
            logger.error(f"Error deactivating user sessions {user_id}: {str(e)}")
            return 0
    
    @staticmethod
    async def cleanup_user_sessions(user_id: str) -> int:
        """Clean up old/excess sessions for a user"""
        try:
            # Get active sessions for user, ordered by last activity (newest first)
            result = supabase.service.table('persistent_sessions').select(
                'session_id'
            ).eq('user_id', user_id).eq('is_active', True).order(
                'last_activity', desc=True
            ).execute()
            
            active_sessions = result.data
            
            # If user has too many sessions, deactivate oldest ones
            if len(active_sessions) > PersistentSessionManager.MAX_SESSIONS_PER_USER:
                excess_sessions = active_sessions[PersistentSessionManager.MAX_SESSIONS_PER_USER:]
                session_ids_to_deactivate = [s['session_id'] for s in excess_sessions]
                
                # Deactivate excess sessions
                for session_id in session_ids_to_deactivate:
                    await PersistentSessionManager.deactivate_session(session_id)
                
                logger.info(f"Cleaned up {len(session_ids_to_deactivate)} excess sessions for user {user_id}")
                return len(session_ids_to_deactivate)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error cleaning up user sessions {user_id}: {str(e)}")
            return 0
    
    @staticmethod
    async def cleanup_expired_sessions() -> int:
        """Clean up all expired sessions (should be run periodically)"""
        try:
            current_time = datetime.utcnow().isoformat()
            
            # Get expired active sessions
            result = supabase.service.table('persistent_sessions').select(
                'session_id'
            ).eq('is_active', True).lt('expires_at', current_time).execute()
            
            expired_sessions = result.data
            
            if expired_sessions:
                # Deactivate expired sessions
                session_ids = [s['session_id'] for s in expired_sessions]
                
                for session_id in session_ids:
                    await PersistentSessionManager.deactivate_session(session_id)
                
                logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
                return len(expired_sessions)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {str(e)}")
            return 0
    
    @staticmethod
    async def get_user_sessions(user_id: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all sessions for a user"""
        try:
            query = supabase.service.table('persistent_sessions').select(
                'session_id, device_id, created_at, last_activity, expires_at, is_active, user_agent, ip_address'
            ).eq('user_id', user_id)
            
            if active_only:
                query = query.eq('is_active', True)
            
            result = query.order('last_activity', desc=True).execute()
            
            return result.data
            
        except Exception as e:
            logger.error(f"Error getting user sessions {user_id}: {str(e)}")
            return []

# Session validation endpoint dependencies
security = HTTPBearer(auto_error=False)

async def validate_persistent_session(
    session_id: str,
    device_id: str,
    user_id: str,
    access_token: str = None
) -> Dict[str, Any]:
    """Dependency for validating persistent sessions in endpoints"""
    return await PersistentSessionManager.validate_session(
        session_id, device_id, user_id, access_token
    )

async def get_or_create_persistent_session(
    user: AuthenticatedUser = Depends(authenticate_request),
    session_id: str = None,
    device_id: str = None,
    user_agent: str = None,
    ip_address: str = None
) -> PersistentSession:
    """Get existing session or create new one for authenticated user"""
    
    if session_id and device_id:
        # Try to validate existing session
        validation_result = await PersistentSessionManager.validate_session(
            session_id, device_id, user.id
        )
        
        if validation_result['valid']:
            logger.info(f"Using existing persistent session: {session_id}")
            return validation_result['session']
    
    # Create new session
    logger.info(f"Creating new persistent session for user {user.id}")
    
    # For this implementation, we'll create a basic session
    # In a real implementation, you'd get the actual access and refresh tokens
    access_token = "dummy_access_token"  # This would be the actual JWT token
    
    return await PersistentSessionManager.create_session(
        user_id=user.id,
        tenant_id=user.tenant_id or '',
        device_id=device_id or f"device_{user.id}_{datetime.utcnow().timestamp()}",
        access_token=access_token,
        user_agent=user_agent,
        ip_address=ip_address
    )