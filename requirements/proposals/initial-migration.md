# Initial migration from production instance to a custom component

**Status:** in progress
**Touches:** everything

## Goal

Create a custom component that provides the same functionality as the music dashboard I've created found here, http://hass.homelab.lan:8123/btoddb-home/music.

**constrait** Don't change/delete/create anything in production!

## Behavior

FYI, The Home Assistant MCP server might prove very useful.

Create the custom component in [btoddb_ha_music](/workspaces/ha-music/custom_components/btoddb_ha_music/).

1. Play radio station selected from the dropdown on the selected speakers when pressing, Play Radio Station
2. Shuffle play playlist selected from the dropdown on the selected speakers when pressing, Shuffle Play Playlist
3. Stop whatever music is playing when pressing Stop Music button
4. Not on current dashboard, but I would like a way to show "now playing" on a card.  It shows current info on the song playing (Artist, Title), or "unknown" if the player doesn't report it.
5. **suggestion** improve managing speaker, playlist, and radio station lists.  The logic to map selections to actual stations, speakers, playlists is scattered around.

## UI (only if applicable)

None in this iteration

## Out of scope

Don't create any custom lovelace cards this iteration.

## Acceptance criteria

How we'll know it's done — concrete checks (engine test cases, a behavior to
observe in the running app, etc.).

- [ ] I can update my current dashboard to point to the custom component and see essentially the same experience
