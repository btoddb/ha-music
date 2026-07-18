// v0.0.36
const CARD_VERSION = "v0.0.36";
const CARD_TYPE = "btoddb-ha-music-like-card";

console.info(
  `%c BTODDB-HA-MUSIC-LIKE-CARD %c ${CARD_VERSION} `,
  "color: white; background: #00b4d8; font-weight: 700;",
  "color: #00b4d8; background: white; font-weight: 700;"
);

interface HassState {
  state: string;
  attributes: Record<string, unknown>;
}

interface Hass {
  states: Record<string, HassState>;
  callService(domain: string, service: string, data?: Record<string, unknown>): Promise<void>;
}

interface CardConfig {
  entity_prefix?: string;
}

interface LikeCandidate {
  label: string;
  artist: string;
  title: string;
  album: string | null;
  liked?: boolean | null;
}

// Whether the now-playing track (or a candidate) is already in Liked Songs.
// "unknown" means it could not be resolved confidently, so the heart stays
// neutral rather than claiming the song is unliked (issue #43).
type LikedState = "liked" | "not_liked" | "unknown";

interface PlayedTrack {
  artist: string;
  title: string;
  album: string | null;
  played_at: string;
  // Liked Songs state resolved while the track was playing, carried into
  // history so the heart doesn't reset to neutral ("liked"/"not_liked"/null).
  liked?: string | null;
}

// Coerce a liked attribute value (sensor attribute or history entry) to a
// renderable state; anything unrecognized stays a neutral "unknown" heart.
const toLikedState = (value: unknown): LikedState =>
  value === "liked" || value === "not_liked" ? value : "unknown";

interface ResolvedEntity {
  entityId: string;
  state: HassState;
}

// The single transport button (issue #39) doubles as Play, Pause, and
// Resume, morphing its label and action to whichever transport applies.
type TransportMode = "play" | "pause" | "resume";

class BtoddbHaMusicLikeCard extends HTMLElement {
  private _config: CardConfig = {};
  private _hass: Hass | null = null;
  private _rendered = false;
  private _searching = false;
  private _skipping = false;
  private _playing = false;
  private _stopping = false;
  private _pausing = false;
  private _resuming = false;
  private _noMatches = false;
  private _statusMessage = "";
  private _lastPlayingKey = "";
  private _historyExpanded = false;
  private _transportMode: TransportMode = "play";

  static getStubConfig(): CardConfig {
    return { entity_prefix: "btoddb_ha_music" };
  }

  setConfig(config: CardConfig): void {
    this._config = config;
    if (this._hass) this._update();
  }

  set hass(hass: Hass) {
    this._hass = hass;
    if (!this._rendered) {
      this._initialRender();
    } else {
      this._update();
    }
  }

  getCardSize(): number {
    return 6;
  }

  private get _prefix(): string {
    return this._config.entity_prefix ?? "btoddb_ha_music";
  }

  // Entity ids in an existing install can carry different device-name slugs
  // depending on when each entity was first registered (e.g.
  // sensor.btoddb_ha_music_now_playing vs select.btoddb_music_music), so a
  // single configured prefix cannot resolve everything. Try the configured
  // prefix first, then fall back to any entity in the domain with the same
  // suffix, preferring ids that share the prefix's leading token.
  private _entity(domain: string, suffix: string): ResolvedEntity | null {
    if (!this._hass) return null;

    const directId = `${domain}.${this._prefix}_${suffix}`;
    const direct = this._hass.states[directId];
    if (direct) return { entityId: directId, state: direct };

    const token = this._prefix.split("_")[0];
    const matches = Object.keys(this._hass.states)
      .filter((id) => id.startsWith(`${domain}.`) && id.endsWith(`_${suffix}`))
      .sort((a, b) => {
        const aTok = a.startsWith(`${domain}.${token}`) ? 0 : 1;
        const bTok = b.startsWith(`${domain}.${token}`) ? 0 : 1;
        return aTok - bTok || a.localeCompare(b);
      });

    const entityId = matches[0];
    if (!entityId) return null;
    return { entityId, state: this._hass.states[entityId] };
  }

