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
      "button.btoddb_ha_music_pause_music": { state: "unknown", attributes: {} },
      "button.btoddb_ha_music_resume_music": { state: "unknown", attributes: {} },
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
      "section btn-row pause-row",
      "section like-section hidden",
    ]);
  });

  it("shows the now-playing artist and title", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);
    expect(root.querySelector(".artist-value")?.textContent).toBe("Neko Case");
    expect(root.querySelector(".title-value")?.textContent).toBe("Hold On, Hold On");
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

  it("grays Play while a track is playing and enables it when nothing is", () => {
    const playing = makeCard(makeHass());
    expect(shadow(playing).querySelector<HTMLButtonElement>(".play-btn")!.disabled).toBe(true);

    const idle = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
      })
    );
    expect(shadow(idle).querySelector<HTMLButtonElement>(".play-btn")!.disabled).toBe(false);
  });

  it("grays Skip, Stop, and Find Song when nothing is playing", () => {
    const card = makeCard(
      makeHass({
        "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
      })
    );
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".find-btn")!.disabled).toBe(true);
  });

  it("enables Skip, Stop, and Find Song while a track is playing", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".skip-btn")!.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".find-btn")!.disabled).toBe(false);
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

    expect(root.querySelector<HTMLButtonElement>(".find-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".history-like-btn")!.disabled).toBe(false);
  });

  it("disables transport buttons whose backing button entity is unavailable", () => {
    const hass = makeHass({
      "button.btoddb_music_play_music": { state: "unavailable", attributes: {} },
    });
    delete hass.states["button.btoddb_ha_music_skip_song"];
    const card = makeCard(hass);
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".play-btn")!.disabled).toBe(true);
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

  it("pause and resume buttons call the integration services", async () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const root = shadow(card);

    root.querySelector<HTMLButtonElement>(".pause-btn")!.click();
    await flush();
    root.querySelector<HTMLButtonElement>(".resume-btn")!.click();
    await flush();

    expect(hass.calls.map((c) => `${c.domain}.${c.service}`)).toEqual([
      "btoddb_ha_music.pause_music",
      "btoddb_ha_music.resume_music",
    ]);
  });

  it("disables pause/resume when their backing button entities are unavailable", () => {
    // The integration marks these unavailable while a radio station (or
    // nothing) is playing — the card just mirrors that.
    const hass = makeHass({
      "button.btoddb_ha_music_pause_music": { state: "unavailable", attributes: {} },
      "button.btoddb_ha_music_resume_music": { state: "unavailable", attributes: {} },
    });
    const card = makeCard(hass);
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".pause-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".resume-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".stop-btn")!.disabled).toBe(false);
  });

  it("disables pause/resume when nothing is playing, even with available buttons", () => {
    const hass = makeHass({
      "sensor.btoddb_ha_music_now_playing": { state: "unknown", attributes: {} },
    });
    const card = makeCard(hass);
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".pause-btn")!.disabled).toBe(true);
    expect(root.querySelector<HTMLButtonElement>(".resume-btn")!.disabled).toBe(true);
  });

  it("enables pause/resume while a playlist is playing", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);

    expect(root.querySelector<HTMLButtonElement>(".pause-btn")!.disabled).toBe(false);
    expect(root.querySelector<HTMLButtonElement>(".resume-btn")!.disabled).toBe(false);
  });

  it("find song calls find_like_matches and shows candidates with like/cancel", async () => {
    const hass = makeHass();
    const card = makeCard(hass);
    const root = shadow(card);

    root.querySelector<HTMLButtonElement>(".find-btn")!.click();
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

  it("renders a collapsed History section that the chevron expands and hides", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);

    const toggle = root.querySelector<HTMLButtonElement>(".history-toggle")!;
    const list = root.querySelector<HTMLElement>(".history-list")!;
    expect(toggle.querySelector(".history-label")?.textContent).toBe("History");
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(list.classList.contains("hidden")).toBe(true);

    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(list.classList.contains("hidden")).toBe(false);

    toggle.click();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(list.classList.contains("hidden")).toBe(true);
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

    const entries = Array.from(root.querySelectorAll(".history-entry"));
    expect(entries.map((li) => li.querySelector(".history-artist")?.textContent)).toEqual([
      "Artist B",
      "Artist A",
    ]);
    expect(entries.map((li) => li.querySelector(".history-song")?.textContent)).toEqual([
      "Song B",
      "Song A",
    ]);
    expect(root.querySelector(".history-empty")).toBeNull();
  });

  it("shows an empty-history row when nothing has played yet", () => {
    const card = makeCard(makeHass());
    const root = shadow(card);
    root.querySelector<HTMLButtonElement>(".history-toggle")!.click();
    expect(root.querySelectorAll(".history-entry").length).toBe(0);
    expect(root.querySelector(".history-empty")?.textContent).toBe("No songs played yet");
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

    root.querySelector<HTMLButtonElement>(".history-like-btn")!.click();
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

    expect(root.querySelector<HTMLButtonElement>(".history-like-btn")!.disabled).toBe(true);
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
});
