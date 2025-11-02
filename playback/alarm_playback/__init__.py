"""
Alarm Playback Module

Robustly wake Spotify Connect speakers and start playback at alarm time.
Includes automatic failover to AirPlay if the primary device fails.
"""

__version__ = "2.0.0"
__author__ = "Wakeify"

from .orchestrator import AlarmPlaybackEngine
from .config import AlarmPlaybackConfig
from .models import PhaseMetrics, State

__all__ = [
    "AlarmPlaybackEngine",
    "AlarmPlaybackConfig", 
    "PhaseMetrics",
    "State"
]

