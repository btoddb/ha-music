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
2. Install **Reminders**, then restart Home Assistant.

### Manual

Copy `custom_components/btoddb_ha_music/` into your HA config's `custom_components/` directory
and restart.

### Configure

**Settings → Devices & Services → Add Integration → Reminders.** The setup picker
is a dropdown of every **notify service** registered in your HA instance — pick the
one you want due reminders delivered to. You can change it later from the integration's
**Configure** button.

## How it behaves (spec)

The full, ID'd behavior spec lives in [`requirements/spec/.`](requirements/spec/.).

## Roadmap

