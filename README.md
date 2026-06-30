# Music (Home Assistant custom component)

A custom component to bridge the gap between HA and Music Assistant(MA).  The goal is to have a dashboard with custom lovelace cards that can:
- play radio stations
- play Playlists (MA or Spotify)
- choose a spearker or MA speaker group
- stop the music

## What you get


## Installation

### HACS (recommended)

1. HACS → ⋮ → **Custom repositories** → add this repo's URL, category **Integration**.
2. Install **BToddB HA Music**, then restart Home Assistant.

### Manual

Copy `custom_components/btoddb_ha_music/` into your HA config's `custom_components/` directory
and restart.

### Configure

**Settings → Devices & Services → Add Integration → BToddB HA Music.** Configure
the speaker group, radio station, and playlist mappings as JSON objects. Speaker
groups map names to one `media_player` entity id or a list of `media_player`
entity ids. Radio stations and playlists map names to the media content id that
your media player or Music Assistant instance can play.

Optionally configure a SpotifyPlus media player entity to enable "like", and a
Spotify playlist (id, URI, or `open.spotify.com` URL) to also append liked
tracks to — Music Assistant can't play Spotify's Liked Songs directly, so this
lets MA play them via a regular playlist.

## How it behaves (spec)

The full, ID'd behavior spec lives in [`requirements/spec/.`](requirements/spec/.).

## Roadmap
