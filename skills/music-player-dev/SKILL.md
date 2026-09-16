---
name: music-player-dev
description: Build a custom music player — web, PyQt, or Electron; local files or Spotify.
---

# music-player-dev

Pick a shell:
- **Web** (fastest): HTML `<audio>` + JS. Playlist, seek, volume, visualizer via
  Web Audio API `AnalyserNode`. Ship as a page or wrap in this app.
- **Python desktop**: PyQt6 `QMediaPlayer`/`QAudioOutput`, or `pygame.mixer` for
  simple playback. File dialog for local library, `mutagen` for tags/album art.
- **Electron**: same web audio, native window, `music-metadata` for tags.

Local library: scan a folder for `.mp3/.flac/.wav`, read tags with mutagen /
music-metadata, store playlist as JSON.

Spotify-backed: control playback with the **spotify-control** skill (spotipy);
you drive play/skip/queue, Spotify streams the audio.

Core features to hit: queue, shuffle/repeat, seek bar, volume, now-playing +
album art, keyboard media keys.