  private _initialRender(): void {
    if (!this._hass) return;

    const shadow = this.attachShadow({ mode: "open" });

    const style = document.createElement("style");
    style.textContent = this._css();

    const card = document.createElement("ha-card");
    card.setAttribute("header", "Play Something ...");

    const content = document.createElement("div");
    content.className = "card-content";

    // --- Now Playing + History ---
    const nowPlaying = document.createElement("div");
    nowPlaying.className = "section now-playing-section";

    // The History title is a static label; the last 2 plays always show, and
    // a small chevron tab hanging off the bottom edge of the box expands it
    // to reveal older entries.
    const historyLabel = this._makeSectionLabel("History");

    const historyList = document.createElement("ul");
    historyList.className = "track-list history-list";

    const historyToggle = document.createElement("button");
    historyToggle.className = "history-toggle";
    historyToggle.setAttribute("aria-expanded", "false");
    historyToggle.setAttribute("aria-label", "Show more history");
    const chevron = document.createElement("span");
    chevron.className = "chevron";
    chevron.setAttribute("aria-hidden", "true");
    historyToggle.append(chevron);
    historyToggle.addEventListener("click", () => {
      this._historyExpanded = !this._historyExpanded;
      this._update();
    });

    const historyWrap = document.createElement("div");
    historyWrap.className = "history-wrap";
    historyWrap.append(historyList, historyToggle);

    // Now Playing renders as a single history-style entry (same outline as
    // the history list) so the currently playing track and the history read
    // as one timeline (issue #40).
    const nowPlayingList = document.createElement("ul");
    nowPlayingList.className = "track-list now-playing-list";

    nowPlaying.append(
      this._makeSectionLabel("Now Playing"),
      nowPlayingList,
      historyLabel,
      historyWrap
    );

    // --- Music source selector ---
    const mediaSection = document.createElement("div");
    mediaSection.className = "section media-section";
    const mediaSelect = this._makeDropdown("media-select");
    mediaSelect.addEventListener("change", () =>
      this._onDropdownChange("select", "music", mediaSelect.value)
    );
    mediaSection.append(this._makeSectionLabel("Music"), mediaSelect);

    // --- Play (doubles as Pause/Resume — issue #39) / Skip ---
    const playRow = document.createElement("div");
    playRow.className = "section btn-row play-row";
    const playBtn = this._makeButton("play-btn", "Play");
    playBtn.addEventListener("click", () => this._onTransport());
    const skipBtn = this._makeButton("skip-btn", "Skip");
    skipBtn.addEventListener("click", () => this._onSkip());
    playRow.append(playBtn, skipBtn);

    // --- Stop ---
    // Find Song was removed (issue #39 follow-up): the ♥ on the Now Playing
    // entry runs the same now-playing search, so a separate button is
    // redundant. The find-status row stays for no-match feedback.
    const stopRow = document.createElement("div");
    stopRow.className = "section btn-row stop-row";
    const stopBtn = this._makeButton("stop-btn", "Stop");
    stopBtn.addEventListener("click", () => this._onStop());
    stopRow.append(stopBtn);

    const findStatus = document.createElement("div");
    findStatus.className = "find-status hidden";
    findStatus.setAttribute("role", "status");

    // --- Like flow (appears after Find Song returns matches) ---
    const likeSection = document.createElement("div");
    likeSection.className = "section like-section hidden";
    const candidateList = document.createElement("ul");
    candidateList.className = "candidate-list";
    candidateList.setAttribute("role", "listbox");
    const likeRow = document.createElement("div");
    likeRow.className = "btn-row like-row";
    const likeBtn = this._makeButton("like-btn", "Like");
    likeBtn.addEventListener("click", () => this._callService("confirm_like"));
    const cancelBtn = this._makeButton("cancel-btn", "Cancel");
    cancelBtn.addEventListener("click", () => this._callService("cancel_like"));
    likeRow.append(likeBtn, cancelBtn);
    likeSection.append(this._makeSectionLabel("Match"), candidateList, likeRow);

    // --- Speakers selector ---
    const speakersSection = document.createElement("div");
    speakersSection.className = "section speakers-section";
    const speakersSelect = this._makeDropdown("speakers-select");
    speakersSelect.addEventListener("change", () =>
      this._onDropdownChange("select", "speaker_group", speakersSelect.value)
    );
    speakersSection.append(this._makeSectionLabel("Speakers"), speakersSelect);

    content.append(
      nowPlaying,
      mediaSection,
      speakersSection,
      playRow,
      stopRow,
      findStatus,
      likeSection
    );

    card.append(content);
    shadow.append(style, card);

    this._rendered = true;
    this._update();
  }

