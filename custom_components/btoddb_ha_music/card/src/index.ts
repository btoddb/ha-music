// v0.0.19
const CARD_VERSION = "v0.0.19";
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
}

interface ResolvedEntity {
  entityId: string;
  state: HassState;
}

class BtoddbHaMusicLikeCard extends HTMLElement {
  private _config: CardConfig = {};
  private _hass: Hass | null = null;
  private _rendered = false;
  private _searching = false;
  private _skipping = false;
  private _playing = false;
  private _stopping = false;
  private _noMatches = false;
  private _statusMessage = "";
  private _lastPlayingKey = "";

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

    // --- Now Playing ---
    const nowPlaying = document.createElement("div");
    nowPlaying.className = "section now-playing-section";
    nowPlaying.append(
      this._makeSectionLabel("Now Playing"),
      this._makeInfoRow("artist-row", "Artist", "artist-value"),
      this._makeInfoRow("title-row", "Song", "title-value")
    );

    // --- Music source selector ---
    const mediaSection = document.createElement("div");
    mediaSection.className = "section media-section";
    const mediaSelect = this._makeDropdown("media-select");
    mediaSelect.addEventListener("change", () =>
      this._onDropdownChange("select", "music", mediaSelect.value)
    );
    mediaSection.append(this._makeSectionLabel("Music"), mediaSelect);

    // --- Play / Skip ---
    const playRow = document.createElement("div");
    playRow.className = "section btn-row play-row";
    const playBtn = this._makeButton("play-btn", "Play");
    playBtn.addEventListener("click", () => this._onPlay());
    const skipBtn = this._makeButton("skip-btn", "Skip");
    skipBtn.addEventListener("click", () => this._onSkip());
    playRow.append(playBtn, skipBtn);

    // --- Stop / Find Song ---
    const stopRow = document.createElement("div");
    stopRow.className = "section btn-row stop-row";
    const stopBtn = this._makeButton("stop-btn", "Stop");
    stopBtn.addEventListener("click", () => this._onStop());
    const findBtn = this._makeButton("find-btn", "Find Song");
    findBtn.addEventListener("click", () => this._onFind());
    stopRow.append(stopBtn, findBtn);

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

  private _makeInfoRow(rowClass: string, labelText: string, valueClass: string): HTMLElement {
    const row = document.createElement("div");
    row.className = `info-row ${rowClass}`;
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = labelText;
    const value = document.createElement("span");
    value.className = `value ${valueClass}`;
    value.textContent = "—";
    row.append(label, value);
    return row;
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

    // Now Playing
    const artistEl = this.shadowRoot.querySelector(".artist-value");
    if (artistEl)
      artistEl.textContent = String(nowPlaying?.attributes?.artist ?? "—");

    const titleEl = this.shadowRoot.querySelector(".title-value");
    if (titleEl)
      titleEl.textContent = String(nowPlaying?.attributes?.title ?? "—");

    // Selectors
    this._updateDropdown(".media-select", this._entity("select", "music"));
    this._updateDropdown(".speakers-select", this._entity("select", "speaker_group"));

    // Transport buttons — availability mirrors the integration's button
    // entities, layered with this card's own in-flight state.
    this._updateActionButton(".play-btn", ["play_music"], this._playing, "Play", "Playing…");
    this._updateActionButton(
      ".skip-btn",
      ["skip_song", "next_track"],
      this._skipping,
      "Skip",
      "Skipping…"
    );
    this._updateActionButton(".stop-btn", ["stop_music"], this._stopping, "Stop", "Stop");

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

          li.append(artistSpan, songSpan, albumSpan);
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

    // Find button + no-match feedback
    const findBtn = this.shadowRoot.querySelector<HTMLButtonElement>(".find-btn");
    const findStatus = this.shadowRoot.querySelector<HTMLElement>(".find-status");
    if (findBtn) {
      const findState = this._entity("button", "find_like_matches")?.state.state;
      findBtn.disabled =
        this._searching || findState === "unavailable" || findState === undefined;
      findBtn.textContent = this._searching ? "Searching…" : "Find Song";
    }
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

  private _updateActionButton(
    selector: string,
    buttonSuffixes: string[],
    inFlight: boolean,
    label: string,
    inFlightLabel: string
  ): void {
    if (!this.shadowRoot) return;
    const btn = this.shadowRoot.querySelector<HTMLButtonElement>(selector);
    if (!btn) return;
    const backing = buttonSuffixes
      .map((suffix) => this._entity("button", suffix)?.state.state)
      .find((state) => state !== undefined);
    btn.disabled = inFlight || backing === "unavailable" || backing === undefined;
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

  private async _onFind(): Promise<void> {
    if (!this._hass || this._searching) return;
    this._searching = true;
    this._noMatches = false;
    this._update();
    try {
      await this._callService("find_like_matches");
    } catch (err: unknown) {
      this._noMatches = true;
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message;
      this._statusMessage = msg ?? "No songs found";
    } finally {
      this._searching = false;
      this._update();
    }
  }

  private async _callService(service: string): Promise<void> {
    if (!this._hass) return;
    await this._hass.callService("btoddb_ha_music", service);
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
      .info-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 4px;
        width: 100%;
      }
      .label {
        font-size: 0.8em;
        font-weight: 600;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: var(--secondary-text-color);
        min-width: 52px;
        flex-shrink: 0;
      }
      .value {
        font-size: 1em;
        color: var(--primary-text-color);
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .artist-value {
        font-weight: 600;
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
      .find-status {
        font-size: 0.85em;
        color: var(--secondary-text-color);
        text-align: center;
      }
      .find-status.hidden,
      .like-section.hidden {
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
        flex-direction: column;
        padding: 8px 12px;
        cursor: pointer;
        border-bottom: 1px solid var(--divider-color, #e0e0e0);
        transition: background 0.1s;
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
