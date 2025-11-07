"""
High-level playback control for Spotify Connect devices
"""

import logging
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .spotify_api import SpotifyApiWrapper
    from .models import CloudDevice

logger = logging.getLogger(__name__)


def stage_device(api: 'SpotifyApiWrapper', device_id: str, volume: Optional[int] = None) -> None:
    """
    Transfer playback to device and optionally set volume.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        volume: Optional volume level (0-100)
    """
    logger.debug(f"Staging device {device_id} (volume: {volume})")
    
    try:
        # Transfer playback without starting
        api.put_transfer(device_id=device_id, play=False)
        logger.debug(f"Transferred playback to device {device_id}")
        
        # Set volume if specified (ignore failures for devices that don't support volume control)
        if volume is not None:
            try:
                api.put_volume(device_id=device_id, percent=volume)
                logger.debug(f"Set volume to {volume}% for device {device_id}")
            except Exception as e:
                logger.warning(f"Volume control not supported for device {device_id}: {e}")
                # Continue without volume control - this is not a fatal error
        
        # Small delay to ensure volume is set
        time.sleep(0.2)
        
    except Exception as e:
        logger.error(f"Failed to stage device {device_id}: {e}")
        raise


def start_play(api: 'SpotifyApiWrapper', device_id: str, context_uri: str, retry_404_delay_s: float = 0.7, shuffle: bool = False) -> None:
    """
    Start playback on device with context URI and 404 retry logic.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        context_uri: URI to play (playlist, album, artist)
        retry_404_delay_s: Delay before retrying on 404 error
        shuffle: Whether to enable shuffle mode
    """
    logger.info(f"Starting playback on device {device_id} with context {context_uri}, shuffle={shuffle}")
    
    try:
        play_kwargs = {
            "device_id": device_id,
            "context_uri": context_uri,
            "retry_404_delay_s": retry_404_delay_s,
        }
        if shuffle:
            play_kwargs["shuffle"] = True

        api.put_play(**play_kwargs)
        logger.info(f"Successfully started playback on device {device_id}")
        
    except Exception as e:
        logger.error(f"Failed to start playback on device {device_id}: {e}")
        raise


def prepare_device_for_playback(api: 'SpotifyApiWrapper', device: 'CloudDevice', 
                               volume_preset: Optional[int] = None) -> None:
    """
    Prepare device for playback by transferring and setting volume.
    
    Args:
        api: Spotify API wrapper instance
        device: Target device
        volume_preset: Optional volume level to set
    """
    logger.info(f"Preparing device {device.name} ({device.id}) for playback")
    
    # Use device's current volume if no preset specified
    target_volume = volume_preset if volume_preset is not None else device.volume_percent
    
    try:
        # Stage the device
        stage_device(api, device.id, target_volume)
        
        # Small delay to ensure device is ready
        time.sleep(0.5)
        
        logger.info(f"Device {device.name} prepared for playback")
        
    except Exception as e:
        logger.error(f"Failed to prepare device {device.name}: {e}")
        raise


def verify_device_ready(api: 'SpotifyApiWrapper', device_id: str, timeout_s: float = 5.0) -> bool:
    """
    Verify that device is ready for playback by checking current playback state.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        timeout_s: Maximum time to wait for device to be ready
        
    Returns:
        True if device is ready, False otherwise
    """
    logger.info(f"Verifying device {device_id} is ready for playback")
    
    start_time = time.time()
    
    while time.time() - start_time < timeout_s:
        try:
            playback_info = api.get_current_playback()
            
            if playback_info and playback_info.get('device', {}).get('id') == device_id:
                logger.info(f"Device {device_id} is ready and active")
                return True
            
            time.sleep(0.5)
            
        except Exception as e:
            logger.warning(f"Error checking device readiness: {e}")
            time.sleep(0.5)
    
    logger.warning(f"Device {device_id} not ready after {timeout_s}s")
    return False


def stop_playback(api: 'SpotifyApiWrapper', device_id: str) -> None:
    """
    Stop playback on a specific device.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
    """
    logger.info(f"Stopping playback on device {device_id}")
    
    try:
        api.pause_playback(device_id=device_id)
        logger.info(f"Stopped playback on device {device_id}")
        
    except Exception as e:
        logger.error(f"Failed to stop playback on device {device_id}: {e}")
        raise


def set_device_volume(api: 'SpotifyApiWrapper', device_id: str, volume_percent: int) -> None:
    """
    Set volume for a specific device.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        volume_percent: Volume percentage (0-100)
    """
    logger.info(f"Setting volume to {volume_percent}% for device {device_id}")
    
    try:
        api.put_volume(device_id=device_id, percent=volume_percent)
        logger.info(f"Volume set to {volume_percent}% for device {device_id}")
        
    except Exception as e:
        logger.error(f"Failed to set volume for device {device_id}: {e}")
        raise


def get_device_playback_state(api: 'SpotifyApiWrapper', device_id: str) -> Optional[dict]:
    """
    Get current playback state for a specific device.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        
    Returns:
        Playback state dictionary or None if no active playback
    """
    try:
        playback_info = api.get_current_playback()
        
        if playback_info and playback_info.get('device', {}).get('id') == device_id:
            return playback_info
        
        return None
        
    except Exception as e:
        logger.error(f"Failed to get playback state for device {device_id}: {e}")
        return None


def wait_for_playback_to_start(api: 'SpotifyApiWrapper', device_id: str, 
                              context_uri: str, timeout_s: float = 10.0) -> bool:
    """
    Start playback and wait for it to actually begin.
    
    Args:
        api: Spotify API wrapper instance
        device_id: Target device ID
        context_uri: URI to play
        timeout_s: Maximum time to wait for playback to start
        
    Returns:
        True if playback started successfully, False otherwise
    """
    logger.info(f"Starting playback on device {device_id} and waiting for confirmation")
    
    try:
        # Start playback
        start_play(api, device_id, context_uri)
        
        # Wait for playback to actually start
        start_time = time.time()
        
        while time.time() - start_time < timeout_s:
            playback_info = get_device_playback_state(api, device_id)
            
            if playback_info and playback_info.get('is_playing', False):
                logger.info(f"Playback confirmed started on device {device_id}")
                return True
            
            time.sleep(0.5)
        
        logger.warning(f"Playback did not start on device {device_id} within {timeout_s}s")
        return False
        
    except Exception as e:
        logger.error(f"Failed to start playback on device {device_id}: {e}")
        return False