  private _makeSectionLabel(text: string): HTMLElement {
    const label = document.createElement("div");
    label.className = "section-label";
    label.textContent = text;
    return label;
  }

  private _makeDropdown(className: string): HTMLSelectElement {
    const select = document.createElement("select");
    select.className = `dropdown ${className}`;
    return select;
  }

  private _makeButton(className: string, label: string): HTMLButtonElement {
    const btn = document.createElement("button");
    btn.className = `ha-btn ${className}`;
    btn.textContent = label;
    return btn;
  }

  private _update(): void {
    if (!this._rendered || !this._hass || !this.shadowRoot) return;

    const nowPlaying = this._entity("sensor", "now_playing")?.state;

    const playingKey = `${nowPlaying?.attributes?.artist ?? ""}|${nowPlaying?.attributes?.title ?? ""}`;
    if (playingKey !== this._lastPlayingKey) {
      this._lastPlayingKey = playingKey;
      this._noMatches = false;
      this._statusMessage = "";
    }

    // "Is anything playing" signal — see the transport-button comment below
    // for why playback_active is preferred over the sensor state string.
    const playbackActive = nowPlaying?.attributes?.playback_active;
    const nothingPlaying =
      playbackActive === undefined
        ? nowPlaying === undefined ||
          nowPlaying.state === "unknown" ||
          nowPlaying.state === "unavailable"
        : !playbackActive;

    // Now Playing renders as a history-style entry the moment a track starts
    // (issue #40); the integration puts that same track at the head of the
    // history, so the expanded list drops its newest matching entry to avoid
    // showing the current track twice. When nothing is playing the entry
    // empties and the full history shows.
    const known = (value: unknown): value is string =>
      typeof value === "string" && value !== "" && value !== "unknown";
    const artist = nowPlaying?.attributes?.artist;
    const title = nowPlaying?.attributes?.title;
    const currentTrack =
      !nothingPlaying && (known(artist) || known(title))
        ? {
            artist: known(artist) ? artist : "unknown",
            title: known(title) ? title : "unknown",
          }
        : null;
    const nowPlayingLiked = toLikedState(nowPlaying?.attributes?.now_playing_liked);
    this._updateNowPlayingEntry(currentTrack, nowPlayingLiked);

    // History (from the now-playing sensor's history attribute, newest first)
    const history =
      (nowPlaying?.attributes?.history as PlayedTrack[] | undefined) ?? [];
    let visibleHistory = history;
    if (currentTrack) {
      const currentIdx = history.findIndex(
        (t) => t.artist === currentTrack.artist && t.title === currentTrack.title
      );
      if (currentIdx !== -1)
        visibleHistory = history
          .slice(0, currentIdx)
          .concat(history.slice(currentIdx + 1));
    }
    this._updateHistory(visibleHistory);

    // Selectors
    this._updateDropdown(".media-select", this._entity("select", "music"));
    this._updateDropdown(".speakers-select", this._entity("select", "speaker_group"));

    // Transport buttons — availability mirrors the integration's button
    // entities, layered with this card's own in-flight state and the
    // now-playing sensor (issue #36): Play grays while something is playing,
    // and the play-dependent buttons gray when nothing is. The sensor's
    // playback_active attribute carries the "is anything playing" signal —
    // it derives from real player states (with the integration's paused
    // players counting as active), not from the sensor's state string, which
    // is built from media metadata an idle player can retain after its queue
    // finishes. Older integrations without the attribute fall back to the
    // state string. (Computed above, before the Now Playing entry.)
    this._updateTransportButton(nothingPlaying);
    this._updateActionButton(
      ".skip-btn",
      ["skip_song", "next_track"],
      this._skipping,
      "Skip",
      "Skipping…",
      nothingPlaying
    );
    this._updateActionButton(
      ".stop-btn",
      ["stop_music"],
      this._stopping,
      "Stop",
      "Stop",
      nothingPlaying
    );

    // Like candidates
    const likeCandidate = this._entity("select", "like_candidate")?.state;
    const currentOption = likeCandidate?.state;

    const structuredCandidates =
      (likeCandidate?.attributes?.candidates as LikeCandidate[] | undefined) ?? [];
    const fallbackOptions =
      (likeCandidate?.attributes?.options as string[] | undefined) ?? [];

    const candidates: LikeCandidate[] =
      structuredCandidates.length > 0
        ? structuredCandidates
        : fallbackOptions.map((opt) => ({ label: opt, artist: opt, title: "", album: null }));

    const hasCandidates = candidates.length > 0;

    const likeSection = this.shadowRoot.querySelector<HTMLElement>(".like-section");
    if (likeSection) likeSection.classList.toggle("hidden", !hasCandidates);

    const candidateList = this.shadowRoot.querySelector<HTMLUListElement>(".candidate-list");
    if (candidateList && hasCandidates) {
      const existingLabels = Array.from(
        candidateList.querySelectorAll<HTMLLIElement>(".candidate-option")
      ).map((li) => li.dataset.value ?? "");
      const newLabels = candidates.map((c) => c.label);

      if (existingLabels.join("\0") !== newLabels.join("\0")) {
        candidateList.innerHTML = "";
        for (const candidate of candidates) {
          const li = document.createElement("li");
          li.className = "candidate-option";
          li.setAttribute("role", "option");
          li.dataset.value = candidate.label;

          const textWrap = document.createElement("div");
          textWrap.className = "candidate-text";

          const artistSpan = document.createElement("span");
          artistSpan.className = "candidate-artist";
          artistSpan.textContent = candidate.artist;

          const songSpan = document.createElement("span");
          songSpan.className = "candidate-song";
          songSpan.textContent = candidate.title;

          const albumSpan = document.createElement("span");
          albumSpan.className = "candidate-album";
          albumSpan.textContent = candidate.album ?? "";
          if (!candidate.album) albumSpan.hidden = true;
          textWrap.append(artistSpan, songSpan, albumSpan);

          // Exact per-candidate liked marker: once a search resolves we hold
          // each candidate's real track id, so its Liked Songs membership is
          // certain — a filled ♥ means "you already liked this one" (issue
          // #43). Hidden until the check resolves (liked == null/undefined).
          const heart = document.createElement("span");
          heart.className = "candidate-liked";
          heart.textContent = "♥";
          heart.setAttribute("aria-hidden", "true");
          heart.hidden = candidate.liked !== true;
          if (candidate.liked === true) heart.title = "Already in Liked Songs";

          li.append(textWrap, heart);
          li.addEventListener("click", () => this._onCandidateSelect(candidate.label));
          candidateList.append(li);
        }
      }

      candidateList.querySelectorAll<HTMLLIElement>(".candidate-option").forEach((li) => {
        const selected = li.dataset.value === currentOption;
        li.classList.toggle("selected", selected);
        li.setAttribute("aria-selected", String(selected));
      });
    }

    // No-match feedback (the ♥ buttons drive the search now that the Find
    // Song button is gone).
    const findStatus = this.shadowRoot.querySelector<HTMLElement>(".find-status");
    if (findStatus) {
      const showNoMatches = this._noMatches && !this._searching && !hasCandidates;
      findStatus.classList.toggle("hidden", !showNoMatches);
      if (showNoMatches) findStatus.textContent = this._statusMessage;
    }

    // Like / Cancel availability
    const likeBtn = this.shadowRoot.querySelector<HTMLButtonElement>(".like-btn");
    const cancelBtn = this.shadowRoot.querySelector<HTMLButtonElement>(".cancel-btn");
    if (likeBtn)
      likeBtn.disabled = this._entity("button", "confirm_like")?.state.state === "unavailable";
    if (cancelBtn)
      cancelBtn.disabled = this._entity("button", "cancel_like")?.state.state === "unavailable";
  }

