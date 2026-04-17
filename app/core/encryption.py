"""
PII Encryption Module
Provides field-level encryption for GDPR compliance
"""
import logging
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import settings

logger = logging.getLogger(__name__)


class PIIEncryption:
    """
    Field-level encryption for PII (Personally Identifiable Information).
    Uses Fernet (symmetric encryption) for secure, reversible encryption.
    """
    
    def __init__(self):
        self._cipher = None
        self._initialize_cipher()
    
    def _initialize_cipher(self):
        """Initialize Fernet cipher from settings"""
        if not settings.PII_ENCRYPTION_KEY:
            logger.warning(
                "PII_ENCRYPTION_KEY not set. PII will be stored in plaintext. "
                "Generate a key with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )
            return
        
        try:
            # Validate key format
            key_bytes = settings.PII_ENCRYPTION_KEY.encode() if isinstance(settings.PII_ENCRYPTION_KEY, str) else settings.PII_ENCRYPTION_KEY
            self._cipher = Fernet(key_bytes)
            logger.info("PII encryption initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize PII encryption: {e}")
            self._cipher = None
    
    def encrypt(self, plaintext: Optional[str]) -> Optional[bytes]:
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext: String to encrypt (e.g., email, name, phone)
        
        Returns:
            Encrypted bytes, or None if plaintext is None
        """
        if plaintext is None:
            return None
        
        if not self._cipher:
            # Encryption not configured - return plaintext as bytes (fallback)
            logger.warning("PII encryption not configured - storing in plaintext")
            return plaintext.encode('utf-8')
        
        try:
            plaintext_bytes = plaintext.encode('utf-8')
            encrypted = self._cipher.encrypt(plaintext_bytes)
            return encrypted
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            # Fallback to plaintext to avoid data loss
            return plaintext.encode('utf-8')
    
    def decrypt(self, ciphertext: Optional[bytes]) -> Optional[str]:
        """
        Decrypt ciphertext back to plaintext.
        
        Args:
            ciphertext: Encrypted bytes
        
        Returns:
            Decrypted string, or None if ciphertext is None
        """
        if ciphertext is None:
            return None
        
        if not self._cipher:
            # Encryption not configured - assume plaintext
            try:
                return ciphertext.decode('utf-8')
            except Exception:
                return None
        
        try:
            decrypted_bytes = self._cipher.decrypt(ciphertext)
            return decrypted_bytes.decode('utf-8')
        except InvalidToken:
            # Data might be plaintext (migration scenario)
            try:
                plaintext = ciphertext.decode('utf-8')
                logger.warning("Decryption failed - data appears to be plaintext")
                return plaintext
            except Exception:
                logger.error("Failed to decrypt or decode data")
                return None
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return None
    
    def is_enabled(self) -> bool:
        """Check if encryption is properly configured"""
        return self._cipher is not None


# Global encryption instance
_pii_encryption = PIIEncryption()


def encrypt_field(value: Optional[str]) -> Optional[bytes]:
    """Encrypt a PII field"""
    return _pii_encryption.encrypt(value)


def decrypt_field(value: Optional[bytes]) -> Optional[str]:
    """Decrypt a PII field"""
    return _pii_encryption.decrypt(value)


def is_encryption_enabled() -> bool:
    """Check if PII encryption is enabled"""
    return _pii_encryption.is_enabled()
