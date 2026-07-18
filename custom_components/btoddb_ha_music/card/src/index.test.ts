// @vitest-environment happy-dom
import { beforeAll, describe, expect, it } from "vitest";

const CARD_TYPE = "btoddb-ha-music-like-card";

interface ServiceCall {
  domain: string;
  service: string;
  data?: Record<string, unknown>;
}

interface FakeHass {
  states: Record<string, { state: string; attributes: Record<string, unknown> }>;
  calls: ServiceCall[];
  callService(domain: string, service: string, data?: Record<string, unknown>): Promise<void>;
}

// Mixed entity-id slugs on purpose: the combined-media entities were
// registered under a different device-name slug (btoddb_music_*) than the
// original entities (btoddb_ha_music_*), and the card must resolve both.
function makeHass(overrides: FakeHass["states"] = {}): FakeHass {
  const calls: ServiceCall[] = [];
  return {
    calls,
    states: {
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: { artist: "Neko Case", title: "Hold On, Hold On" },
      },
      "select.btoddb_music_music": {
        state: "KEXP",
        attributes: { options: ["KEXP", "Dinner Playlist"] },
      },
      "select.btoddb_music_music_filter": {
        state: "All",
        attributes: { options: ["All", "Playlists", "Radio stations"] },
      },
      "select.btoddb_ha_music_speaker_group": {
        state: "Kitchen",
        attributes: { options: ["Kitchen", "All Speakers"] },
      },
      "select.btoddb_ha_music_like_candidate": {
        state: "unavailable",
        attributes: {},
      },
      "button.btoddb_music_play_music": { state: "unknown", attributes: {} },
      "button.btoddb_ha_music_stop_music": { state: "unknown", attributes: {} },
      "button.btoddb_ha_music_skip_song": { state: "unknown", attributes: {} },
      // Default fixture: a playlist is playing and un-paused, so only
      // pause_music is available (resume applies only while paused — PM-8).
      "button.btoddb_ha_music_pause_music": { state: "unknown", attributes: {} },
      "button.btoddb_ha_music_resume_music": { state: "unavailable", attributes: {} },
      "button.btoddb_ha_music_find_like_matches": { state: "unknown", attributes: {} },
      "button.btoddb_ha_music_confirm_like": { state: "unavailable", attributes: {} },
      "button.btoddb_ha_music_cancel_like": { state: "unavailable", attributes: {} },
      ...overrides,
    },
    callService(domain, service, data) {
      calls.push({ domain, service, data });
      return Promise.resolve();
    },
  };
}

interface CardElement extends HTMLElement {
  setConfig(config: Record<string, unknown>): void;
  hass: FakeHass;
}

function makeCard(hass: FakeHass): CardElement {
  const card = document.createElement(CARD_TYPE) as CardElement;
  card.setConfig({ entity_prefix: "btoddb_ha_music" });
  card.hass = hass;
  return card;
}