  // Build one history-style row (artist + song stacked, ♥ like button) —
  // shared by the Now Playing entry and the history list so they render
  // identically (issue #40).
  private _makeTrackEntry(artist: string, title: string, onLike: () => void): HTMLLIElement {
    const li = document.createElement("li");
    li.className = "history-entry";

    const text = document.createElement("div");
    text.className = "history-text";
    const artistSpan = document.createElement("span");
    artistSpan.className = "history-artist";
    artistSpan.textContent = artist;
    const songSpan = document.createElement("span");
    songSpan.className = "history-song";
    songSpan.textContent = title;
    text.append(artistSpan, songSpan);

    const likeBtn = document.createElement("button");
    likeBtn.className = "history-like-btn";
    likeBtn.addEventListener("click", onLike);
    this._applyLikedHeart(likeBtn, "unknown", `${artist} - ${title}`);

    li.append(text, likeBtn);
    return li;
  }

  // Render a heart button for a given liked state: filled ♥ when the song is
  // already a Liked Song, outline ♡ when confirmed not, and a muted outline
  // when it could not be resolved (issue #43). The button always stays a Like
  // affordance regardless of state.
  private _applyLikedHeart(btn: HTMLButtonElement, liked: LikedState, label: string): void {
    btn.textContent = liked === "liked" ? "♥" : "♡";
    btn.classList.toggle("liked", liked === "liked");
    btn.classList.toggle("not-liked", liked === "not_liked");
    btn.classList.toggle("liked-unknown", liked === "unknown");
    const suffix =
      liked === "liked" ? " (already liked)" : liked === "unknown" ? " (like status unknown)" : "";
    btn.title = liked === "liked" ? "Already in Liked Songs" : "Like this song";
    btn.setAttribute("aria-label", `Like ${label}${suffix}`);
  }

