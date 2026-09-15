---
name: spotify-control
description: Control Spotify playback (play/skip/pause/volume) via the Web API, and cast pages to Google Home.
---

# spotify-control

`pip install spotipy`. Make an app at developer.spotify.com/dashboard for
client id/secret. Scopes: `user-modify-playback-state user-read-playback-state
user-read-currently-playing`.

```python
import spotipy
from spotipy.oauth2 import SpotifyOAuth
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
    client_id="ID", client_secret="SECRET",
    redirect_uri="http://localhost:8888/callback",
    scope="user-modify-playback-state user-read-playback-state user-read-currently-playing"))

sp.start_playback()                 # resume
sp.start_playback(context_uri="spotify:playlist:37i9dQZF1DXcBWIGoYBM5M")  # play a playlist
sp.next_track(); sp.previous_track(); sp.pause_playback()
sp.volume(60)
now = sp.currently_playing(); print(now["item"]["name"])
```

First run opens a browser to authorize once; the token is cached after that.

## Cast a page (e.g. lyrics) to Google Home / Nest display
`pip install pychromecast`
```python
import pychromecast
casts,_ = pychromecast.get_chromecasts()
cc = next(c for c in casts if c.name=="Living Room"); cc.wait()
cc.media_controller.play_media("http://localhost:5000/lyrics", "text/html")
cc.media_controller.block_until_active()
```
Lyrics aren't in Spotify's API — pull from a third-party lyrics API by track name
and render a big auto-scrolling HTML page to cast.