function shadow(card: CardElement): ShadowRoot {
  const root = card.shadowRoot;
  if (!root) throw new Error("card did not render a shadow root");
  return root;
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

beforeAll(async () => {
  await import("./index");
});

describe(CARD_TYPE, () => {
  it("registers the custom element", () => {
    expect(customElements.get(CARD_TYPE)).toBeDefined();
  });

  it("renders header and sections in the issue-specified order", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);

    expect(root.querySelector("ha-card")?.getAttribute("header")).toBe("Play Something ...");

    const sections = Array.from(root.querySelectorAll(".card-content > .section")).map(
      (el) => el.className
    );
    expect(sections).toEqual([
      "section now-playing-section",
      "section media-section",
      "section speakers-section",
      "section btn-row play-row",
      "section btn-row stop-row",
      "section like-section hidden",
    ]);
  });

  it("shows the now-playing track as a history-style entry", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);
    const entry = root.querySelector(".now-playing-list .history-entry")!;
    expect(entry.classList.contains("now-playing-entry")).toBe(true);
    expect(entry.querySelector(".history-artist")?.textContent).toBe("Neko Case");
    expect(entry.querySelector(".history-song")?.textContent).toBe("Hold On, Hold On");
  });

  it("empties Now Playing when nothing is playing", () => {
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
      })
    );
    const root = shadow(card);
    expect(root.querySelector(".now-playing-list .history-entry")).toBeNull();
    expect(root.querySelector(".now-playing-list .history-empty")?.textContent).toBe(
      "Nothing playing"
    );
  });

  it("treats retained metadata on an idle player as nothing playing in Now Playing", () => {
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "Neko Case - Hold On, Hold On",
          attributes: {
            artist: "Neko Case",
            title: "Hold On, Hold On",
            playback_active: false,
          },
        },
      })
    );
    const root = shadow(card);
    expect(root.querySelector(".now-playing-list .history-entry")).toBeNull();
  });

  it("liking the now-playing entry calls find_like_matches for the current track", async () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const root = shadow(card);

    root.querySelector<HTMLButtonElement>(".now-playing-list .history-like-btn")!.click();
    await flush();

    expect(hass.calls).toEqual([
      { domain: "btoddb_ha_music", service: "find_like_matches", data: undefined },
    ]);
  });

  it("excludes the currently playing track from the expanded history list", () => {
    // The integration records a track into history the moment it starts
    // (issue #40), so the head entry duplicates Now Playing while playing.
    const history = [
      { artist: "Neko Case", title: "Hold On, Hold On", album: null, played_at: "2026-07-13T03:00:00" },
      { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
    ];
    const playing = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "playing",
          attributes: { artist: "Neko Case", title: "Hold On, Hold On", history },
        },
      })
    );
    const playingRoot = shadow(playing);
    playingRoot.querySelector<HTMLButtonElement>(".history-toggle")!.click();
    expect(
      Array.from(playingRoot.querySelectorAll(".history-list .history-artist")).map(
        (el) => el.textContent
      )
    ).toEqual(["Artist A"]);

    // Once playback stops, the full history shows.
    const stopped = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "unknown",
          attributes: { playback_active: false, history },
        },
      })
    );
    const stoppedRoot = shadow(stopped);
    stoppedRoot.querySelector<HTMLButtonElement>(".history-toggle")!.click();
    expect(
      Array.from(stoppedRoot.querySelectorAll(".history-list .history-artist")).map(
        (el) => el.textContent
      )
    ).toEqual(["Neko Case", "Artist A"]);
  });

  it("populates the music dropdown from the fallback-resolved media select", () => {
    const card = makeCard(makeHass());
    const dropdown = shadow(card).querySelector<HTMLSelectElement>(".media-select");
    expect(Array.from(dropdown!.options).map((o) => o.value)).toEqual([
      "KEXP",
      "Dinner Playlist",
    ]);
    expect(dropdown!.value).toBe("KEXP");
  });

  it("does not resolve the media dropdown from the music filter select", () => {
    const hass = makeHass();
    delete hass.states["select.btoddb_music_music"];
    const card = makeCard(hass);
    const dropdown = shadow(card).querySelector<HTMLSelectElement>(".media-select");
    expect(dropdown!.options.length).toBe(0);
    expect(dropdown!.disabled).toBe(true);
  });

  it("selecting music calls select.select_option on the resolved entity id", () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const dropdown = shadow(card).querySelector<HTMLSelectElement>(".media-select")!;
    dropdown.value = "Dinner Playlist";
    dropdown.dispatchEvent(new Event("change"));
    expect(hass.calls).toEqual([
      {
        domain: "select",
        service: "select_option",
        data: { entity_id: "select.btoddb_music_music", option: "Dinner Playlist" },
      },
    ]);
  });

  it("selecting speakers calls select.select_option on the speaker group", () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const dropdown = shadow(card).querySelector<HTMLSelectElement>(".speakers-select")!;
    dropdown.value = "All Speakers";
    dropdown.dispatchEvent(new Event("change"));
    expect(hass.calls).toEqual([
      {
        domain: "select",
        service: "select_option",
        data: {
          entity_id: "select.btoddb_ha_music_speaker_group",
          option: "All Speakers",
        },
      },
    ]);
  });

  it("play, skip, and stop buttons call the integration services", async () => {
    // Play is only clickable while nothing is playing; skip/stop only while
    // something is (issue #36), so the sensor flips between the two clicks.
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
    });
    const card = makeCard(hass);
    const root = shadow(card);

    root.querySelector<HTMLButtonElement>(".play-btn")!.click();
    await flush();

    hass.states["sensor.btoddb_ha_music_now_playing"] = {
      state: "playing",
      attributes: { artist: "Neko Case", title: "Hold On, Hold On" },
    };
    card.hass = hass;

    root.querySelector<HTMLButtonElement>(".skip-btn")!.click();
    await flush();
    root.querySelector<HTMLButtonElement>(".stop-btn")!.click();
    await flush();

    expect(hass.calls.map((c) => `${c.domain}.${c.service}`)).toEqual([
      "btoddb_ha_music.play_music",
      "btoddb_ha_music.next_track",
      "btoddb_ha_music.stop_music",
    ]);
  });

  it("shows an enabled Play button when nothing is playing", () => {
    const idle = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
      })
    );
    const btn = shadow(idle).querySelector<HTMLButtonElement>(".play-btn")!;
    expect(btn.textContent).toBe("Play");
    expect(btn.disabled).toBe(false);
  });

  it("shows a disabled Play button while a radio station plays", () => {
    // Radio cannot be paused or resumed (PM-7), so both backing buttons are
    // unavailable and the transport button falls back to Play — grayed
    // because something is already playing (issue #39, CARD-3).
    const card = makeCard(
      makeHass({
        "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
        "button.btoddb_ha_music_resume_music": { state: "unavailable", attributes: {} },
      })
    );
    const btn = shadow(card).querySelector<HTMLButtonElement>(".play-btn")!;
    expect(btn.textContent).toBe("Play");
    expect(btn.disabled).toBe(true);
  });

  it("morphs the Play button into Pause while a playlist plays un-paused", () => {
    const card = makeCard(makeHass());
    const btn = shadow(card).querySelector<HTMLButtonElement>(".play-btn")!;
    expect(btn.textContent).toBe("Pause");
    expect(btn.disabled).toBe(false);
  });

  it("morphs the Play button into Resume while a playlist is paused", () => {
    const card = makeCard(
      makeHass({
        "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
        "button.btoddb_ha_music_resume_music": { state: "unknown", attributes: {} },
      })
    );
    const btn = shadow(card).querySelector<HTMLButtonElement>(".play-btn")!;
    expect(btn.textContent).toBe("Resume");
    expect(btn.disabled).toBe(false);
  });

  it("clicking the Play button calls the service for its current mode", async () => {
    // Nothing playing → Play; playlist un-paused → Pause; paused → Resume.
    const idleHass = makeHass({
      "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
    });
    shadow(makeCard(idleHass)).querySelector<HTMLButtonElement>(".play-btn")!.click();
    await flush();
    expect(idleHass.calls.map((c) => c.service)).toEqual(["play_music"]);

    const playingHass = makeHass();
    shadow(makeCard(playingHass)).querySelector<HTMLButtonElement>(".play-btn")!.click();
    await flush();
    expect(playingHass.calls.map((c) => c.service)).toEqual(["pause_music"]);

    const pausedHass = makeHass({
      "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
      "button.btoddb_ha_music_resume_music": { state: "unknown", attributes: {} },
    });
    shadow(makeCard(pausedHass)).querySelector<HTMLButtonElement>(".play-btn")!.click();
    await flush();
    expect(pausedHass.calls.map((c) => c.service)).toEqual(["resume_music"]);
  });

  it("grays Skip and Stop when nothing is playing", () => {
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
      })
    );
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(true);
  });

  it("enables Skip and Stop while a track is playing", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
  });

  it("does not render a Find Song button (the ♥ hearts drive search now)", () => {
    const card = makeCard(makeHass());
    expect(shadow(card).querySelector(".find-btn")).toBeNull();
  });

  it("treats retained metadata on an idle player as nothing playing", () => {
    // After a queue finishes, an idle player can keep its last artist/title,
    // so the sensor state still names a track. The playback_active attribute
    // carries the real signal (PR #38 review).
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "Neko Case - Hold On, Hold On",
          attributes: {
            artist: "Neko Case",
            title: "Hold On, Hold On",
            playback_active: false,
          },
        },
      })
    );
    const root = shadow(card);

    const play = root.querySelector<HTMLButtonElement>(".play-btn")!;
    expect(play.textContent).toBe("Play");
    expect(play.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(true);
  });

  it("honors playback_active=true even when the sensor state carries no track", () => {
    // Music Assistant reports paused players as idle; the integration counts
    // its own pause as active so Resume stays applicable. The transport button
    // morphs into an enabled Resume even though the sensor state names no track.
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "unknown",
          attributes: { playback_active: true },
        },
        "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
        "button.btoddb_ha_music_resume_music": { state: "unknown", attributes: {} },
      })
    );
    const root = shadow(card);

    const play = root.querySelector<HTMLButtonElement>(".play-btn")!;
    expect(play.textContent).toBe("Resume");
    expect(play.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
  });

  it("keeps history like buttons usable when nothing is playing", () => {
    // History entries carry their own artist/title, so liking a song that
    // already stopped playing must keep working (issue #27).
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": {
          state: "unknown",
          attributes: {
            history: [
              { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
            ],
          },
        },
      })
    );
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();

    expect(root.querySelector<HTMLButtonElement>(".history-list .history-like-btn")!.disabled).toBe(false);
  });

  it("disables the Play button when its backing button entity is unavailable", () => {
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
        "button.btoddb_music_play_music": { state: "unavailable", attributes: {} },
      })
    );
    const btn = shadow(card).querySelector<HTMLButtonElement>(".play-btn")!;
    expect(btn.textContent).toBe("Play");
    expect(btn.disabled).toBe(true);
  });

  it("disables skip whose backing button entity is unavailable but leaves stop usable", () => {
    const hass = makeHass();
    delete hass.states["button.btoddb_ha_music_skip_song"];
    const card = makeCard(hass);
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
  });

  it("falls back to the next_track button entity for skip availability", () => {
    const hass = makeHass({
      "button.btoddb_ha_music_next_track": { state: "unknown", attributes: {} },
    });
    delete hass.states["button.btoddb_ha_music_skip_song"];
    const card = makeCard(hass);
    expect(shadow(card).querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(false);
  });

  it("falls back to Play (disabled) when a paused-state backing entity is unavailable but something plays", () => {
    // Guards against the transport button offering Pause/Resume for radio:
    // both backing buttons unavailable while playing → Play, grayed.
    const card = makeCard(
      makeHass({
        "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
        "button.btoddb_ha_music_resume_music": { state: "unavailable", attributes: {} },
      })
    );
    const root = shadow(card);
    const play = root.querySelector<HTMLButtonElement>(".play-btn")!;
    expect(play.textContent).toBe("Play");
    expect(play.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
  });

  it("the now-playing ♥ calls find_like_matches and shows candidates with like/cancel", async () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const root = shadow(card);

    root.querySelector<HTMLButtonElement>(".now-playing-list .history-like-btn")!.click();
    await flush();
    expect(hass.calls.map((c) => c.service)).toEqual(["find_like_matches"]);

    hass.states["select.btoddb_ha_music_like_candidate"] = {
      state: "Neko Case — Hold On, Hold On",
      attributes: {
        candidates: [
          {
            label: "Neko Case — Hold On, Hold On",
            artist: "Neko Case",
            title: "Hold On, Hold On",
            album: "Fox Confessor Brings the Flood",
          },
        ],
      },
    };
    hass.states["button.btoddb_ha_music_confirm_like"] = { state: "unknown", attributes: {} };
    hass.states["button.btoddb_ha_music_cancel_like"] = { state: "unknown", attributes: {} };
    card.hass = hass;

    const likeSection = root.querySelector<HTMLElement>(".like-section")!;
    expect(likeSection.classList.contains("hidden")).toBe(false);
    expect(root.querySelectorAll(".candidate-option").length).toBe(1);
    expect(root.querySelector(".candidate-album")?.textContent).toBe(
      "Fox Confessor Brings the Flood"
    );

    root.querySelector<HTMLButtonElement>(".like-btn")!.click();
    await flush();
    root.querySelector<HTMLButtonElement>(".cancel-btn")!.click();
    await flush();
    expect(hass.calls.map((c) => c.service)).toEqual([
      "find_like_matches",
      "confirm_like",
      "cancel_like",
    ]);
  });

  it("always shows the last 2 history entries and uses the chevron to expand the rest", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "unknown",
        attributes: {
          playback_active: false,
          history: [
            { artist: "Artist C", title: "Song C", album: null, played_at: "2026-07-13T03:00:00" },
            { artist: "Artist B", title: "Song B", album: null, played_at: "2026-07-13T02:00:00" },
            { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
          ],
        },
      },
    });
    const card = makeCard(hass);
    const root = shadow(card);

    const toggle = root.querySelector<HTMLButtonElement>(".history-toggle")!;
    expect(toggle.querySelector(".history-label")?.textContent).toBe("History");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(toggle.classList.contains("hidden")).toBe(false);

    const entries = () => Array.from(root.querySelectorAll<HTMLLIElement>(".history-list .history-entry"));
    const visibleArtists = () =>
      entries()
        .filter((li) => !li.classList.contains("hidden"))
        .map((li) => li.querySelector(".history-artist")?.textContent);

    expect(visibleArtists()).toEqual(["Artist C", "Artist B"]);

    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(visibleArtists()).toEqual(["Artist C", "Artist B", "Artist A"]);

    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(visibleArtists()).toEqual(["Artist C", "Artist B"]);
  });

  it("hides the chevron when there are 2 or fewer history entries", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "unknown",
        attributes: {
          playback_active: false,
          history: [
            { artist: "Artist B", title: "Song B", album: null, played_at: "2026-07-13T02:00:00" },
            { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
          ],
        },
      },
    });
    const card = makeCard(hass);
    const root = shadow(card);
    const toggle = root.querySelector<HTMLButtonElement>(".history-toggle")!;
    expect(toggle.classList.contains("hidden")).toBe(true);
  });

  it("renders history entries newest-first from the now-playing sensor", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          history: [
            { artist: "Artist B", title: "Song B", album: null, played_at: "2026-07-13T02:00:00" },
            { artist: "Artist A", title: "Song A", album: "Album A", played_at: "2026-07-13T01:00:00" },
          ],
        },
      },
    });
    const card = makeCard(hass);
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();

    const entries = Array.from(root.querySelectorAll(".history-list .history-entry"));
    expect(entries.map((li) => li.querySelector(".history-artist")?.textContent)).toEqual([
      "Artist B",
      "Artist A",
    ]);
    expect(entries.map((li) => li.querySelector(".history-song")?.textContent)).toEqual([
      "Song B",
      "Song A",
    ]);
    expect(root.querySelector(".history-list .history-empty")).toBeNull();
  });

  it("renders history hearts from each entry's carried liked state", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          history: [
            { artist: "Artist C", title: "Song C", album: null, played_at: "2026-07-13T03:00:00", liked: "liked" },
            { artist: "Artist B", title: "Song B", album: null, played_at: "2026-07-13T02:00:00", liked: "not_liked" },
            { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00", liked: null },
          ],
        },
      },
    });
    const card = makeCard(hass);
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();

    const hearts = Array.from(
      root.querySelectorAll<HTMLButtonElement>(".history-list .history-like-btn")
    );
    expect(hearts.map((btn) => btn.textContent)).toEqual(["♥", "♡", "♡"]);
    expect(hearts.map((btn) => btn.classList.contains("liked"))).toEqual([true, false, false]);
    expect(hearts.map((btn) => btn.classList.contains("not-liked"))).toEqual([false, true, false]);
    expect(hearts.map((btn) => btn.classList.contains("liked-unknown"))).toEqual([false, false, true]);
  });

  it("shows an empty-history row when nothing has played yet", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);
    expect(root.querySelectorAll(".history-list .history-entry").length).toBe(0);
    expect(root.querySelector(".history-list .history-empty")?.textContent).toBe(
      "This space will fill up as you play songs"
    );
  });

  it("liking a history entry calls find_like_matches with that artist and title", async () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          history: [
            { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
          ],
        },
      },
    });
    const card = makeCard(hass);
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();

    root.querySelector<HTMLButtonElement>(".history-list .history-like-btn")!.click();
    await flush();

    expect(hass.calls).toEqual([
      {
        domain: "btoddb_ha_music",
        service: "find_like_matches",
        data: { artist: "Artist A", title: "Song A" },
      },
    ]);
  });

  it("disables history like buttons when find_like_matches is unavailable", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          history: [
            { artist: "Artist A", title: "Song A", album: null, played_at: "2026-07-13T01:00:00" },
          ],
        },
      },
      "button.btoddb_ha_music_find_like_matches": { state: "unavailable", attributes: {} },
    });
    const card = makeCard(hass);
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();

    expect(root.querySelector<HTMLButtonElement>(".history-list .history-like-btn")!.disabled).toBe(true);
  });

  it("prefers a direct prefix match over the fallback scan", () => {
    const hass = makeHass({
      "select.btoddb_ha_music_music": {
        state: "Direct",
        attributes: { options: ["Direct"] },
      },
    });
    const card = makeCard(hass);
    const dropdown = shadow(card).querySelector<HTMLSelectElement>(".media-select")!;
    dropdown.value = "Direct";
    dropdown.dispatchEvent(new Event("change"));
    expect(hass.calls[0]?.data?.entity_id).toBe("select.btoddb_ha_music_music");
  });

  // issue #43: the now-playing heart reflects Liked Songs membership.
  it("fills the now-playing heart when the track is already liked", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          now_playing_liked: "liked",
        },
      },
    });
    const heart = shadow(makeCard(hass)).querySelector<HTMLButtonElement>(
      ".now-playing-list .history-like-btn"
    )!;
    expect(heart.textContent).toBe("♥");
    expect(heart.classList.contains("liked")).toBe(true);
    expect(heart.getAttribute("aria-label")).toContain("already liked");
  });

  it("outlines the now-playing heart when the track is not liked", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": {
        state: "playing",
        attributes: {
          artist: "Neko Case",
          title: "Hold On, Hold On",
          now_playing_liked: "not_liked",
        },
      },
    });
    const heart = shadow(makeCard(hass)).querySelector<HTMLButtonElement>(
      ".now-playing-list .history-like-btn"
    )!;
    expect(heart.textContent).toBe("♡");
    expect(heart.classList.contains("not-liked")).toBe(true);
  });

  it("shows a muted outline heart when liked state is unknown or absent", () => {
    const heart = shadow(makeCard(makeHass())).querySelector<HTMLButtonElement>(
      ".now-playing-list .history-like-btn"
    )!;
    expect(heart.textContent).toBe("♡");
    expect(heart.classList.contains("liked-unknown")).toBe(true);
  });

  it("marks a candidate that is already liked with a filled heart", () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const root = shadow(card);
    hass.states["select.btoddb_ha_music_like_candidate"] = {
      state: "Neko Case — Hold On, Hold On",
      attributes: {
        candidates: [
          {
            label: "Neko Case — Hold On, Hold On",
            artist: "Neko Case",
            title: "Hold On, Hold On",
            album: "Fox Confessor Brings the Flood",
            liked: true,
          },
          {
            label: "Neko Case — Hold On, Hold On (Live)",
            artist: "Neko Case",
            title: "Hold On, Hold On",
            album: "Live",
            liked: false,
          },
        ],
      },
    };
    card.hass = hass;

    const options = root.querySelectorAll(".candidate-option");
    const firstHeart = options[0].querySelector<HTMLElement>(".candidate-liked")!;
    const secondHeart = options[1].querySelector<HTMLElement>(".candidate-liked")!;
    expect(firstHeart.hidden).toBe(false);
    expect(secondHeart.hidden).toBe(true);
  });
});