  // The hearts go through find_like_matches, so they mirror the backing
  // button entity's availability and the card's in-flight state — but not
  // the Find Song button's nothing-playing graying, since these entries
  // carry their own artist/title.
  private _likeDisabled(): boolean {
    const findState = this._entity("button", "find_like_matches")?.state.state;
    return this._searching || findState === "unavailable" || findState === undefined;
  }

  private _updateNowPlayingEntry(
    track: { artist: string; title: string } | null,
    liked: LikedState
  ): void {
    if (!this.shadowRoot) return;
    const list = this.shadowRoot.querySelector<HTMLUListElement>(".now-playing-list");
    if (!list) return;

    const key = track ? `${track.artist}|${track.title}` : "";
    if (list.dataset.key !== key) {
      list.dataset.key = key;
      list.innerHTML = "";
      if (track) {
        const li = this._makeTrackEntry(track.artist, track.title, () => this._onFind());
        li.classList.add("now-playing-entry");
        list.append(li);
      } else {
        const empty = document.createElement("li");
        empty.className = "history-empty";
        empty.textContent = "Nothing playing";
        list.append(empty);
      }
    }

    const likeBtn = list.querySelector<HTMLButtonElement>(".history-like-btn");
    if (likeBtn) {
      // The liked state can update independently of the track (the async
      // favorites lookup resolves after the row is built), so refresh the
      // heart on every pass, not only when the row is rebuilt.
      if (track) this._applyLikedHeart(likeBtn, liked, `${track.artist} - ${track.title}`);
      likeBtn.disabled = this._likeDisabled();
    }
  }

  // The most recent PINNED_HISTORY_COUNT tracks always show; the chevron
  // only expands/collapses the older ones beneath them.
  private static readonly PINNED_HISTORY_COUNT = 2;

  private _updateHistory(history: PlayedTrack[]): void {
    if (!this.shadowRoot) return;

    const toggle = this.shadowRoot.querySelector<HTMLButtonElement>(".history-toggle");
    const hasOverflow = history.length > BtoddbHaMusicLikeCard.PINNED_HISTORY_COUNT;
    if (toggle) {
      toggle.classList.toggle("hidden", !hasOverflow);
      toggle.setAttribute("aria-expanded", String(this._historyExpanded));
      toggle.classList.toggle("expanded", this._historyExpanded);
      toggle.setAttribute(
        "aria-label",
        this._historyExpanded ? "Show less history" : "Show more history"
      );
    }

    const list = this.shadowRoot.querySelector<HTMLUListElement>(".history-list");
    if (!list) return;

    const key = (t: PlayedTrack) => `${t.artist}|${t.title}|${t.played_at}`;
    const existingKeys = Array.from(
      list.querySelectorAll<HTMLLIElement>(".history-entry")
    ).map((li) => li.dataset.key ?? "");
    const hadEmptyRow = list.querySelector(".history-empty") !== null;
    const newKeys = history.map(key);

    if (
      existingKeys.join("\0") !== newKeys.join("\0") ||
      hadEmptyRow !== (history.length === 0)
    ) {
      list.innerHTML = "";
      if (history.length === 0) {
        const empty = document.createElement("li");
        empty.className = "history-empty";
        empty.textContent = "This space will fill up as you play songs";
        list.append(empty);
      }
      for (const track of history) {
        const li = this._makeTrackEntry(track.artist, track.title, () =>
          this._onFind({ artist: track.artist, title: track.title })
        );
        li.dataset.key = key(track);
        list.append(li);
      }
    }

    // The first PINNED_HISTORY_COUNT rows always show; the rest stay hidden
    // until the chevron expands them.
    list
      .querySelectorAll<HTMLLIElement>(".history-entry")
      .forEach((li, index) => {
        li.classList.toggle(
          "hidden",
          index >= BtoddbHaMusicLikeCard.PINNED_HISTORY_COUNT && !this._historyExpanded
        );
      });

    // Liked state can arrive after the rows are built (the async favorites
    // lookup, or a confirmed like stamping older entries), so refresh each
    // row's heart on every pass — rows are rendered in history order.
    const likeDisabled = this._likeDisabled();
    list
      .querySelectorAll<HTMLLIElement>(".history-entry")
      .forEach((li, index) => {
        const btn = li.querySelector<HTMLButtonElement>(".history-like-btn");
        if (!btn) return;
        btn.disabled = likeDisabled;
        const track = history[index];
        if (track)
          this._applyLikedHeart(
            btn,
            toLikedState(track.liked),
            `${track.artist} - ${track.title}`
          );
      });
  }

