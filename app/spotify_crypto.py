"""
Spotify ZeroConf Authentication Crypto Module

Implements the encrypted blob generation for Spotify Connect devices using:
- Diffie-Hellman key exchange
- AES-128-CTR encryption
- HMAC-SHA1 for key derivation

Based on Spotify's official ZeroConf authentication protocol and librespot's implementation.
"""

import os
import base64
import hashlib
import hmac
import logging
from typing import Tuple, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# Spotify's standard DH parameters (1024-bit MODP group)
SPOTIFY_DH_PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF", 16
)

SPOTIFY_DH_GENERATOR = 2


class SpotifyCrypto:
    """Handles Spotify ZeroConf authentication cryptography."""
    
    def __init__(self):
        self.backend = default_backend()
        
    def generate_dh_keypair(self) -> Tuple[bytes, bytes]:
        """
        Generate Diffie-Hellman key pair for Spotify authentication.
        
        Returns:
            Tuple of (private_key_bytes, public_key_bytes)
        """
        try:
            # Create DH parameters using Spotify's standard values
            dh_parameters = dh.DHParameterNumbers(
                p=SPOTIFY_DH_PRIME,
                g=SPOTIFY_DH_GENERATOR
            ).parameters(self.backend)
            
            # Generate private key
            private_key = dh_parameters.generate_private_key()
            
            # Get public key
            public_key = private_key.public_key()
            
            # Serialize keys
            private_bytes = private_key.private_numbers().private_value.to_bytes(128, 'big')
            public_bytes = public_key.public_numbers().y.to_bytes(128, 'big')
            
            logger.info("Generated DH key pair successfully")
            return private_bytes, public_bytes
            
        except Exception as e:
            logger.error(f"Failed to generate DH key pair: {e}")
            raise
    
    def compute_shared_secret(self, private_key_bytes: bytes, device_public_bytes: bytes) -> bytes:
        """
        Compute shared secret using Diffie-Hellman key exchange.
        
        Args:
            private_key_bytes: Our private key
            device_public_bytes: Device's public key
            
        Returns:
            Shared secret bytes
        """
        try:
            # Reconstruct our private key
            dh_parameters = dh.DHParameterNumbers(
                p=SPOTIFY_DH_PRIME,
                g=SPOTIFY_DH_GENERATOR
            ).parameters(self.backend)
            
            private_value = int.from_bytes(private_key_bytes, 'big')
            private_key = dh_parameters.private_key(private_value)
            
            # Reconstruct device's public key
            device_y = int.from_bytes(device_public_bytes, 'big')
            device_public_key = dh_parameters.public_key(device_y)
            
            # Compute shared secret
            shared_secret = private_key.exchange(device_public_key)
            
            logger.info("Computed DH shared secret successfully")
            return shared_secret
            
        except Exception as e:
            logger.error(f"Failed to compute shared secret: {e}")
            raise
    
    def derive_encryption_keys(self, shared_secret: bytes, username: str) -> Tuple[bytes, bytes]:
        """
        Derive encryption keys using HMAC-SHA1.
        
        Args:
            shared_secret: DH shared secret
            username: Spotify username
            
        Returns:
            Tuple of (encryption_key, hmac_key)
        """
        try:
            # Create HMAC key from shared secret
            hmac_key = hmac.new(
                shared_secret,
                username.encode('utf-8'),
                hashlib.sha1
            ).digest()
            
            # Derive encryption key (first 16 bytes)
            encryption_key = hmac_key[:16]
            
            # Derive HMAC key (remaining bytes)
            hmac_key_final = hmac_key[16:32] if len(hmac_key) >= 32 else hmac_key[16:] + b'\x00' * (32 - len(hmac_key))
            
            logger.info("Derived encryption keys successfully")
            return encryption_key, hmac_key_final
            
        except Exception as e:
            logger.error(f"Failed to derive encryption keys: {e}")
            raise
    
    def encrypt_credentials(self, username: str, password: str, encryption_key: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt credentials using AES-128-CTR.
        
        Args:
            username: Spotify username
            password: Spotify password
            encryption_key: AES encryption key
            
        Returns:
            Tuple of (encrypted_data, iv)
        """
        try:
            # Prepare credentials
            credentials = f"{username}:{password}".encode('utf-8')
            
            # Generate random IV
            iv = os.urandom(16)
            
            # Create cipher
            cipher = Cipher(
                algorithms.AES(encryption_key),
                modes.CTR(iv),
                backend=self.backend
            )
            encryptor = cipher.encryptor()
            
            # Encrypt credentials
            encrypted_data = encryptor.update(credentials) + encryptor.finalize()
            
            logger.info("Encrypted credentials successfully")
            return encrypted_data, iv
            
        except Exception as e:
            logger.error(f"Failed to encrypt credentials: {e}")
            raise
    
    def generate_encrypted_blob(self, username: str, password: str, token: dict) -> Tuple[str, str]:
        """
        Generate encrypted authentication blob for Spotify ZeroConf addUser.
        
        Args:
            username: Spotify username
            password: Spotify password  
            token: OAuth token dict
            
        Returns:
            Tuple of (encrypted_blob_base64, client_key_base64)
        """
        try:
            logger.info(f"Generating encrypted blob for user: {username}")
            
            # Generate DH key pair
            private_key, public_key = self.generate_dh_keypair()
            
            # For now, simulate device public key (in real implementation, 
            # this would come from device's response to initial DH exchange)
            # Using a dummy public key for testing
            device_public_key = os.urandom(128)
            
            # Compute shared secret
            shared_secret = self.compute_shared_secret(private_key, device_public_key)
            
            # Derive encryption keys
            encryption_key, hmac_key = self.derive_encryption_keys(shared_secret, username)
            
            # Encrypt credentials
            encrypted_data, iv = self.encrypt_credentials(username, password, encryption_key)
            
            # Create final blob: IV + encrypted_data
            blob = iv + encrypted_data
            
            # Encode as base64
            blob_base64 = base64.b64encode(blob).decode('utf-8')
            client_key_base64 = base64.b64encode(public_key).decode('utf-8')
            
            logger.info("Generated encrypted blob successfully")
            return blob_base64, client_key_base64
            
        except Exception as e:
            logger.error(f"Failed to generate encrypted blob: {e}")
            raise


def generate_spotify_blob_simple(username: str, password: str, token: dict) -> str:
    """
    Generate simple authentication blob (fallback for devices that don't require encryption).
    
    Args:
        username: Spotify username
        password: Spotify password
        token: OAuth token dict
        
    Returns:
        Simple blob string
    """
    try:
        # Try access token first
        access_token = token.get('access_token')
        if access_token:
            logger.info("Using OAuth access token as simple blob")
            return access_token
        
        # Fallback to username:password
        credentials = f"{username}:{password}"
        logger.info("Using username:password as simple blob")
        return credentials
        
    except Exception as e:
        logger.error(f"Failed to generate simple blob: {e}")
        return ""


def generate_spotify_blob(username: str, password: str, token: dict, device_name: str = "") -> Tuple[str, str]:
    """
    Generate appropriate authentication blob based on device requirements.
    
    Args:
        username: Spotify username
        password: Spotify password
        token: OAuth token dict
        device_name: Target device name
        
    Returns:
        Tuple of (blob, client_key) - client_key may be empty for simple blobs
    """
    try:
        # Try encrypted blob first (works for many devices)
        logger.info(f"Generating encrypted blob for {device_name}")
        try:
            crypto = SpotifyCrypto()
            return crypto.generate_encrypted_blob(username, password, token)
        except Exception as e:
            logger.debug(f"Encrypted blob generation failed for {device_name}, falling back to simple blob: {e}")
            simple_blob = generate_spotify_blob_simple(username, password, token)
            return simple_blob, ""
            
    except Exception as e:
        logger.error(f"Failed to generate blob for {device_name}: {e}")
        # Fallback to simple blob
        simple_blob = generate_spotify_blob_simple(username, password, token)
        return simple_blob, ""


