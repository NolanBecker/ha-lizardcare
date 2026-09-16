const EVENT_TYPE = "lizardcare_journal_updated";

const EVENT_DETAILS = {
  feeding: ["Feeding", "mdi:food-apple"],
  food_removed: ["Food Removed", "mdi:food-apple-off"],
  spot_clean: ["Spot Clean", "mdi:broom"],
  full_clean: ["Full Clean", "mdi:spray-bottle"],
  note: ["Note", "mdi:note-text-outline"],
  shed: ["Shed", "mdi:snake"],
  weight: ["Weight", "mdi:scale"],
  enclosure: ["Enclosure", "mdi:home-outline"],
  health: ["Health", "mdi:heart-pulse"],
  other: ["Other", "mdi:dots-horizontal-circle-outline"],
};

class LizardCareHistoryCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Lizard Care History Card requires an entity");
    }
    this._config = {
      title: "Recent Activity",
      limit: 5,
      show_add: true,
      show_view_all: true,
      view_all_hash: "#pixel-history",
      ...config,
    };
    this._entries = [];
    this._loading = true;
    this._error = null;
    this._dialogOpen = false;
    this._submitting = false;
    this._formError = null;
    this._render();
  }

  set hass(hass) {
    const connectionChanged = this._hass?.connection !== hass.connection;
    this._hass = hass;
    if (!this._loaded || connectionChanged) {
      this._loaded = true;
      this._subscribe();
      this._loadEntries();
    }
  }

  connectedCallback() {
    if (this._hass && !this._loaded) {
      this._loaded = true;
      this._subscribe();
      this._loadEntries();
    }
  }

  disconnectedCallback() {
    this._unsubscribe?.();
    this._unsubscribe = undefined;
    this._loaded = false;
  }

  getCardSize() {
    return Math.max(2, Math.ceil((this._entries?.length || 1) * 0.8) + 1);
  }

  async _subscribe() {
    this._unsubscribe?.();
    try {
      this._unsubscribe = await this._hass.connection.subscribeEvents(
        (event) => {
          if (event.data?.entry_id === this._entryId) {
            this._loadEntries();
          }
        },
        EVENT_TYPE,
      );
    } catch (_error) {
      // Retrieval still works; reconnecting Home Assistant will retry.
    }
  }

  async _loadEntries() {
    if (!this._hass || !this._config) return;
    this._loading = true;
    this._error = null;
    this._render();
    try {
      const result = await this._hass.callWS({
        type: "lizardcare/journal/get",
        entity_id: this._config.entity,
        limit: Number(this._config.limit) || 5,
      });
      this._entryId = result.entry_id;
      this._entries = result.entries || [];
    } catch (error) {
      this._error = error?.message || "Unable to load care history.";
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _dateKey(date) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: this._hass?.config?.time_zone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(date);
    const value = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${value.year}-${value.month}-${value.day}`;
  }

  _dateHeading(date) {
    const now = new Date();
    const today = this._dateKey(now);
    const [year, month, day] = today.split("-").map(Number);
    const yesterday = new Date(Date.UTC(year, month - 1, day - 1))
      .toISOString().slice(0, 10);
    const key = this._dateKey(date);
    if (key === today) return "Today";
    if (key === yesterday) return "Yesterday";
    const options = { month: "short", day: "numeric" };
    if (key.slice(0, 4) !== today.slice(0, 4)) options.year = "numeric";
    return new Intl.DateTimeFormat(this._locale(), {
      ...options,
      timeZone: this._hass?.config?.time_zone,
    }).format(date);
  }

  _time(date) {
    return new Intl.DateTimeFormat(this._locale(), {
      hour: "numeric",
      minute: "2-digit",
      timeZone: this._hass?.config?.time_zone,
    }).format(date);
  }

  _locale() {
    return this._hass?.locale?.language || navigator.language;
  }

  _localDateTime(date = new Date()) {
    const offset = date.getTimezoneOffset() * 60000;
    return new Date(date.getTime() - offset).toISOString().slice(0, 16);
  }

  _openAddDialog() {
    this._dialogOpen = true;
    this._formError = null;
    this._formValues = {
      eventType: "note",
      note: "",
      timestamp: this._localDateTime(),
      weightValue: "",
      weightUnit: "g",
    };
    this._render();
    this.shadowRoot.getElementById("event-type")?.focus();
  }

  _closeAddDialog() {
    if (this._submitting) return;
    this._dialogOpen = false;
    this._formError = null;
    this._render();
  }

  _toggleWeightFields() {
    const eventType = this.shadowRoot.getElementById("event-type")?.value;
    const isWeight = eventType === "weight";
    this.shadowRoot.getElementById("weight-fields")?.toggleAttribute("hidden", !isWeight);
    const icon = this.shadowRoot.getElementById("event-icon");
    if (icon) icon.icon = EVENT_DETAILS[eventType]?.[1] || EVENT_DETAILS.other[1];
  }

  async _submitEntry(event) {
    event.preventDefault();
    if (this._submitting) return;
    const form = new FormData(event.currentTarget);
    const eventType = form.get("event_type");
    const timestamp = form.get("timestamp");
    this._formValues = {
      eventType,
      note: String(form.get("note") || ""),
      timestamp: String(timestamp || ""),
      weightValue: String(form.get("weight_value") || ""),
      weightUnit: String(form.get("weight_unit") || "g"),
    };
    const message = {
      type: "lizardcare/journal/create",
      entity_id: this._config.entity,
      event_type: eventType,
    };
    const note = String(form.get("note") || "").trim();
    if (note) message.note = note;
    if (timestamp) message.timestamp = new Date(timestamp).toISOString();
    if (eventType === "weight") {
      const value = Number(form.get("weight_value"));
      if (!Number.isFinite(value) || value <= 0) {
        this._formError = "Weight must be a number greater than zero.";
        this._render();
        return;
      }
      message.weight_value = value;
      message.weight_unit = form.get("weight_unit");
    }
    this._submitting = true;
    this._formError = null;
    this._render();
    try {
      await this._hass.callWS(message);
      this._dialogOpen = false;
      await this._loadEntries();
    } catch (error) {
      this._formError = error?.message || "Unable to save this journal entry.";
    } finally {
      this._submitting = false;
      this._render();
    }
  }

  _addDialog() {
    if (!this._dialogOpen) return "";
    const values = this._formValues;
    const options = Object.entries(EVENT_DETAILS).map(([value, [label]]) =>
      `<option value="${value}" ${value === values.eventType ? "selected" : ""}>${this._escape(label)}</option>`
    ).join("");
    const weight = values.eventType === "weight";
    return `<div class="scrim" id="dialog-scrim">
      <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <h3 id="dialog-title">Add Journal Entry</h3>
        <form id="entry-form">
          <label>Event Type<div class="select-with-icon"><ha-icon id="event-icon" icon="${EVENT_DETAILS[values.eventType]?.[1] || EVENT_DETAILS.other[1]}"></ha-icon><select id="event-type" name="event_type" required>${options}</select></div></label>
          <label>Note<textarea name="note" maxlength="2000" rows="3" placeholder="Optional details">${this._escape(values.note)}</textarea></label>
          <label>Date/Time<input name="timestamp" type="datetime-local" value="${this._escape(values.timestamp)}" required></label>
          <div id="weight-fields" ${weight ? "" : "hidden"}>
            <label>Weight Value<input name="weight_value" type="number" min="0.01" step="any" inputmode="decimal" value="${this._escape(values.weightValue)}" ${weight ? "required" : ""}></label>
            <label>Weight Unit<select name="weight_unit"><option value="g" ${values.weightUnit === "g" ? "selected" : ""}>g</option><option value="oz" ${values.weightUnit === "oz" ? "selected" : ""}>oz</option></select></label>
          </div>
          <p class="helper">Journal entries do not change care schedules or completion status.</p>
          ${this._formError ? `<p class="form-error" role="alert">${this._escape(this._formError)}</p>` : ""}
          <div class="dialog-actions">
            <button id="cancel-entry" type="button" ${this._submitting ? "disabled" : ""}>Cancel</button>
            <button class="save" type="submit" ${this._submitting ? "disabled" : ""}>${this._submitting ? "Saving…" : "Save Entry"}</button>
          </div>
        </form>
      </div>
    </div>`;
  }

  _escape(value) {
    const element = document.createElement("span");
    element.textContent = String(value ?? "");
    return element.innerHTML;
  }

  _entryRow(entry) {
    const [label, icon] = EVENT_DETAILS[entry.event_type] || EVENT_DETAILS.other;
    const weight = entry.event_type === "weight" && entry.metadata?.value
      ? `${entry.metadata.value} ${entry.metadata.unit || ""}`.trim()
      : "";
    const detail = entry.note || weight;
    return `
      <div class="entry">
        <div class="icon"><ha-icon icon="${icon}"></ha-icon></div>
        <div class="entry-content">
          <div class="entry-main">
            <span class="label">${this._escape(label)}</span>
            <time>${this._escape(this._time(new Date(entry.timestamp)))}</time>
          </div>
          ${detail ? `<div class="detail">${this._escape(detail)}</div>` : ""}
        </div>
      </div>`;
  }

  _content() {
    if (this._loading) {
      return `<div class="state"><ha-circular-progress active></ha-circular-progress><span>Loading care history…</span></div>`;
    }
    if (this._error) {
      return `<div class="state error"><ha-icon icon="mdi:alert-circle-outline"></ha-icon><span>${this._escape(this._error)}</span></div>`;
    }
    if (!this._entries.length) {
      return `<div class="state empty"><ha-icon icon="mdi:notebook-outline"></ha-icon><strong>No care history yet.</strong><span>Feeding, cleaning, and journal entries will appear here.</span></div>`;
    }
    const groups = [];
    for (const entry of this._entries) {
      const date = new Date(entry.timestamp);
      const key = this._dateKey(date);
      let group = groups.at(-1);
      if (!group || group.key !== key) {
        group = { key, date, entries: [] };
        groups.push(group);
      }
      group.entries.push(entry);
    }
    return groups.map((group) => `
      <section>
        <div class="date-heading">${this._escape(this._dateHeading(group.date))}</div>
        ${group.entries.map((entry) => this._entryRow(entry)).join("")}
      </section>`).join("");
  }

  _render() {
    if (!this._config) return;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const viewAll = this._config.show_view_all
      ? `<button id="view-all" type="button">View All</button>`
      : "";
    const add = this._config.show_add
      ? `<button id="add-entry" class="icon-button" type="button" aria-label="Add journal entry"><ha-icon icon="mdi:plus"></ha-icon></button>`
      : "";
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; border-radius: var(--md-sys-shape-corner-extra-large, 24px); background: var(--md-sys-color-surface-container, var(--ha-card-background)); color: var(--primary-text-color); overflow: hidden; }
        header { display:flex; align-items:center; justify-content:space-between; min-height:40px; margin-bottom:8px; }
        .header-actions { display:flex; align-items:center; gap:2px; }
        h2 { margin:0; font-size:18px; line-height:24px; font-weight:600; }
        button { border:0; background:transparent; color:var(--primary-color); font:inherit; font-weight:600; min-height:40px; padding:0 8px; cursor:pointer; border-radius:20px; }
        button:focus-visible, button:hover { background:color-mix(in srgb, var(--primary-color) 10%, transparent); }
        button:disabled { opacity:.55; cursor:default; }
        .icon-button { width:40px; padding:0; display:grid; place-items:center; }
        section + section { margin-top:14px; }
        .date-heading { color:var(--secondary-text-color); font-size:12px; font-weight:600; letter-spacing:.04em; margin:0 0 4px 44px; }
        .entry { display:flex; gap:12px; padding:8px 0; min-width:0; }
        .entry + .entry { border-top:1px solid var(--divider-color); }
        .icon { width:32px; height:32px; flex:0 0 32px; display:grid; place-items:center; border-radius:16px; color:var(--primary-color); background:var(--md-sys-color-primary-container, var(--secondary-background-color)); }
        .icon ha-icon { --mdc-icon-size:18px; }
        .entry-content { flex:1; min-width:0; }
        .entry-main { display:flex; gap:8px; align-items:baseline; justify-content:space-between; }
        .label { font-size:14px; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
        time { color:var(--secondary-text-color); font-size:12px; white-space:nowrap; }
        .detail { color:var(--secondary-text-color); font-size:13px; line-height:18px; margin-top:2px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
        .state { min-height:112px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:8px; color:var(--secondary-text-color); text-align:center; font-size:13px; }
        .state ha-icon { --mdc-icon-size:28px; }
        .error { color:var(--error-color); }
        .scrim { position:fixed; inset:0; z-index:999; display:grid; place-items:center; padding:16px; background:rgba(0,0,0,.5); }
        .dialog { box-sizing:border-box; width:min(440px, 100%); max-height:calc(100vh - 32px); overflow:auto; padding:24px; border-radius:28px; background:var(--md-sys-color-surface-container-high, var(--card-background-color, var(--ha-card-background))); color:var(--primary-text-color); box-shadow:var(--ha-card-box-shadow); }
        h3 { margin:0 0 18px; font-size:22px; line-height:28px; }
        form, label { display:flex; flex-direction:column; }
        form { gap:16px; }
        label { gap:6px; color:var(--secondary-text-color); font-size:13px; font-weight:500; }
        input, select, textarea { box-sizing:border-box; width:100%; min-height:48px; padding:10px 12px; border:1px solid var(--divider-color); border-radius:12px; outline:none; background:var(--md-sys-color-surface-container, var(--secondary-background-color)); color:var(--primary-text-color); font:inherit; }
        textarea { min-height:84px; resize:vertical; }
        input:focus, select:focus, textarea:focus { border-color:var(--primary-color); box-shadow:0 0 0 1px var(--primary-color); }
        .select-with-icon { position:relative; }
        .select-with-icon ha-icon { position:absolute; left:12px; top:12px; z-index:1; color:var(--primary-color); --mdc-icon-size:22px; pointer-events:none; }
        .select-with-icon select { padding-left:44px; }
        #weight-fields { display:grid; grid-template-columns:2fr 1fr; gap:12px; }
        #weight-fields[hidden] { display:none; }
        .helper { margin:0; color:var(--secondary-text-color); font-size:12px; line-height:17px; }
        .form-error { margin:0; color:var(--error-color); font-size:13px; }
        .dialog-actions { display:flex; justify-content:flex-end; gap:8px; margin-top:4px; }
        .dialog-actions button { padding:0 16px; }
        .dialog-actions .save { background:var(--primary-color); color:var(--text-primary-color, white); }
        @media (max-width: 400px) { ha-card { padding:14px; } .date-heading { margin-left:40px; } .entry { gap:8px; } }
      </style>
      <ha-card>
        <header><h2>${this._escape(this._config.title)}</h2><div class="header-actions">${add}${viewAll}</div></header>
        <div>${this._content()}</div>
      </ha-card>${this._addDialog()}`;
    this.shadowRoot.getElementById("add-entry")?.addEventListener("click", () => this._openAddDialog());
    this.shadowRoot.getElementById("view-all")?.addEventListener("click", () => {
      window.location.hash = this._config.view_all_hash;
    });
    this.shadowRoot.getElementById("cancel-entry")?.addEventListener("click", () => this._closeAddDialog());
    this.shadowRoot.getElementById("event-type")?.addEventListener("change", () => this._toggleWeightFields());
    this.shadowRoot.getElementById("entry-form")?.addEventListener("submit", (event) => this._submitEntry(event));
  }
}

customElements.define("lizard-care-history-card", LizardCareHistoryCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "lizard-care-history-card",
  name: "Lizard Care History",
  description: "Recent persistent care and journal activity for one pet.",
});