  private _updateDropdown(selector: string, resolved: ResolvedEntity | null): void {
    if (!this.shadowRoot) return;
    const dropdown = this.shadowRoot.querySelector<HTMLSelectElement>(selector);
    if (!dropdown) return;

    const options = (resolved?.state.attributes?.options as string[] | undefined) ?? [];
    dropdown.disabled = options.length === 0;

    const existing = Array.from(dropdown.options).map((o) => o.value);
    if (existing.join("\0") !== options.join("\0")) {
      dropdown.innerHTML = "";
      for (const option of options) {
        const el = document.createElement("option");
        el.value = option;
        el.textContent = option;
        dropdown.append(el);
      }
    }

    const current = resolved?.state.state;
    if (current && options.includes(current)) {
      dropdown.value = current;
    } else {
      dropdown.selectedIndex = -1;
    }
  }

  // The single Play button doubles as Pause and Resume (issue #39). It shows
  // whichever transport applies to the current playback state and delegates to
  // that action's availability rules: Resume while the integration reports a
  // paused playlist (its resume_music button is available), Pause while a
  // playlist plays un-paused (pause_music available), and Play otherwise —
  // including radio, which grays Play because something is playing. The
  // resume/pause backing entities are mutually exclusive per playback state
  // (PM-8), so at most one wins and the button never presents both actions.
  private _updateTransportButton(nothingPlaying: boolean): void {
    let mode: TransportMode = "play";
    if (!nothingPlaying) {
      if (this._backingAvailable("resume_music")) mode = "resume";
      else if (this._backingAvailable("pause_music")) mode = "pause";
    }
    this._transportMode = mode;

    const specs: Record<
      TransportMode,
      { suffix: string; inFlight: boolean; label: string; busy: string; disabled: boolean }
    > = {
      play: { suffix: "play_music", inFlight: this._playing, label: "Play", busy: "Playing…", disabled: !nothingPlaying },
      pause: { suffix: "pause_music", inFlight: this._pausing, label: "Pause", busy: "Pausing…", disabled: nothingPlaying },
      resume: { suffix: "resume_music", inFlight: this._resuming, label: "Resume", busy: "Resuming…", disabled: nothingPlaying },
    };
    const spec = specs[mode];
    this._updateActionButton(".play-btn", [spec.suffix], spec.inFlight, spec.label, spec.busy, spec.disabled);
  }

  private _backingAvailable(suffix: string): boolean {
    const state = this._entity("button", suffix)?.state.state;
    return state !== undefined && state !== "unavailable";
  }

  private _onTransport(): void {
    if (this._transportMode === "pause") void this._onPause();
    else if (this._transportMode === "resume") void this._onResume();
    else void this._onPlay();
  }

  private _updateActionButton(
    selector: string,
    buttonSuffixes: string[],
    inFlight: boolean,
    label: string,
    inFlightLabel: string,
    forceDisabled = false
  ): void {
    if (!this.shadowRoot) return;
    const btn = this.shadowRoot.querySelector<HTMLButtonElement>(selector);
    if (!btn) return;
    const backing = buttonSuffixes
      .map((suffix) => this._entity("button", suffix)?.state.state)
      .find((state) => state !== undefined);
    btn.disabled =
      forceDisabled || inFlight || backing === "unavailable" || backing === undefined;
    btn.textContent = inFlight ? inFlightLabel : label;
  }

