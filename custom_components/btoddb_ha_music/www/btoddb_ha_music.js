(function () {
    'use strict';

    // v0.0.6
    const CARD_VERSION = "v0.0.6";
    const CARD_TYPE = "btoddb-ha-music-like-card";
    console.info(`%c BTODDB-HA-MUSIC-LIKE-CARD %c ${CARD_VERSION} `, "color: white; background: #00b4d8; font-weight: 700;", "color: #00b4d8; background: white; font-weight: 700;");
    class BtoddbHaMusicLikeCard extends HTMLElement {
        _config = {};
        _hass = null;
        _rendered = false;
        static getStubConfig() {
            return { entity_prefix: "btoddb_ha_music" };
        }
        setConfig(config) {
            this._config = config;
            if (this._hass)
                this._update();
        }
        set hass(hass) {
            this._hass = hass;
            if (!this._rendered) {
                this._initialRender();
            }
            else {
                this._update();
            }
        }
        getCardSize() {
            return 4;
        }
        get _prefix() {
            return this._config.entity_prefix ?? "btoddb_ha_music";
        }
        _initialRender() {
            if (!this._hass)
                return;
            const shadow = this.attachShadow({ mode: "open" });
            const style = document.createElement("style");
            style.textContent = this._css();
            const card = document.createElement("ha-card");
            card.setAttribute("header", "Like This Track");
            // --- Card content ---
            const content = document.createElement("div");
            content.className = "card-content";
            content.append(this._makeInfoRow("artist-row", "Artist", "artist-value"), this._makeInfoRow("title-row", "Song", "title-value"), this._makeCandidateRow());
            // --- Card actions ---
            const actions = document.createElement("div");
            actions.className = "card-actions";
            const findBtn = this._makeButton("find-btn", "Find Matches");
            findBtn.addEventListener("click", () => this._callService("find_like_matches"));
            const actionRow = document.createElement("div");
            actionRow.className = "action-row";
            const likeBtn = this._makeButton("like-btn", "Like");
            likeBtn.addEventListener("click", () => this._callService("confirm_like"));
            const cancelBtn = this._makeButton("cancel-btn", "Cancel");
            cancelBtn.addEventListener("click", () => this._callService("cancel_like"));
            actionRow.append(likeBtn, cancelBtn);
            actions.append(findBtn, actionRow);
            card.append(content, actions);
            shadow.append(style, card);
            this._rendered = true;
            this._update();
        }
        _makeInfoRow(rowClass, labelText, valueClass) {
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
        _makeCandidateRow() {
            const row = document.createElement("div");
            row.className = "candidate-row hidden";
            const label = document.createElement("div");
            label.className = "label candidate-label";
            label.textContent = "Match";
            const list = document.createElement("ul");
            list.className = "candidate-list";
            list.setAttribute("role", "listbox");
            row.append(label, list);
            return row;
        }
        _makeButton(className, label) {
            const btn = document.createElement("button");
            btn.className = `ha-btn ${className}`;
            btn.textContent = label;
            return btn;
        }
        _update() {
            if (!this._rendered || !this._hass || !this.shadowRoot)
                return;
            const nowPlaying = this._hass.states[`sensor.${this._prefix}_now_playing`];
            const likeCandidate = this._hass.states[`select.${this._prefix}_like_candidate`];
            const confirmState = this._hass.states[`button.${this._prefix}_confirm_like`];
            const cancelState = this._hass.states[`button.${this._prefix}_cancel_like`];
            // Artist / Song
            const artistEl = this.shadowRoot.querySelector(".artist-value");
            if (artistEl)
                artistEl.textContent = String(nowPlaying?.attributes?.artist ?? "—");
            const titleEl = this.shadowRoot.querySelector(".title-value");
            if (titleEl)
                titleEl.textContent = String(nowPlaying?.attributes?.title ?? "—");
            // Candidate listbox
            const candidateRow = this.shadowRoot.querySelector(".candidate-row");
            const candidateList = this.shadowRoot.querySelector(".candidate-list");
            const currentOption = likeCandidate?.state;
            const structuredCandidates = likeCandidate?.attributes?.candidates ?? [];
            const fallbackOptions = likeCandidate?.attributes?.options ?? [];
            const candidates = structuredCandidates.length > 0
                ? structuredCandidates
                : fallbackOptions.map((opt) => ({ label: opt, artist: opt, title: "", album: null }));
            const hasCandidates = candidates.length > 0;
            if (candidateRow)
                candidateRow.classList.toggle("hidden", !hasCandidates);
            if (candidateList && hasCandidates) {
                const existingLabels = Array.from(candidateList.querySelectorAll(".candidate-option")).map((li) => li.dataset.value ?? "");
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
                        if (!candidate.album)
                            albumSpan.hidden = true;
                        li.append(artistSpan, songSpan, albumSpan);
                        li.addEventListener("click", () => this._onCandidateSelect(candidate.label));
                        candidateList.append(li);
                    }
                }
                candidateList.querySelectorAll(".candidate-option").forEach((li) => {
                    const selected = li.dataset.value === currentOption;
                    li.classList.toggle("selected", selected);
                    li.setAttribute("aria-selected", String(selected));
                });
            }
            // Button availability
            const likeBtn = this.shadowRoot.querySelector(".like-btn");
            const cancelBtn = this.shadowRoot.querySelector(".cancel-btn");
            if (likeBtn)
                likeBtn.disabled = confirmState?.state === "unavailable";
            if (cancelBtn)
                cancelBtn.disabled = cancelState?.state === "unavailable";
        }
        _onCandidateSelect(label) {
            if (!this._hass)
                return;
            this._hass.callService("select", "select_option", {
                entity_id: `select.${this._prefix}_like_candidate`,
                option: label,
            });
        }
        async _callService(service) {
            if (!this._hass)
                return;
            await this._hass.callService("btoddb_ha_music", service);
        }
        _css() {
            return `
      :host {
        display: block;
      }
      .card-content {
        padding: 16px 16px 8px;
      }
      .info-row {
        display: flex;
        align-items: baseline;
        gap: 8px;
        margin-bottom: 6px;
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
      .candidate-row {
        display: flex;
        flex-direction: column;
        gap: 6px;
        margin-top: 12px;
        width: 100%;
      }
      .candidate-row.hidden {
        display: none;
      }
      .candidate-label {
        min-width: unset;
      }
      .candidate-list {
        list-style: none;
        padding: 0;
        margin: 0;
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
      .card-actions {
        padding: 8px 16px 16px;
        display: flex;
        flex-direction: column;
        gap: 8px;
      }
      .action-row {
        display: flex;
        gap: 8px;
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
      .find-btn {
        width: 100%;
      }
      .action-row .ha-btn {
        flex: 1;
      }
      .like-btn {
        background-color: var(--success-color, #4caf50);
        color: #fff;
      }
      .cancel-btn {
        background-color: var(--error-color, #f44336);
        color: #fff;
      }
    `;
        }
    }
    if (!customElements.get(CARD_TYPE)) {
        customElements.define(CARD_TYPE, BtoddbHaMusicLikeCard);
        window["customCards"] ??= [];
        (window["customCards"]).push({
            type: CARD_TYPE,
            name: "HA Music — Like Card",
            description: "Displays the currently playing track and lets you like it on Spotify.",
        });
    }

})();
//# sourceMappingURL=btoddb_ha_music.js.map
