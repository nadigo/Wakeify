"""
Device Registry for automatic device discovery and profile management
"""

import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

# Import playback module components
from alarm_playback.discovery import discover_all_connect_devices, mdns_discover_connect
from alarm_playback.config import DeviceProfile
from alarm_playback.zeroconf_client import check_device_health

from alarm_config import AlarmSystemConfig

logger = logging.getLogger(__name__)


@dataclass
class DeviceStatus:
    """Device status information"""
    name: str
    ip: str
    port: int
    cpath: str
    is_online: bool
    last_seen: float
    response_time_ms: Optional[float] = None
    health_error: Optional[str] = None


class DeviceRegistry:
    """Manages device discovery and profile generation"""
    
    def __init__(self, config: AlarmSystemConfig):
        self.config = config
        self.device_status: Dict[str, DeviceStatus] = {}
        self.discovery_cache: Dict[str, Any] = {}
        self.cache_ttl = 300  # 5 minutes
    
    def discover_devices(self, force_refresh: bool = False) -> List[DeviceProfile]:
        """
        Discover devices and generate device profiles
        
        Args:
            force_refresh: Force new discovery even if cache is valid
            
        Returns:
            List of discovered device profiles
        """
        current_time = time.time()
        
        # Check cache validity
        if (not force_refresh and 
            'last_discovery' in self.discovery_cache and 
            current_time - self.discovery_cache['last_discovery'] < self.cache_ttl):
            logger.info("Using cached device discovery results")
            return self.discovery_cache.get('devices', [])
        
        logger.info("Starting device discovery...")
        
        try:
            # Discover all Spotify Connect devices
            discovered_devices = discover_all_connect_devices(timeout_s=3.0)
            logger.info(f"Discovered {len(discovered_devices)} Spotify Connect devices")
            
            # Convert to device profiles
            device_profiles = []
            for device in discovered_devices:
                profile = self._create_device_profile(device)
                if profile:
                    device_profiles.append(profile)
                    logger.info(f"Created profile for {profile.name} at {profile.ip}:{profile.port}")
            
            # Update cache
            self.discovery_cache = {
                'devices': device_profiles,
                'last_discovery': current_time
            }
            
            # Update device status
            self._update_device_status(device_profiles)
            
            logger.info(f"Device discovery completed: {len(device_profiles)} profiles created")
            return device_profiles
            
        except Exception as e:
            logger.error(f"Device discovery failed: {e}")
            return []
    
    def _extract_friendly_name(self, discovery_result) -> Optional[str]:
        """
        Extract friendly device name from discovery result - prioritizes device properties (getInfo)
        Logic: getInfo remoteName > TXT records > cleaned instance name > raw instance name
        """
        try:
            # PRIORITY 1: Get friendly name from device's getInfo response (device properties)
            # This is the most reliable source - device provides its own friendly name
            friendly_name = self._get_friendly_name_from_device_info(discovery_result)
            if friendly_name and len(friendly_name.strip()) > 0:
                # Use device properties name directly as-is (no pattern-based cleaning)
                logger.debug(f"Using friendly name '{friendly_name}' from device properties (getInfo)")
                return friendly_name.strip()
            
            # If getInfo failed or returned no name, continue to fallback options
            logger.debug(f"getInfo did not provide a name for {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port}), trying fallback sources")
            
            # PRIORITY 2: Try to get friendly name from TXT records
            txt_records = discovery_result.txt_records or {}
            friendly_name_fields = ['CN', 'Name', 'DisplayName', 'FriendlyName']
            for field in friendly_name_fields:
                if field in txt_records and txt_records[field]:
                    friendly_name = txt_records[field].strip()
                    if friendly_name and len(friendly_name) > 0:
                        logger.debug(f"Found friendly name '{friendly_name}' from TXT field '{field}'")
                        return friendly_name
            
            # PRIORITY 3: If no friendly name from getInfo or TXT records, clean up the instance name
            # This is a fallback when device properties are unavailable (e.g., Sonos doesn't support getInfo)
            instance_name = discovery_result.instance_name
            if instance_name:
                # Generic cleanup: only remove common technical suffixes (no device-specific patterns)
                cleaned_name = self._clean_technical_name_to_friendly(instance_name)
                
                # If we got a cleaned name that's different, use it
                if cleaned_name and cleaned_name != instance_name:
                    logger.debug(f"Using cleaned instance name '{cleaned_name}' (fallback - getInfo unavailable)")
                    return cleaned_name
                
                # Final fallback: use original instance name as-is
                logger.debug(f"Using original instance name '{instance_name}' for {discovery_result.ip}:{discovery_result.port} (fallback - getInfo unavailable)")
                return instance_name
            
            return None
            
        except Exception as e:
            logger.error(f"Error extracting friendly name: {e}")
            return discovery_result.instance_name
    
    def _get_friendly_name_from_device_info(self, discovery_result) -> Optional[str]:
        """
        Get friendly name from device's getInfo response - robust error handling
        Returns the friendly name directly from device properties (remoteName field) without any cleaning
        """
        try:
            import requests
            import json
            
            # Validate required fields
            if not discovery_result.ip or not discovery_result.port:
                logger.debug(f"Missing IP/port for getInfo: {discovery_result.ip}:{discovery_result.port}")
                return None
            
            # Ensure cpath is valid and properly formatted (generic for all devices)
            # Some devices report cpath="/" or empty, getInfo expects "/spotifyconnect/zeroconf" or similar
            cpath = discovery_result.cpath or "/spotifyconnect/zeroconf"
            # Handle devices that report cpath="/" or empty - use default path
            if cpath == "/" or not cpath or cpath.strip() == "":
                cpath = "/spotifyconnect/zeroconf"
            if not cpath.startswith("/"):
                cpath = "/" + cpath
            # Remove trailing slash to avoid double slashes
            cpath = cpath.rstrip("/")
            # Build URL properly
            url = f"http://{discovery_result.ip}:{discovery_result.port}{cpath}/?action=getInfo"
            logger.debug(f"getInfo URL for {discovery_result.instance_name}: {url}")
            
            try:
                response = requests.get(url, timeout=3.0)  # Increased timeout to 3.0s
            except requests.exceptions.Timeout:
                logger.debug(f"getInfo timeout for {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port}) via URL: {url}")
                return None
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"getInfo connection error for {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port}) via URL: {url}: {e}")
                return None
            except Exception as e:
                logger.debug(f"getInfo request error for {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port}) via URL: {url}: {e}")
                return None
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    # Log full response for debugging (only in debug mode)
                    logger.debug(f"getInfo response for {discovery_result.ip}: {json.dumps(data, indent=2)}")
                except (json.JSONDecodeError, ValueError) as e:
                    logger.debug(f"Invalid JSON response from getInfo: {e}")
                    return None
                
                # PRIORITY: Try to get friendly name from device properties in order of preference
                # Use device properties DIRECTLY - no pattern-based cleaning or modification
                # Priority: remoteName (device's chosen name) > displayName > name > deviceName > modelDisplayName (model name as fallback)
                friendly_name_fields = ['remoteName', 'displayName', 'name', 'deviceName', 'modelDisplayName']
                for field in friendly_name_fields:
                    if field in data and data[field]:
                        friendly_name = str(data[field]).strip()
                        if friendly_name and len(friendly_name) > 0:
                            # Use device property name directly - no pattern-based cleaning
                            field_type = "friendly" if field != 'modelDisplayName' else "model"
                            logger.info(f"getInfo SUCCESS: Using {field_type} name '{friendly_name}' from field '{field}' for device {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port})")
                            return friendly_name
                
                # Log available fields if no name found
                available_fields = [k for k in data.keys() if 'name' in k.lower() or 'display' in k.lower()]
                logger.debug(f"No friendly name fields found in getInfo response for {discovery_result.ip}. Available name-like fields: {available_fields}")
                return None
            
            else:
                logger.debug(f"getInfo returned status {response.status_code} for {discovery_result.instance_name} ({discovery_result.ip}:{discovery_result.port}) via URL: {url} (device may not support getInfo endpoint)")
            
            return None
            
        except Exception as e:
            # All network exceptions (Timeout, ConnectionError, etc.) are already handled in the try block above
            logger.debug(f"Unexpected error getting friendly name from device info for {discovery_result.ip}: {e}")
            return None
    
    def _clean_technical_name_to_friendly(self, technical_name: str) -> Optional[str]:
        """
        Generic cleanup for instance names when device properties are unavailable.
        Only removes common technical suffixes - no device-specific patterns.
        """
        if not technical_name:
            return None
        
        import re
        name = technical_name.strip()
        original_name = name
        
        # Only remove common technical suffixes generically (no device-specific assumptions)
        # Remove Spotify Connect specific suffixes
        cleaned = re.sub(r'_spotify-connect\._tcp\.local\.?$', '', name, flags=re.IGNORECASE)
        cleaned = re.sub(r'\.spotify-connect\._tcp\.local\.?$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'_spotify-connect$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\.spotify-connect$', '', cleaned, flags=re.IGNORECASE)
        
        cleaned = cleaned.strip()
        
        # If cleaning changed the name meaningfully, return it
        if cleaned and len(cleaned) >= 3 and cleaned != original_name:
            return cleaned
        
        # If already looks friendly (has spaces/apostrophes), keep as-is
        if any(c in original_name for c in [' ', "'"]):
            return None
        
        # If no meaningful cleaning, return None to use original
        return None
    
    def _create_device_profile(self, discovery_result) -> Optional[DeviceProfile]:
        """Create device profile from discovery result"""
        try:
            if not discovery_result.is_complete:
                logger.warning(f"Incomplete discovery result: {discovery_result}")
                return None
            
            # Extract device name - try to get friendly name from TXT records first
            device_name = self._extract_friendly_name(discovery_result)
            if not device_name:
                logger.warning("No device name in discovery result")
                return None
            
            # Create device profile with generic settings (no device-specific logic)
            # Store both friendly name and instance name for exact matching
            profile = DeviceProfile(
                name=device_name,  # Friendly name for display
                instance_name=discovery_result.instance_name,  # Instance name for matching
                spotify_device_names=[],  # Will be populated when device appears in Spotify
                ip=discovery_result.ip,
                port=discovery_result.port,
                cpath=discovery_result.cpath or "/",
                volume_preset=self.config.default_volume,
                auth_mode_for_adduser="access_token",  # Unified auth mode for all devices
                max_wake_wait_s=22
            )
            
            return profile
            
        except Exception as e:
            logger.error(f"Failed to create device profile: {e}")
            return None
    
    def _update_device_status(self, device_profiles: List[DeviceProfile]) -> None:
        """Update device status information"""
        current_time = time.time()
        
        for profile in device_profiles:
            # Check device health
            health_info = check_device_health(
                profile.ip, 
                profile.port, 
                profile.cpath, 
                timeout_s=1.0
            )
            
            status = DeviceStatus(
                name=profile.name,
                ip=profile.ip,
                port=profile.port,
                cpath=profile.cpath,
                is_online=health_info['responding'],
                last_seen=current_time,
                response_time_ms=health_info.get('response_time_ms'),
                health_error=health_info.get('error')
            )
            
            self.device_status[profile.name] = status
            
            if status.is_online:
                response_time = f"{status.response_time_ms:.1f}ms" if status.response_time_ms else "N/A"
                logger.info(f"Device {profile.name} is online (response: {response_time})")
            else:
                logger.warning(f"Device {profile.name} is offline: {status.health_error}")
    
    def get_device_status(self, device_name: str) -> Optional[DeviceStatus]:
        """Get status for a specific device"""
        return self.device_status.get(device_name)
    
    def get_online_devices(self) -> List[DeviceStatus]:
        """Get all online devices"""
        return [status for status in self.device_status.values() if status.is_online]
    
    def refresh_device_status(self, device_name: str) -> Optional[DeviceStatus]:
        """Refresh status for a specific device"""
        try:
            # Try to discover the device
            result = mdns_discover_connect(device_name, timeout_s=1.5)
            if not result.is_complete:
                logger.warning(f"Could not discover device {device_name}")
                return None
            
            # Check health
            health_info = check_device_health(
                result.ip, 
                result.port, 
                result.cpath, 
                timeout_s=1.0
            )
            
            # Update status
            status = DeviceStatus(
                name=device_name,
                ip=result.ip,
                port=result.port,
                cpath=result.cpath,
                is_online=health_info['responding'],
                last_seen=time.time(),
                response_time_ms=health_info.get('response_time_ms'),
                health_error=health_info.get('error')
            )
            
            self.device_status[device_name] = status
            return status
            
        except Exception as e:
            logger.error(f"Failed to refresh status for {device_name}: {e}")
            return None
    
    def get_or_create_device_profile(self, device_name: str) -> Optional[DeviceProfile]:
        """Get existing device profile or create new one"""
        # Check if we already have a profile
        for profile in self.config.targets:
            if profile.name == device_name:
                return profile
        
        # Try to discover and create new profile
        logger.info(f"Device {device_name} not found in registry, attempting discovery...")
        result = mdns_discover_connect(device_name, timeout_s=1.5)
        
        if result.is_complete:
            profile = self._create_device_profile(result)
            if profile:
                # Add to config and save
                self.config.add_or_update_device_profile(profile)
                return profile
        
        logger.warning(f"Could not create profile for device {device_name}")
        return None
    
    def get_device_summary(self) -> Dict[str, Any]:
        """Get summary of all devices"""
        online_devices = self.get_online_devices()
        
        return {
            "total_devices": len(self.device_status),
            "online_devices": len(online_devices),
            "offline_devices": len(self.device_status) - len(online_devices),
            "devices": [
                {
                    "name": status.name,
                    "ip": status.ip,
                    "port": status.port,
                    "is_online": status.is_online,
                    "last_seen": status.last_seen,
                    "response_time_ms": status.response_time_ms,
                    "health_error": status.health_error
                }
                for status in self.device_status.values()
            ]
        }