  private _onDropdownChange(domain: string, suffix: string, option: string): void {
    if (!this._hass || !option) return;
    const resolved = this._entity(domain, suffix);
    if (!resolved) return;
    this._hass.callService("select", "select_option", {
      entity_id: resolved.entityId,
      option,
    });
  }

  private _onCandidateSelect(label: string): void {
    if (!this._hass) return;
    const resolved = this._entity("select", "like_candidate");
    if (!resolved) return;
    this._hass.callService("select", "select_option", {
      entity_id: resolved.entityId,
      option: label,
    });
  }

  private async _onPlay(): Promise<void> {
    await this._runTransient(
      "play_music",
      (v) => (this._playing = v),
      () => this._playing
    );
  }

  private async _onStop(): Promise<void> {
    await this._runTransient(
      "stop_music",
      (v) => (this._stopping = v),
      () => this._stopping
    );
  }

  private async _onPause(): Promise<void> {
    await this._runTransient(
      "pause_music",
      (v) => (this._pausing = v),
      () => this._pausing
    );
  }

  private async _onResume(): Promise<void> {
    await this._runTransient(
      "resume_music",
      (v) => (this._resuming = v),
      () => this._resuming
    );
  }

  private async _onSkip(): Promise<void> {
    await this._runTransient(
      "next_track",
      (v) => (this._skipping = v),
      () => this._skipping
    );
  }

  private async _runTransient(
    service: string,
    setFlag: (value: boolean) => void,
    getFlag: () => boolean
  ): Promise<void> {
    if (!this._hass || getFlag()) return;
    setFlag(true);
    this._update();
    try {
      await this._callService(service);
    } catch (err: unknown) {
      console.warn(`[btoddb-ha-music] ${service} failed:`, err);
    } finally {
      setFlag(false);
      this._update();
    }
  }

  private async _onFind(data?: Record<string, unknown>): Promise<void> {
    if (!this._hass || this._searching) return;
    this._searching = true;
    this._noMatches = false;
    this._update();
    try {
      await this._callService("find_like_matches", data);
    } catch (err: unknown) {
      this._noMatches = true;
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message;
      this._statusMessage = msg ?? "No songs found";
    } finally {
      this._searching = false;
      this._update();
    }
  }

  private async _callService(
    service: string,
    data?: Record<string, unknown>
  ): Promise<void> {
    if (!this._hass) return;
    await this._hass.callService("btoddb_ha_music", service, data);
  }

