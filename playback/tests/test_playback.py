"""
Basic smoke tests for playback module
"""

import pytest
from unittest.mock import Mock, patch

from alarm_playback.playback import stage_device, start_play
from alarm_playback.models import CloudDevice


class TestPlayback:
    """Test playback functionality"""
    
    def test_cloud_device_from_spotify_dict(self):
        """Test CloudDevice creation from Spotify API response"""
        spotify_device_dict = {
            "id": "test_device_id",
            "name": "Test Device",
            "is_active": True,
            "volume_percent": 50,
            "type": "Speaker",
            "is_private_session": False,
            "is_restricted": False
        }
        
        device = CloudDevice.from_spotify_dict(spotify_device_dict)
        
        assert device.id == "test_device_id"
        assert device.name == "Test Device"
        assert device.is_active is True
        assert device.volume_percent == 50
        assert device.device_type == "Speaker"
        assert device.is_private_session is False
        assert device.is_restricted is False
    
    @patch('alarm_playback.playback.logger')
    def test_stage_device_success(self, mock_logger):
        """Test successful device staging"""
        mock_api = Mock()
        mock_api.put_transfer.return_value = None
        mock_api.put_volume.return_value = None
        
        stage_device(mock_api, "test_device_id", 50)
        
        mock_api.put_transfer.assert_called_once_with(device_id="test_device_id", play=False)
        mock_api.put_volume.assert_called_once_with(device_id="test_device_id", percent=50)
    
    @patch('alarm_playback.playback.logger')
    def test_stage_device_no_volume(self, mock_logger):
        """Test device staging without volume"""
        mock_api = Mock()
        mock_api.put_transfer.return_value = None
        
        stage_device(mock_api, "test_device_id", None)
        
        mock_api.put_transfer.assert_called_once_with(device_id="test_device_id", play=False)
        mock_api.put_volume.assert_not_called()
    
    @patch('alarm_playback.playback.logger')
    def test_start_play_success(self, mock_logger):
        """Test successful playback start"""
        mock_api = Mock()
        mock_api.put_play.return_value = None
        
        start_play(mock_api, "test_device_id", "spotify:playlist:test", retry_404_delay_s=0.1)
        
        mock_api.put_play.assert_called_once_with(
            device_id="test_device_id",
            context_uri="spotify:playlist:test",
            retry_404_delay_s=0.1
        )

