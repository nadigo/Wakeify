# Alarm Playback Module

A robust Python system for waking Spotify Connect speakers (especially Devialet Phantom) and starting playback at alarm time, with automatic failover to AirPlay if the primary device fails.

## Features

- **mDNS Discovery**: Automatically discover Spotify Connect devices on your network
- **Zeroconf Protocol**: Wake sleeping devices using getInfo and addUser endpoints
- **Spotify Web API Integration**: Control playback, volume, and device selection
- **Automatic Failover**: Falls back to spotifyd or AirPlay if primary device fails
- **Circuit Breaker**: Prevents repeated failures on problematic devices
- **Structured Logging**: JSON logging with detailed metrics and timing
- **CLI Testing Tools**: Comprehensive command-line interface for testing

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/nadigo/Wakeify
cd Wakeify/playback

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### 2. Configuration

Copy the environment template from the project root and configure your Spotify credentials:

```bash
cp ../.env.example ../.env
cd ..
```

Edit `.env` with your Spotify app credentials:

```env
# Spotify API Credentials (required)
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REFRESH_TOKEN=your_refresh_token_here

# Default playlist for alarms
ALARM_CONTEXT_URI=spotify:playlist:your_default_playlist_id

# AirPlay fallback targets
AIRPLAY_TARGET_IPS=192.168.1.100,192.168.1.101

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### 3. Spotify App Setup

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set redirect URI to `https://your-container-ip/callback` (e.g., `https://192.168.1.11/callback`)
4. Note down your Client ID and Client Secret
5. Generate a refresh token using the authorization flow

### 4. Testing

Test your setup with the CLI:

```bash
# Discover devices on your network
alarm-cli discover-all

# Test a specific device
alarm-cli discover "Phantom"

# Test device wake-up
alarm-cli touch "Phantom"

# Test authentication
alarm-cli adduser "Phantom" --mode blob_clientKey

# List Spotify devices
alarm-cli list-devices

# Test immediate playback
alarm-cli play "Phantom" --context "spotify:playlist:your_playlist_id"

# Run full alarm simulation
alarm-cli alarm "Phantom"
```

## Usage

### Basic Python Usage

```python
from alarm_playback import AlarmPlaybackEngine, AlarmPlaybackConfig

# Load configuration from environment
config = AlarmPlaybackConfig.from_env()

# Add your target devices
config.targets = [
    DeviceProfile(
        name="Phantom",
        volume_preset=35,
        auth_mode_for_adduser="blob_clientKey",
        capabilities=["connect", "airplay"],
        fallback_policy="both"
    )
]

# Create engine and run alarm
engine = AlarmPlaybackEngine(config)
metrics = engine.play_alarm("Phantom")

print(f"Alarm completed via: {metrics.branch}")
print(f"Total duration: {metrics.total_duration_ms}ms")
```

### Configuration Options

#### Device Profiles

```python
DeviceProfile(
    name="Phantom",                    # Friendly name for device matching
    ip="192.168.1.100",               # Static IP (optional)
    cpath="/spotify",                 # Zeroconf CPath (optional)
    port=8080,                        # Zeroconf port (optional)
    volume_preset=35,                 # Volume level 0-100
    auth_mode_for_adduser="blob_clientKey",  # Authentication mode
    capabilities=["connect", "airplay"],     # Device capabilities
    fallback_policy="both",           # Fallback behavior
    max_wake_wait_s=22               # Max time to wait for device wake
)
```

#### Timing Configuration

```python
Timings(
    prewarm_s=60,                     # Pre-warm time (T-60s)
    poll_fast_period_s=5.0,           # Fast polling period
    total_poll_deadline_s=20,         # Total polling deadline
    debounce_after_seen_s=0.6,        # Debounce after device seen
    retry_404_delay_s=0.7,            # Delay before 404 retry
    failover_fire_after_s=2.0         # Failover timeout (T+2s)
)
```

## Architecture

### Timeline Flow

1. **T-60s Pre-warm**: mDNS discovery to find device
2. **T-30s Activate**: getInfo check to wake device
3. **T-10s Poll**: Fast polling for device to appear in Spotify API
4. **T-0 Fire**: Transfer playback, set volume, start playing
5. **T+2s Failover**: If primary fails, activate fallback mechanisms

### Fallback Mechanisms

1. **Spotifyd Fallback**: Use always-online spotifyd device
2. **AirPlay Fallback**: Stream to AirPlay targets via raop_play
3. **Circuit Breaker**: Skip primary path for repeatedly failing devices

### State Machine

```
UNKNOWN → DISCOVERED → LOCAL_AWAKE → LOGGED_IN → CLOUD_VISIBLE → STAGED → PLAYING
                ↓
        DEEP_SLEEP_SUSPECTED → FALLBACK_ACTIVE
```

## Dependencies

### Required External Services

- **librespot/spotifyd**: Always-online Spotify Connect device for fallback
- **raop_play**: AirPlay client for audio streaming
- **sox**: Audio processing for test tones (optional)

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt-get install sox

# macOS
brew install sox

# Install raop_play (varies by distribution)
# See: https://github.com/philippe44/raop_play
```

## CLI Commands

### Device Discovery
- `alarm-cli discover <name>`: Discover specific device
- `alarm-cli discover-all`: Discover all devices
- `alarm-cli touch <name>`: Test device wake-up
- `alarm-cli health <name>`: Check device health

### Authentication
- `alarm-cli adduser <name> --mode [blob|token]`: Test authentication

### Playback Testing
- `alarm-cli list-devices`: Show Spotify devices
- `alarm-cli play <name> --context <uri>`: Test immediate playback
- `alarm-cli alarm <name>`: Run full alarm simulation

### System
- `alarm-cli status`: Show configuration and system status

## Logging

The system uses structured JSON logging with detailed metrics:

```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "level": "INFO",
  "message": "Completed phase: play (success: true)",
  "device_name": "Phantom",
  "phase": "play",
  "duration_ms": 1234,
  "success": true
}
```

## Troubleshooting

### Common Issues

1. **Device not discovered**: Check mDNS/Bonjour is working, device is on same network
2. **Authentication fails**: Verify Spotify app credentials and device pairing
3. **Playback fails**: Check device appears in Spotify Web API devices
4. **Fallback fails**: Ensure spotifyd is running and raop_play is installed

### Debug Mode

Run with debug logging for detailed information:

```bash
alarm-cli --log-level DEBUG alarm "Phantom"
```

### Device-Specific Notes

#### Devialet Phantom
- Requires app pairing for addUser authentication
- May need specific timing adjustments for wake-up
- AirPlay fallback works well as backup

#### Other Spotify Connect Devices
- Some devices may not support addUser (skip authentication)
- Volume control may vary by device type
- Check device capabilities in configuration

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest

# Run tests
pytest tests/
```

### Adding New Device Types

1. Create device profile in configuration
2. Adjust timing parameters if needed
3. Test with CLI commands
4. Add to device registry

### Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

## License

MIT License - see LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review logs with debug mode
3. Test individual components with CLI
4. Open an issue with detailed logs

