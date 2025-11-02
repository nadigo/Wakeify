"""
Spotify API client bridge between existing token management and playback module
"""

import logging
import time
import json
import os
from typing import List, Optional, Dict, Any

# Import playback module components
from alarm_playback.spotify_api import SpotifyApiWrapper, TokenManager
from alarm_playback.models import CloudDevice

from alarm_config import AlarmSystemConfig

logger = logging.getLogger(__name__)

# Token file path - use same path as main.py
TOKEN_FILE = os.path.join(os.environ.get("BASE_DIR", "/data/wakeify"), "data", "token.json")

def load_token_simple() -> Optional[Dict[str, Any]]:
    """Load token from file"""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load token: {e}")
    return None

def refresh_token_simple(token: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Refresh access token using refresh token"""
    if not token or 'refresh_token' not in token:
        return None
    
    # Check if token needs refresh (60 seconds before expiry)
    if time.time() <= token.get("expires_at", 0) - 60:
        return token
    
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyOAuth
        
        # Use environment variables for Spotify credentials
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI')
        
        if not all([client_id, client_secret, redirect_uri]):
            logger.error("Missing Spotify credentials in environment variables")
            return None
        
        sp_oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope="user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-read-private"
        )
        
        new_token = sp_oauth.refresh_access_token(token['refresh_token'])
        
        # Save the refreshed token
        save_token_simple(new_token)
        return new_token
        
    except Exception as e:
        logger.error(f"Failed to refresh token: {e}")
        return None

def save_token_simple(token: Dict[str, Any]) -> None:
    """Save token to file"""
    try:
        with open(TOKEN_FILE, 'w') as f:
            json.dump(token, f)
    except Exception as e:
        logger.error(f"Failed to save token: {e}")


class AlarmSpotifyClient:
    """Bridge between existing token management and playback module Spotify API"""
    
    def __init__(self, config: AlarmSystemConfig):
        self.config = config
        self.token_manager = TokenManager(config.spotify)
        self.api_wrapper = SpotifyApiWrapper(self.token_manager)
        self._device_cache = {"devices": [], "timestamp": 0, "ttl": 30}
    
    def get_devices(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Get available Spotify devices using legacy API for web interface
        
        Args:
            use_cache: Whether to use cached results if available
            
        Returns:
            List of device dictionaries for web interface
        """
        current_time = time.time()
        
        # Check cache validity
        if (use_cache and 
            self._device_cache["timestamp"] + self._device_cache["ttl"] > current_time):
            logger.debug("Using cached device list")
            return self._device_cache["devices"]
        
        try:
            # Use simple token system for web interface compatibility
            token = load_token_simple()
            if not token:
                logger.warning("No token available for devices")
                return []
            
            token = refresh_token_simple(token)
            if not token:
                logger.warning("Token refresh failed for devices")
                return []
            
            # Use spotipy directly for devices
            import spotipy
            sp = spotipy.Spotify(auth=token['access_token'])
            devices_data = sp.devices()
            
            # Convert to simple dictionaries for web interface
            devices = []
            for device_data in devices_data.get('devices', []):
                device_dict = {
                    'id': device_data['id'],
                    'name': device_data['name'],
                    'type': device_data['type'],
                    'is_active': device_data['is_active'],
                    'is_private_session': device_data.get('is_private_session', False),
                    'is_restricted': device_data.get('is_restricted', False),
                    'volume_percent': device_data.get('volume_percent', 0)
                }
                devices.append(device_dict)
            
            # Update cache
            self._device_cache = {
                "devices": devices,
                "timestamp": current_time,
                "ttl": 30
            }
            
            logger.info(f"Retrieved {len(devices)} devices from Spotify API")
            return devices
            
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
            return []
    
    def get_playlists(self) -> List[Dict[str, Any]]:
        """
        Get user's Spotify playlists using legacy API for web interface
        
        Returns:
            List of playlist dictionaries
        """
        try:
            # Use simple token system for web interface compatibility
            token = load_token_simple()
            if not token:
                logger.warning("No token available for playlists")
                return []
            
            token = refresh_token_simple(token)
            if not token:
                logger.warning("Token refresh failed for playlists")
                return []
            
            # Use spotipy directly for playlists
            import spotipy
            sp = spotipy.Spotify(auth=token['access_token'])
            playlists = sp.current_user_playlists(limit=50)
            
            # Convert to the format expected by the template
            playlist_items = []
            if playlists and 'items' in playlists:
                for playlist in playlists['items']:
                    playlist_items.append({
                        'name': playlist['name'],
                        'uri': playlist['uri'],
                        'id': playlist['id'],
                        'tracks': playlist.get('tracks', {}).get('total', 0)
                    })
            
            logger.info(f"Retrieved {len(playlist_items)} playlists from Spotify API")
            return playlist_items
            
        except Exception as e:
            logger.error(f"Failed to get playlists: {e}")
            return []
    
    def get_device_by_name(self, device_name: str) -> Optional[Dict[str, Any]]:
        """Get device by name"""
        devices = self.get_devices()
        
        # Try exact match first
        for device in devices:
            if device['name'] == device_name:
                return device
        
        # Try case-insensitive match
        for device in devices:
            if device['name'].lower() == device_name.lower():
                return device
        
        # Try partial match
        for device in devices:
            if device_name.lower() in device['name'].lower():
                return device
        
        return None
    
    def transfer_playback(self, device_id: str, play: bool = False) -> bool:
        """Transfer playback to device"""
        try:
            self.api_wrapper.put_transfer(device_id=device_id, play=play)
            logger.info(f"Transferred playback to device {device_id} (play={play})")
            return True
        except Exception as e:
            logger.error(f"Failed to transfer playback: {e}")
            return False
    
    def set_volume(self, device_id: str, volume_percent: int) -> bool:
        """Set device volume"""
        try:
            self.api_wrapper.put_volume(device_id=device_id, percent=volume_percent)
            logger.info(f"Set volume to {volume_percent}% for device {device_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set volume: {e}")
            return False
    
    def start_playback(self, device_id: str, context_uri: str, retry_404_delay_s: float = 0.7) -> bool:
        """Start playback on device"""
        try:
            self.api_wrapper.put_play(
                device_id=device_id, 
                context_uri=context_uri,
                retry_404_delay_s=retry_404_delay_s
            )
            logger.info(f"Started playback on device {device_id} with context {context_uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to start playback: {e}")
            return False
    
    def pause_playback(self, device_id: str) -> bool:
        """Pause playback on device"""
        try:
            self.api_wrapper.pause_playback(device_id=device_id)
            logger.info(f"Paused playback on device {device_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to pause playback: {e}")
            return False
    
    def get_current_playback(self) -> Optional[Dict[str, Any]]:
        """Get current playback state"""
        try:
            return self.api_wrapper.get_current_playback()
        except Exception as e:
            logger.error(f"Failed to get current playback: {e}")
            return None
    
    def is_device_online(self, device_name: str) -> bool:
        """Check if device is online and available"""
        device = self.get_device_by_name(device_name)
        return device is not None and device.is_active
    
    def wait_for_device(self, device_name: str, timeout_s: float = 20.0) -> Optional[CloudDevice]:
        """
        Wait for device to appear in Spotify API
        
        Args:
            device_name: Name of device to wait for
            timeout_s: Maximum time to wait
            
        Returns:
            CloudDevice if found, None if timeout
        """
        start_time = time.time()
        
        while time.time() - start_time < timeout_s:
            device = self.get_device_by_name(device_name)
            if device:
                logger.info(f"Device {device_name} found after {time.time() - start_time:.1f}s")
                return device
            
            time.sleep(0.5)
        
        logger.warning(f"Device {device_name} not found within {timeout_s}s")
        return None
    
    def get_device_health(self, device_name: str) -> Dict[str, Any]:
        """Get device health information"""
        device = self.get_device_by_name(device_name)
        
        if not device:
            return {
                "found": False,
                "online": False,
                "error": "Device not found in Spotify API"
            }
        
        return {
            "found": True,
            "online": device.is_active,
            "device_id": device.id,
            "name": device.name,
            "volume_percent": device.volume_percent,
            "device_type": device.device_type,
            "is_private_session": device.is_private_session,
            "is_restricted": device.is_restricted
        }
    
    def invalidate_cache(self) -> None:
        """Invalidate device cache to force fresh data"""
        self._device_cache["timestamp"] = 0
        logger.info("Device cache invalidated")


def refresh_token_legacy(token: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Legacy token refresh for backward compatibility"""
    if not token:
        return None
    
    # Check if token needs refresh (60 seconds before expiry)
    if time.time() <= token.get("expires_at", 0) - 60:
        return token
    
    try:
        import requests
        
        data = {
            "grant_type": "refresh_token",
            "refresh_token": token.get("refresh_token"),
        }
        
        if not data["refresh_token"]:
            logger.error("No refresh token available")
            return None
        
        # Get credentials from environment
        client_id = os.environ.get("SPOTIFY_CLIENT_ID")
        client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
        
        if not client_id or not client_secret:
            logger.error("Spotify credentials not configured")
            return None
        
        auth = (client_id, client_secret)
        response = requests.post(
            "https://accounts.spotify.com/api/token", 
            data=data, 
            auth=auth,
            timeout=10
        )
        response.raise_for_status()
        
        fresh_token = token.copy()
        fresh_token.update(response.json())
        fresh_token["expires_at"] = int(time.time()) + fresh_token["expires_in"]
        
        # Save token
        with open(TOKEN_FILE, "w") as f:
            json.dump(fresh_token, f, indent=2)
        
        return fresh_token
        
    except Exception as e:
        logger.error(f"Failed to refresh token: {e}")
        return None


def load_token_legacy() -> Optional[Dict[str, Any]]:
    """Legacy token loading for backward compatibility"""
    try:
        if not os.path.exists(TOKEN_FILE):
            return None
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load token: {e}")
        return None