  private _css(): string {
    return `
      :host {
        display: block;
      }
      .card-content {
        padding: 0 16px 16px;
        display: flex;
        flex-direction: column;
        gap: 14px;
      }
      .section {
        width: 100%;
      }
      .section-label {
        font-size: 0.8em;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: var(--secondary-text-color);
        margin-bottom: 4px;
      }
      .dropdown {
        width: 100%;
        min-height: 40px;
        padding: 0 8px;
        font-family: inherit;
        font-size: 0.95em;
        color: var(--primary-text-color);
        background: var(--card-background-color, #fff);
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        cursor: pointer;
      }
      .dropdown:disabled {
        opacity: 0.5;
        cursor: not-allowed;
      }
      .btn-row {
        display: flex;
        gap: 8px;
      }
      .btn-row .ha-btn {
        flex: 1;
      }
      .ha-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 36px;
        padding: 0 16px;
        border: none;
        border-radius: 4px;
        font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        font-size: 0.875rem;
        font-weight: 500;
        letter-spacing: 0.08929em;
        text-transform: uppercase;
        cursor: pointer;
        background-color: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
        box-shadow: 0 3px 1px -2px rgba(0,0,0,.2), 0 2px 2px 0 rgba(0,0,0,.14), 0 1px 5px 0 rgba(0,0,0,.12);
        transition: box-shadow 280ms cubic-bezier(0.4, 0, 0.2, 1);
        outline: none;
      }
      .ha-btn:hover:not(:disabled) {
        box-shadow: 0 2px 4px -1px rgba(0,0,0,.2), 0 4px 5px 0 rgba(0,0,0,.14), 0 1px 10px 0 rgba(0,0,0,.12);
      }
      .ha-btn:disabled {
        background-color: rgba(0,0,0,.12);
        color: rgba(0,0,0,.37);
        box-shadow: none;
        cursor: not-allowed;
      }
      .history-wrap {
        position: relative;
      }
      .history-toggle {
        position: absolute;
        left: 50%;
        bottom: 0;
        transform: translate(-50%, 50%);
        width: 22px;
        height: 22px;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 0;
        margin: 0;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 50%;
        background: var(--card-background-color, #fff);
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.15);
        cursor: pointer;
      }
      .chevron {
        width: 7px;
        height: 7px;
        border-right: 2px solid var(--secondary-text-color);
        border-bottom: 2px solid var(--secondary-text-color);
        transform: rotate(45deg);
        transition: transform 0.15s ease;
        margin-top: -3px;
      }
      .history-toggle.expanded .chevron {
        transform: rotate(-135deg);
        margin-top: 3px;
      }
      .track-list {
        list-style: none;
        padding: 0;
        margin: 6px 0 0;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        max-height: 300px;
        overflow-y: auto;
      }
      .track-list.hidden {
        display: none;
      }
      .history-entry {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 6px 12px;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
      }
      .history-entry:last-child {
        border-bottom: none;
      }
      .history-entry.hidden {
        display: none;
      }
      .history-text {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 0;
      }
      .history-artist {
        font-size: 0.9em;
        font-weight: 600;
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .history-song {
        font-size: 0.85em;
        color: var(--primary-text-color);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .history-empty {
        padding: 8px 12px;
        font-size: 0.85em;
        color: var(--secondary-text-color);
        font-style: italic;
      }
      .history-like-btn {
        flex-shrink: 0;
        border: none;
        background: none;
        cursor: pointer;
        font-size: 1.2em;
        line-height: 1;
        padding: 4px 6px;
        color: var(--primary-color, #03a9f4);
      }
      .history-like-btn:hover:not(:disabled) {
        transform: scale(1.15);
      }
      .history-like-btn:disabled {
        color: rgba(0,0,0,.26);
        cursor: not-allowed;
      }
      /* Liked-state hearts (issue #43): filled = already a Liked Song,
         outline = confirmed not liked, muted outline = could not resolve. */
      .history-like-btn.liked {
        color: var(--error-color, #e0245e);
      }
      .history-like-btn.not-liked {
        color: var(--primary-color, #03a9f4);
      }
      .history-like-btn.liked-unknown {
        color: var(--secondary-text-color, #727272);
        opacity: 0.55;
      }
      .find-status {
        font-size: 0.85em;
        color: var(--secondary-text-color);
        text-align: center;
      }
      .find-status.hidden,
      .like-section.hidden,
      .history-toggle.hidden {
        display: none;
      }
      .candidate-list {
        list-style: none;
        padding: 0;
        margin: 0 0 8px;
        border: 1px solid var(--divider-color, #e0e0e0);
        border-radius: 6px;
        max-height: 260px;
        overflow-y: auto;
      }
      .candidate-option {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 8px;
        padding: 8px 12px;
        cursor: pointer;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        transition: background 0.1s;
      }
      .candidate-text {
        display: flex;
        flex-direction: column;
        flex: 1;
        min-width: 0;
      }
      .candidate-liked {
        flex-shrink: 0;
        font-size: 1.1em;
        line-height: 1;
        color: var(--error-color, #e0245e);
      }
      .candidate-option:last-child {
        border-bottom: none;
      }
      .candidate-option:hover {
        background: var(--secondary-background-color, rgba(0, 0, 0, 0.04));
      }
      .candidate-option.selected {
        background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.12);
      }
      .candidate-artist {
        font-size: 0.9em;
        font-weight: 600;
        color: var(--primary-text-color);
      }
      .candidate-song {
        font-size: 0.85em;
        color: var(--primary-text-color);
      }
      .candidate-album {
        font-size: 0.8em;
        color: var(--secondary-text-color);
        font-style: italic;
      }
    `;
  }
}

if (!customElements.get(CARD_TYPE)) {
  customElements.define(CARD_TYPE, BtoddbHaMusicLikeCard);
  (window as unknown as Record<string, unknown[]>)["customCards"] ??= [];
  ((window as unknown as Record<string, unknown[]>)["customCards"]).push({
    type: CARD_TYPE,
    name: "HA Music — Like Card",
    description:
      "Now playing, music source and speaker selection, playback controls, and Spotify likes.",
  });
}
