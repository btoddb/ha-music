// v0.0.1
const CARD_VERSION = "v0.0.1";
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

class BtoddbHaMusicLikeCard extends HTMLElement {
  private _config: CardConfig = {};
  private _hass: Hass | null = null;
  private _rendered = false;

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
    return 4;
  }

  private get _prefix(): string {
    return this._config.entity_prefix ?? "btoddb_ha_music";
  }

  private _initialRender(): void {
    if (!this._hass) return;

    const shadow = this.attachShadow({ mode: "open" });

    const style = document.createElement("style");
    style.textContent = this._css();

    const card = document.createElement("ha-card");
    card.setAttribute("header", "Like This Track");

    // --- Card content ---
    const content = document.createElement("div");
    content.className = "card-content";

    content.append(
      this._makeInfoRow("artist-row", "Artist", "artist-value"),
      this._makeInfoRow("title-row", "Song", "title-value"),
      this._makeCandidateRow()
    );

    // --- Card actions ---
    const actions = document.createElement("div");
    actions.className = "card-actions";

    const findBtn = this._makeButton("find-btn", "Find Matches", "mdi:magnify");
    findBtn.addEventListener("click", () => this._callService("find_like_matches"));

    const actionRow = document.createElement("div");
    actionRow.className = "action-row";

    const confirmBtn = this._makeButton("confirm-btn", "Confirm", "mdi:check");
    confirmBtn.addEventListener("click", () => this._callService("confirm_like"));

    const cancelBtn = this._makeButton("cancel-btn", "Cancel", "mdi:close");
    cancelBtn.addEventListener("click", () => this._callService("cancel_like"));

    actionRow.append(confirmBtn, cancelBtn);
    actions.append(findBtn, actionRow);

    card.append(content, actions);
    shadow.append(style, card);

    this._rendered = true;
    this._update();
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

  private _makeCandidateRow(): HTMLElement {
    const row = document.createElement("div");
    row.className = "candidate-row hidden";
    const label = document.createElement("label");
    label.className = "label";
    label.textContent = "Match";
    const select = document.createElement("select");
    select.className = "candidate-select";
    select.addEventListener("change", (e) => this._onSelectChange(e));
    row.append(label, select);
    return row;
  }

  private _makeButton(className: string, label: string, icon: string): HTMLElement {
    const btn = document.createElement("button");
    btn.className = `action-btn ${className}`;
    btn.setAttribute("aria-label", label);

    const iconEl = document.createElement("ha-icon");
    iconEl.setAttribute("icon", icon);

    const labelEl = document.createElement("span");
    labelEl.textContent = label;

    btn.append(iconEl, labelEl);
    return btn;
  }

  private _update(): void {
    if (!this._rendered || !this._hass || !this.shadowRoot) return;

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

    // Candidate select
    const candidateRow = this.shadowRoot.querySelector<HTMLElement>(".candidate-row");
    const selectEl = this.shadowRoot.querySelector<HTMLSelectElement>(".candidate-select");
    const options = (likeCandidate?.attributes?.options as string[] | undefined) ?? [];
    const currentOption = likeCandidate?.state;
    const hasCandidates = options.length > 0;

    if (candidateRow) candidateRow.classList.toggle("hidden", !hasCandidates);

    if (selectEl && hasCandidates) {
      const existing = Array.from(selectEl.options).map((o) => o.value);
      if (existing.join(",") !== options.join(",")) {
        selectEl.innerHTML = "";
        for (const opt of options) {
          const el = document.createElement("option");
          el.value = opt;
          el.textContent = opt;
          selectEl.append(el);
        }
      }
      if (currentOption && selectEl.value !== currentOption) {
        selectEl.value = currentOption;
      }
    }

    // Button availability
    const confirmBtn = this.shadowRoot.querySelector<HTMLButtonElement>(".confirm-btn");
    const cancelBtn = this.shadowRoot.querySelector<HTMLButtonElement>(".cancel-btn");

    if (confirmBtn)
      confirmBtn.disabled = confirmState?.state === "unavailable";
    if (cancelBtn)
      cancelBtn.disabled = cancelState?.state === "unavailable";
  }

  private _onSelectChange(e: Event): void {
    const select = e.target as HTMLSelectElement;
    const option = select.value;
    if (!option || !this._hass) return;
    this._hass.callService("select", "select_option", {
      entity_id: `select.${this._prefix}_like_candidate`,
      option,
    });
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
        gap: 4px;
        margin-top: 12px;
        width: 100%;
      }
      .candidate-row.hidden {
        display: none;
      }
      .candidate-select {
        width: 100%;
        padding: 8px 10px;
        border-radius: 6px;
        border: 1px solid var(--divider-color, #e0e0e0);
        background: var(--card-background-color, #fff);
        color: var(--primary-text-color);
        font-size: 0.9em;
        cursor: pointer;
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
      .action-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        padding: 6px 14px;
        border: none;
        border-radius: 6px;
        background: var(--primary-color, #03a9f4);
        color: var(--text-primary-color, #fff);
        font-size: 0.875em;
        font-weight: 500;
        cursor: pointer;
        transition: filter 0.15s;
      }
      .action-btn:hover:not(:disabled) {
        filter: brightness(1.1);
      }
      .action-btn:disabled {
        opacity: 0.4;
        cursor: default;
      }
      .find-btn {
        width: 100%;
      }
      .action-row .action-btn {
        flex: 1;
      }
      .confirm-btn {
        background: var(--success-color, #4caf50);
        color: #fff;
      }
      .cancel-btn {
        background: var(--error-color, #f44336);
        color: #fff;
      }
      ha-icon {
        --mdc-icon-size: 18px;
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
    description: "Displays the currently playing track and lets you like it on Spotify.",
  });
}
