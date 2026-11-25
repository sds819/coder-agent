"use strict";

const CLIENT = { "X-Coder-Client": "1" };

/* The strings of the language of the page. The template hands them over. */
function t(key, values = {}) {
  const text = (window.STRINGS || {})[key] || key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in values ? values[name] : match));
}

/* The money of a session. A model without a price spends no money: the cost
   is unknown, not zero. */
function money(cost, priced) {
  return priced === false ? "$?" : `$${(cost || 0).toFixed(4)}`;
}

const MODE_NOTES = {
  default: "mode_default",
  acceptEdits: "mode_acceptEdits",
  plan: "mode_plan",
  readonly: "mode_readonly",
  bypass: "mode_bypass",
};

/* The reasons a turn may end before the agent is done. The others end well. */
const STOP_NOTES = {
  max_turns: "stop_max_turns",
  cost_exceeded: "stop_cost_exceeded",
  token_limit: "stop_token_limit",
  interrupted: "stop_interrupted",
};

/* The dots that say the agent is still working. The server hands them over:
   the same animation as in the terminal. */
const DOT_FRAMES = window.DOT_FRAMES || [".", "..", "...", ".."];

const state = {
  sessionId: null,
  seq: 0,
  stream: null,
  cards: {},
  assistant: null,
  current: null,
  stick: true,
  attention: null,
  mode: "",
  images: [],
  working: null,
  workingTimer: null,
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

async function api(path, options = {}) {
  const opts = Object.assign({}, options, {
    headers: Object.assign({ "X-Coder-Client": "1" }, options.headers || {}),
  });
  if (opts.body && typeof opts.body !== "string") {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(opts.body);
  }
  const response = await fetch(path, opts);
  const text = await response.text();
  if (!response.ok) throw new Error(detailOf(text) || `${response.status}`);
  return text ? JSON.parse(text) : null;
}

/* The reason of a failure: the server says it in `detail`. */
function detailOf(text) {
  try {
    return JSON.parse(text).detail || "";
  } catch (error) {
    return "";
  }
}

// -- the conversation ------------------------------------------------------

function messages() {
  return document.getElementById("messages");
}

/* The items of the turn that is running. The turns before it are folded away. */
function target() {
  if (!state.current) {
    state.current = el("div", "turn");
    messages().appendChild(state.current);
  }
  return state.current;
}

function foldTurn() {
  const done = state.current;
  state.current = null;
  if (!done) return;
  let history = document.getElementById("history");
  if (!history) {
    history = el("details", "history");
    history.id = "history";
    history.appendChild(el("summary", "", t("history")));
    history.appendChild(el("div", "history-body"));
    messages().insertBefore(history, messages().firstChild);
  }
  history.querySelector(".history-body").appendChild(done);
  const count = history.querySelectorAll(".turn").length;
  history.querySelector("summary").textContent = t("earlier_turns", { count });
}

/* The conversation follows the newest content, unless the user scrolled up. */
function scrollToBottom(force) {
  const box = messages();
  if (!box) return;
  /* While a card waits for an answer, the view stays with the card and not
     with the newest content. */
  if (state.attention) {
    keepAttention();
    return;
  }
  if (force || state.stick) box.scrollTop = box.scrollHeight;
}

/* The card that waits for an answer is put in the middle of the view, so that
   the user does not have to look for it. */
function scrollToCard(card) {
  const box = messages();
  if (!box || !card) return;
  const top = card.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
  const wanted = Math.max(0, top - (box.clientHeight - card.offsetHeight) / 2);
  box.scrollTo({ top: wanted, behavior: "smooth" });
}

/* Whether the whole of a node is in the view of the conversation. */
function inView(box, node) {
  const one = node.getBoundingClientRect();
  const other = box.getBoundingClientRect();
  return one.top >= other.top && one.bottom <= other.bottom;
}

/* The card that waits for an answer stays in view while the rest arrives. */
function keepAttention() {
  const box = messages();
  if (!box || !state.attention) return;
  if (!inView(box, state.attention)) scrollToCard(state.attention);
}

/* The button that jumps to the newest content. It shows when the user scrolled up. */
function showLatest() {
  const button = document.getElementById("to-latest");
  if (button) button.hidden = state.stick;
}

function bubble(className, text) {
  const node = el("div", `bubble ${className}`, text || "");
  target().appendChild(node);
  scrollToBottom();
  return node;
}

/* The sign that the agent is still working: the dots grow and shrink. */
function showWorking() {
  if (state.working) return;
  state.working = bubble("working", DOT_FRAMES[0]);
  let step = 0;
  state.workingTimer = setInterval(() => {
    step += 1;
    state.working.textContent = DOT_FRAMES[step % DOT_FRAMES.length];
  }, 400);
}

/* The agent said something: the dots go away. */
function hideWorking() {
  if (!state.working) return;
  clearInterval(state.workingTimer);
  state.workingTimer = null;
  state.working.remove();
  state.working = null;
}

function toolCard(item) {
  const card = el("div", "tool");
  const header = el("header");
  header.appendChild(el("strong", "", item.tool || t("tool")));
  if (item.summary) header.appendChild(el("span", "", item.summary));
  card.appendChild(header);
  const body = el("div", "body", t("running"));
  card.appendChild(body);
  target().appendChild(card);
  scrollToBottom();
  return card;
}

function fillTool(card, item) {
  if (!card) return;
  const body = card.querySelector(".body");
  body.className = `body ${item.is_error ? "bad" : "ok"}`;
  if (item.diff) {
    body.innerHTML = "";
    body.appendChild(diffView(item.diff));
  } else {
    body.textContent = item.content || "";
  }
  /* the output of a tool can be long: the view follows it */
  scrollToBottom();
}

function diffView(diff) {
  const pre = el("pre", "diff");
  for (const line of diff.split("\n")) {
    let cls = "";
    if (line.startsWith("+")) cls = "add";
    else if (line.startsWith("-")) cls = "del";
    else if (line.startsWith("@@") || line.startsWith("---") || line.startsWith("+++")) cls = "meta";
    pre.appendChild(el("div", cls, line));
  }
  return pre;
}

function renderApproval(item) {
  const card = el("div", "tool approval");
  const header = el("header");
  header.appendChild(el("strong", "", t("approval", { tool: item.tool })));
  if (item.reason) header.appendChild(el("span", "", item.reason));
  card.appendChild(header);
  const body = el("div", "body", JSON.stringify(item.params || {}, null, 2));
  card.appendChild(body);
  const buttons = el("div", "buttons");
  for (const [label, decision] of [[t("allow"), "allow"], [t("deny"), "deny"], [t("always"), "always"]]) {
    const button = el("button", decision === "allow" ? "primary" : "", label);
    button.onclick = async () => {
      buttons.innerHTML = "";
      buttons.appendChild(el("span", "", t("answered")));
      card.classList.remove("attention");
      if (state.attention === card) state.attention = null;
      try {
        await api(`/api/approvals/${item.id}`, { method: "POST", body: { decision } });
      } catch (error) {
        buttons.appendChild(el("span", "", t("error", { message: error.message })));
      }
    };
    buttons.appendChild(button);
  }
  card.appendChild(buttons);
  target().appendChild(card);
  state.attention = card;
  card.classList.add("attention");
  scrollToCard(card);
  return card;
}

function renderTodos(todos) {
  const turn = target();
  let panel = turn.querySelector(".todos");
  if (!panel) {
    panel = el("div", "todos");
    turn.appendChild(panel);
  }
  panel.innerHTML = "";
  for (const todo of todos || []) {
    panel.appendChild(el("div", todo.status === "completed" ? "done" : "", todo.content || ""));
  }
  scrollToBottom();
}

function render(item) {
  switch (item.kind) {
    case "user_message": {
      foldTurn();
      const original = item.original || "";
      const node = bubble("user", original || item.text || item.content);
      for (const url of item.images || []) {
        const image = el("img", "attached");
        image.src = url;
        image.alt = "";
        node.appendChild(image);
      }
      if (original && original !== item.content) {
        /* a hook rewrote the prompt: the browser shows what the user typed, and what the model got */
        const note = el("div", "rewritten", t("rewritten", { text: item.content }));
        target().appendChild(note);
        scrollToBottom();
      }
      state.assistant = null;
      break;
    }
    case "assistant_message": {
      const content = item.content || "";
      hideWorking();
      if (state.assistant) {
        /* the answer was streamed into this bubble; the message is the whole of it */
        state.assistant.textContent = content;
        state.assistant = null;
        scrollToBottom();
        break;
      }
      bubble("assistant", content);
      state.assistant = null;
      break;
    }
    case "text_delta": {
      hideWorking();
      if (!state.assistant) {
        state.assistant = bubble("assistant", "");
      }
      state.assistant.textContent += item.content;
      scrollToBottom();
      break;
    }
    case "reasoning_delta":
    case "reasoning":
      break;
    case "tool_call":
      hideWorking();
      state.cards[item.tool_call_id] = toolCard(item);
      break;
    case "tool_result":
      fillTool(state.cards[item.tool_call_id], item);
      break;
    case "approval_request":
      state.cards[`approval-${item.id}`] = renderApproval(item);
      break;
    case "approval_response": {
      const card = state.cards[`approval-${item.id}`];
      if (card) {
        card.classList.remove("attention");
        card.querySelector(".buttons").innerHTML = "";
        card.querySelector(".buttons").appendChild(
          el("span", "", item.timed_out ? t("no_answer") : t("answered_decision", { decision: item.decision }))
        );
      }
      if (state.attention === card) {
        state.attention = null;
        state.stick = true;
        scrollToBottom(true);
        showLatest();
      }
      break;
    }
    case "todos":
      renderTodos(item.todos);
      break;
    case "state":
      /* The agent is thinking: the dots say so, until it says something. */
      if (item.state === "thinking") showWorking();
      else hideWorking();
      break;
    case "command_output":
      bubble("command", item.text);
      break;
    case "review": {
      const card = el("div", "tool review");
      const header = el("header");
      header.appendChild(el("strong", "", t("review")));
      card.appendChild(header);
      const body = el("div", "body");
      body.appendChild(diffView(item.diff || ""));
      if ((item.untracked || []).length) {
        body.appendChild(el("div", "note", t("untracked", { files: item.untracked.join(", ") })));
      }
      card.appendChild(body);
      target().appendChild(card);
      scrollToBottom();
      break;
    }
    case "error":
      bubble("error", item.error);
      break;
    case "compaction":
      bubble("separator", t("compacted", { tokens: item.tokens }));
      break;
    case "recap":
      bubble("separator", t("recapped"));
      break;
    case "side_conversation":
      bubble("separator", t("side_conversation"));
      break;
    case "verify":
      bubble("separator", t("verified", { failed: (item.failed || []).length }));
      break;
    case "reflection":
      /* A model without a price spends no money: the cost is unknown, not zero. */
      bubble(
        "separator",
        item.priced === false
          ? t("settled_unpriced")
          : t("settled", { cost: (item.cost || 0).toFixed(5) }),
      );
      break;
    case "turn_stopped": {
      /* A turn that was cut off says so: the agent went quiet and the user
         has to know why. */
      hideWorking();
      const note = STOP_NOTES[item.stop_reason];
      if (note) bubble("separator", t(note, { calls: item.calls || 0 }));
      break;
    }
    case "reverted":
      bubble("separator", t("rolled_back", { messages: item.messages }));
      break;
    case "session_switched":
      state.sessionId = item.session_id;
      break;
    case "mode_changed":
      refreshStatus();
      break;
    default:
      break;
  }
  if (item.seq) state.seq = Math.max(state.seq, item.seq);
}

// -- the stream ------------------------------------------------------------

function openStream() {
  if (state.stream) state.stream.close();
  if (!state.sessionId) return;
  const stream = new EventSource(`/api/sessions/${state.sessionId}/stream?since=${state.seq}`);
  state.stream = stream;
  stream.onmessage = (event) => {
    const item = JSON.parse(event.data);
    render(item);
    if (item.kind === "turn_end" || item.kind === "command_end") {
      stream.close();
      state.stream = null;
      openStream();
      refreshStatus();
      loadSessions();
      loadChanges();
    }
  };
  stream.onerror = () => {
    stream.close();
    state.stream = null;
    setTimeout(openStream, 1000);
  };
}

// -- the state of the session ----------------------------------------------

async function refreshStatus() {
  if (!state.sessionId) return;
  try {
    const status = await api(`/api/sessions/${state.sessionId}/status`);
    document.getElementById("status").textContent =
      `${status.model} | ${status.tokens}/${status.window} | ${money(status.cost, status.priced)} | ${status.mode} | ${status.state}`;
    const fields = document.getElementById("status-fields");
    if (fields) {
      fields.innerHTML = "";
      for (const [key, value] of Object.entries(status)) {
        fields.appendChild(el("dt", "", t(`field_${key}`)));
        fields.appendChild(el("dd", "", key === "cost" ? money(value, status.priced) : String(value)));
      }
    }
    showMode(status.mode);
  } catch (error) {
    /* the session is gone; the next poll will say so */
  }
}

/* The mode of the session, in the inspector of the chat page. */
function showMode(mode) {
  if (!mode) return;
  state.mode = mode;
  const select = document.getElementById("permission-mode");
  /* The user may be picking a mode: the poll must not pull the box away. */
  if (select && select.value !== mode && document.activeElement !== select) select.value = mode;
  const note = document.getElementById("mode-note");
  if (note) note.textContent = t(MODE_NOTES[mode] || "");
}

async function loadChanges() {
  const box = document.getElementById("changes");
  if (!box || !state.sessionId) return;
  try {
    const data = await api(`/api/sessions/${state.sessionId}/changes`);
    box.innerHTML = "";
    for (const change of data.changes) {
      box.appendChild(el("div", "", change.path));
      if (change.diff) box.appendChild(diffView(change.diff));
    }
  } catch (error) {
    /* no changes yet */
  }
}

// -- the sessions ----------------------------------------------------------

async function loadSessions() {
  const list = document.getElementById("sessions");
  if (!list) return;
  const data = await api("/api/sessions");
  list.innerHTML = "";
  for (const session of data.sessions) {
    /* The list shows the first question of the session. The counts are in the
       tooltip: the cost of a model that has no price is not worth showing. */
    const item = el("li", "", session.title);
    item.title = `${session.id}  ${session.turns}t  ${money(session.cost, session.priced)}  ${session.cwd}`;
    if (session.id === state.sessionId) item.classList.add("active");
    item.onclick = () => openSession(session.id);
    list.appendChild(item);
  }
}

async function openSession(id) {
  state.sessionId = id;
  state.seq = 0;
  state.cards = {};
  state.assistant = null;
  state.current = null;
  state.attention = null;
  state.stick = true;
  messages().innerHTML = "";
  const data = await api(`/api/sessions/${id}/items`);
  for (const item of data.items) render(item);
  scrollToBottom(true);
  openStream();
  refreshStatus();
  loadSessions();
  loadChanges();
}

// -- the files -------------------------------------------------------------

async function listFiles(path) {
  const list = document.getElementById("files");
  const data = await api(`/api/files?path=${encodeURIComponent(path)}&depth=1`);
  list.innerHTML = "";
  for (const entry of data.entries) {
    const item = el("li", entry.is_dir ? "dir" : "", entry.name + (entry.is_dir ? "/" : ""));
    item.onclick = () => {
      if (entry.is_dir) {
        listFiles(entry.path);
      } else {
        showFile(entry.path);
      }
    };
    list.appendChild(item);
  }
  const input = document.getElementById("file-path");
  /* The panel shows where it is: the directory that was listed. */
  if (input && data.path) input.value = data.path;
}

async function showFile(path) {
  const view = document.getElementById("file-view");
  try {
    const file = await api(`/api/file?path=${encodeURIComponent(path)}`);
    view.textContent = file.content;
  } catch (error) {
    view.textContent = t("error", { message: error.message });
  }
  try {
    const data = await api(`/api/diff?path=${encodeURIComponent(path)}`);
    if (data.diff) view.textContent += `\n\n--- diff ---\n${data.diff}`;
  } catch (error) {
    /* no diff */
  }
}

// -- the commands ----------------------------------------------------------

async function loadCommands() {
  const select = document.getElementById("command-list");
  if (!select) return;
  const data = await api("/api/commands");
  select.innerHTML = "";
  for (const command of data.commands) {
    const option = el("option", "", command.usage ? `/${command.name}  ${command.usage}` : `/${command.name}`);
    option.value = `/${command.name}`;
    option.title = command.usage ? `${command.description} — ${command.usage}` : command.description;
    select.appendChild(option);
  }
}

/* The sub agents of the project, with the turns they may really make. */
async function loadAgents() {
  const box = document.getElementById("agents");
  if (!box) return;
  try {
    const data = await api("/api/agents");
    box.innerHTML = "";
    for (const agent of data.agents) {
      const item = el("div", "agent");
      const head = el("div", "agent-head");
      head.appendChild(el("strong", "", agent.name));
      head.appendChild(el("span", "", agent.purpose));
      item.appendChild(head);
      item.appendChild(el("div", "agent-turns", agent.turns ? t("turns", { count: agent.turns }) : t("no_limit")));
      item.appendChild(el("div", "agent-tools", agent.tools.join(", ")));
      if (agent.description) item.appendChild(el("div", "agent-description", agent.description));
      box.appendChild(item);
    }
    if (data.ceiling) box.appendChild(el("p", "note", t("turn_ceiling", { count: data.ceiling })));
  } catch (error) {
    /* there are no sub agents to show */
  }
}

// -- the language -----------------------------------------------------------

const LANGUAGE_KEY = "coder_lang";

/* The text of a language, without leaving the page: the page of that language
   is fetched and put in place, and the strings of the browser are replaced. */
async function switchLanguage(code) {
  const data = await api(`/api/i18n/${encodeURIComponent(code)}`);
  window.STRINGS = data.strings;
  const answer = await fetch(`${location.pathname}?lang=${encodeURIComponent(code)}`);
  const doc = new DOMParser().parseFromString(await answer.text(), "text/html");
  document.title = doc.title;
  document.documentElement.lang = doc.documentElement.lang;
  const fresh = doc.body.cloneNode(true);
  fresh.querySelectorAll("script").forEach((node) => node.remove());
  document.body.replaceChildren(...fresh.childNodes);
  /* The choice is kept in the browser and in the cookie: the server renders the
     right language the next time, and the browser finds its choice again. */
  document.cookie = `${LANGUAGE_KEY}=${code}; path=/; max-age=31536000; samesite=lax`;
  localStorage.setItem(LANGUAGE_KEY, code);
}

/* The values of the form, so that a change of the language does not throw
   away what was typed. */
function formValues() {
  const values = {};
  for (const node of document.querySelectorAll("input, textarea, select")) {
    if (node.type !== "password" && node.id) values[node.id] = node.value;
  }
  return values;
}

function restoreForm(values) {
  for (const [id, value] of Object.entries(values)) {
    const node = document.getElementById(id);
    if (node) node.value = value;
  }
}

/* The page is drawn again in the new language: the conversation is read from
   the log, the settings are read from the configuration. The values of the
   form are the ones of before the switch, so nothing that was typed is lost. */
async function relocalize(values = {}) {
  if (document.getElementById("messages")) {
    wire();
    await loadCommands().catch(() => {});
    await loadAgents().catch(() => {});
    if (state.sessionId) await openSession(state.sessionId);
    return;
  }
  if (!document.getElementById("model-form")) {
    if (document.getElementById("skills-page")) {
      await startSkills();
      restoreForm(values);
    }
    return;
  }
  await startSettings();
  restoreForm(values);
}

async function chooseLanguage(code) {
  try {
    const values = formValues();
    await switchLanguage(code);
    await relocalize(values);
  } catch (error) {
    /* the page stays in the language it has */
  }
}

// -- the skills -------------------------------------------------------------

const skillState = { staged: null, force: false };
const listState = { installed: { page: 0 }, builtin: { page: 0 } };
const PAGE = 10;
/* How many skills a list shows at a time. */

function skillButton(label, action) {
  const button = el("button", "", label);
  button.onclick = action;
  return button;
}

async function loadSkills() {
  if (!document.getElementById("skills-installed")) return;
  const data = await api("/api/skills");
  siteState.installed = new Set(data.skills.map((skill) => skill.name));
  showInstalled(data.skills || []);
  showBuiltin(data.builtin || []);
  showRegistries(data.registries || []);
  if (siteState.site) renderSite();
}

/* The installed skills, ten at a time. */
function showInstalled(skills) {
  const box = document.getElementById("skills-installed");
  box.innerHTML = "";
  if (!skills.length) {
    box.appendChild(el("div", "note", t("skills_none")));
    return;
  }
  const state = listState.installed;
  const pages = Math.max(1, Math.ceil(skills.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  const grid = el("div", "skill-grid");
  for (const skill of skills.slice(state.page * PAGE, (state.page + 1) * PAGE)) {
    const row = el("div", "skill");
    const head = el("div", "skill-head");
    head.appendChild(el("strong", "", skill.name));
    head.appendChild(el("span", "", skill.description));
    row.appendChild(head);
    const meta = el("div", "skill-meta");
    if (skill.source_text) meta.appendChild(el("div", "", t("skills_from", { source: skill.source_text })));
    meta.appendChild(el("div", "", t("skills_files", { count: skill.files })));
    if (skill.sha256) meta.appendChild(el("div", "", `${t("skills_sha256")} ${skill.sha256}`));
    if (!skill.managed) meta.appendChild(el("div", "", t("skills_yours")));
    row.appendChild(meta);
    const buttons = el("div", "row");
    buttons.appendChild(skillButton(t("skills_details"), () => showSkill(skill.name)));
    if (skill.managed) {
      buttons.appendChild(skillButton(t("skills_update"), () => updateSkill(skill.name)));
      buttons.appendChild(skillButton(t("skills_uninstall"), () => removeSkill(skill.name)));
    }
    row.appendChild(buttons);
    grid.appendChild(row);
  }
  box.appendChild(grid);
  box.appendChild(makePager(state, pages, () => showInstalled(skills), "skills"));
}

/* The skills that come with the agent. They are not installed, so there is
   nothing to update and nothing to remove. */
function showBuiltin(skills) {
  const box = document.getElementById("skills-builtin");
  if (!box) return;
  box.innerHTML = "";
  const state = listState.builtin;
  const pages = Math.max(1, Math.ceil(skills.length / PAGE));
  state.page = Math.min(state.page, pages - 1);
  const grid = el("div", "skill-grid");
  for (const skill of skills.slice(state.page * PAGE, (state.page + 1) * PAGE)) {
    const row = el("div", "skill");
    const head = el("div", "skill-head");
    head.appendChild(el("strong", "", skill.name));
    head.appendChild(el("span", "", skill.description));
    row.appendChild(head);
    const meta = el("div", "skill-meta");
    meta.appendChild(el("div", "", t("skills_files", { count: skill.files })));
    row.appendChild(meta);
    const buttons = el("div", "row");
    buttons.appendChild(skillButton(t("skills_details"), () => showSkill(skill.name)));
    row.appendChild(buttons);
    grid.appendChild(row);
  }
  box.appendChild(grid);
  box.appendChild(makePager(state, pages, () => showBuiltin(skills), "skills"));
}

function showRegistries(urls) {
  const box = document.getElementById("skills-registries");
  box.innerHTML = "";
  if (!urls.length) return;
  box.appendChild(el("h2", "", t("skills_registries")));
  const row = el("div", "row");
  for (const url of urls) row.appendChild(skillButton(url, () => browseRegistry(url)));
  box.appendChild(row);
}

async function browseRegistry(url) {
  const box = document.getElementById("skills-registries");
  const message = document.getElementById("skills-message");
  try {
    const data = await api("/api/skills/registry", { method: "POST", body: { url } });
    const old = box.querySelector(".registry-entries");
    if (old) old.remove();
    const entries = el("div", "registry-entries");
    if (!data.skills.length) entries.appendChild(el("div", "note", t("skills_none")));
    for (const skill of data.skills) {
      const row = el("div", "skill");
      const head = el("div", "skill-head");
      head.appendChild(el("strong", "", skill.name));
      head.appendChild(el("span", "", skill.description));
      row.appendChild(head);
      row.appendChild(skillButton(t("skills_use"), () => {
        document.getElementById("skill-source").value = skill.source_text;
      }));
      entries.appendChild(row);
    }
    box.appendChild(entries);
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

/* What the user is shown before the skill is installed: the whole of the
   SKILL.md, the files that come with it and the warnings about them. */
function openPreview(preview, force) {
  skillState.staged = preview;
  skillState.force = !!force;
  document.getElementById("preview-name").textContent = preview.name;
  const parts = [preview.source_text, t("skills_files", { count: (preview.files || []).length })];
  if (preview.sha256) parts.push(`${t("skills_sha256")} ${preview.sha256}`);
  document.getElementById("preview-meta").textContent = parts.filter(Boolean).join(" · ");
  const warnings = document.getElementById("preview-warnings");
  warnings.innerHTML = "";
  for (const warning of preview.warnings || []) warnings.appendChild(el("div", "warning", `⚠ ${warning}`));
  document.getElementById("preview-body").textContent = preview.body;
  const files = document.getElementById("preview-files");
  files.innerHTML = "";
  for (const file of preview.files || []) files.appendChild(el("div", "", `${file.path} (${file.size} B)`));
  const install = document.getElementById("preview-install");
  install.style.display = preview.stage_id ? "inline-block" : "none";
  const dialog = document.getElementById("skills-preview");
  if (!dialog.open) dialog.showModal();
}

async function showSkill(name) {
  const message = document.getElementById("skills-message");
  try {
    openPreview(await api(`/api/skills/${encodeURIComponent(name)}`), false);
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

async function updateSkill(name) {
  const message = document.getElementById("skills-message");
  message.textContent = t("skills_downloading");
  try {
    const data = await api("/api/skills/update", { method: "POST", body: { name } });
    if (data.up_to_date) {
      message.textContent = t("skills_up_to_date", { name });
      return;
    }
    message.textContent = "";
    openPreview(data.preview, true);
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

async function removeSkill(name) {
  if (!window.confirm(t("skills_uninstall_confirm", { name }))) return;
  const message = document.getElementById("skills-message");
  try {
    await api(`/api/skills/${encodeURIComponent(name)}`, { method: "DELETE" });
    message.textContent = t("skills_removed", { name });
    await loadSkills();
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

async function installStaged() {
  const message = document.getElementById("skills-message");
  if (!skillState.staged || !skillState.staged.stage_id) return;
  message.textContent = t("skills_downloading");
  try {
    await api("/api/skills/install", {
      method: "POST",
      body: { stage_id: skillState.staged.stage_id, force: skillState.force },
    });
    document.getElementById("skills-preview").close();
    message.textContent = t("skills_installed_ok", { name: skillState.staged.name });
    await loadSkills();
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

async function startSkills() {
  const message = document.getElementById("skills-message");
  const download = document.getElementById("skills-download");
  document.getElementById("skills-form").onsubmit = async (event) => {
    event.preventDefault();
    const source = document.getElementById("skill-source").value.trim();
    if (!source) return;
    message.textContent = t("skills_downloading");
    download.disabled = true;
    try {
      const preview = await api("/api/skills/preview", { method: "POST", body: { source } });
      message.textContent = "";
      openPreview(preview, false);
    } catch (error) {
      message.textContent = t("error", { message: error.message });
    } finally {
      download.disabled = false;
    }
  };
  document.getElementById("preview-install").onclick = installStaged;
  document.getElementById("preview-cancel").onclick = () => document.getElementById("skills-preview").close();
  document.getElementById("preview-close").onclick = () => document.getElementById("skills-preview").close();
  await loadSkills();
  await loadSites();
}

// -- the sites of skills ----------------------------------------------------

const siteState = { site: null, skills: [], page: 0, size: 6, installed: new Set() };

const DESCRIPTION = 50;
/* How much of a description a card shows. The rest waits for the mouse. */

/* The sites are the tabs of the page: one tab for each repository, and the
   skills of the repository under it. */
async function loadSites() {
  const box = document.getElementById("skills-sites");
  if (!box) return;
  try {
    const data = await api("/api/skills/sites");
    box.innerHTML = "";
    for (const site of data.sites || []) {
      const tab = el("button", "tab", siteName(site));
      tab.dataset.site = site.id;
      tab.style.setProperty("--site-accent", site.accent || "#6aa9ff");
      tab.onclick = () => showSite(site);
      box.appendChild(tab);
    }
    if ((data.sites || []).length) await showSite(data.sites[0]);
  } catch (error) {
    box.appendChild(el("div", "note", t("error", { message: error.message })));
  }
}

/* The name of a site in the language of the visitor. */
function siteName(site) {
  const name = t(`skills_site_${site.id}_name`);
  return name === `skills_site_${site.id}_name` ? site.repo : name;
}

async function showSite(site, refresh = false) {
  const panel = document.getElementById("skills-site-panel");
  siteState.site = site;
  siteState.page = 0;
  for (const tab of document.querySelectorAll("#skills-sites .tab")) {
    tab.classList.toggle("active", tab.dataset.site === site.id);
  }
  panel.innerHTML = "";
  panel.style.setProperty("--site-accent", site.accent || "#6aa9ff");
  panel.appendChild(el("div", "note", t("skills_site_loading")));
  try {
    const data = await api(`/api/skills/sites/${encodeURIComponent(site.id)}${refresh ? "?refresh=true" : ""}`);
    siteState.skills = data.skills || [];
    siteState.size = data.page_size || 6;
    renderSite();
  } catch (error) {
    panel.innerHTML = "";
    panel.appendChild(el("div", "note", t("error", { message: error.message })));
  }
}

function renderSite() {
  const panel = document.getElementById("skills-site-panel");
  const site = siteState.site;
  panel.innerHTML = "";

  const head = el("div", "site-head");
  const title = el("div", "site-title");
  title.appendChild(el("span", "site-dot"));
  title.appendChild(el("span", "site-name", siteName(site)));
  const link = el("a", "site-repo", site.repo);
  link.href = site.url;
  link.target = "_blank";
  link.rel = "noreferrer";
  title.appendChild(link);
  head.appendChild(title);
  head.appendChild(el("span", "badge", t("skills_site_count", { count: siteState.skills.length })));
  const sync = skillButton(t("skills_site_sync"), syncSite);
  sync.classList.add("ghost");
  head.appendChild(sync);
  panel.appendChild(head);

  panel.appendChild(el("div", "note", t(`skills_site_${site.id}`)));

  const grid = el("div", "site-cards");
  const items = siteState.skills.slice(siteState.page * siteState.size, (siteState.page + 1) * siteState.size);
  if (!items.length) grid.appendChild(el("div", "note", t("skills_site_empty")));
  for (const skill of items) grid.appendChild(siteCard(skill));
  panel.appendChild(grid);

  const pages = Math.max(1, Math.ceil(siteState.skills.length / siteState.size));
  if (pages > 1) panel.appendChild(sitePager(pages));
}

function siteCard(skill) {
  const card = el("div", "site-card");
  card.appendChild(el("div", "site-avatar", (skill.name || "?").slice(0, 1).toUpperCase()));
  const body = el("div", "site-card-body");
  const title = el("div", "site-card-title");
  title.appendChild(el("strong", "", skill.name));
  if (siteState.installed.has(skill.name)) title.appendChild(el("span", "badge ok", t("skills_site_installed")));
  body.appendChild(title);
  const description = el("div", "site-card-desc", shorten(skill.description || ""));
  description.title = skill.description || "";
  body.appendChild(description);
  body.appendChild(el("code", "site-card-path", skill.path));
  card.appendChild(body);
  const actions = el("div", "site-card-actions");
  actions.appendChild(skillButton(t("skills_site_download"), () => downloadSkill(skill)));
  card.appendChild(actions);
  return card;
}

/* A description that fits in a card. The whole of it waits for the mouse:
   the card carries it as its title. */
function shorten(text) {
  return text.length > DESCRIPTION ? `${text.slice(0, DESCRIPTION)}…` : text;
}

function sitePager(pages) {
  return makePager(siteState, pages, renderSite, "skills_site");
}

/* The pages of a list of skills: the one on the screen, the ones around it
   and the first and the last. A list may hold hundreds of skills: a button
   for every page would be a wall of numbers. */
function makePager(state, pages, redraw, keys) {
  const box = el("div", "pager");
  const prev = skillButton(t(`${keys}_prev`), () => {
    state.page = Math.max(0, state.page - 1);
    redraw();
  });
  prev.disabled = state.page <= 0;
  box.appendChild(prev);
  let last = -1;
  for (const index of pageWindow(pages, state.page)) {
    if (last >= 0 && index > last + 1) box.appendChild(el("span", "note", "…"));
    const button = skillButton(String(index + 1), () => {
      state.page = index;
      redraw();
    });
    if (index === state.page) button.classList.add("active");
    box.appendChild(button);
    last = index;
  }
  const next = skillButton(t(`${keys}_next`), () => {
    state.page = Math.min(pages - 1, state.page + 1);
    redraw();
  });
  next.disabled = state.page >= pages - 1;
  box.appendChild(next);
  box.appendChild(el("span", "note", t(`${keys}_page`, { page: state.page + 1, count: pages })));
  return box;
}

function pageWindow(pages, page) {
  const shown = new Set([0, pages - 1]);
  for (let index = page - 2; index <= page + 2; index++) {
    if (index >= 0 && index < pages) shown.add(index);
  }
  return [...shown].sort((a, b) => a - b);
}

async function syncSite() {
  const message = document.getElementById("skills-message");
  message.textContent = t("skills_site_syncing");
  await showSite(siteState.site, true);
  message.textContent = "";
}

async function downloadSkill(skill) {
  const message = document.getElementById("skills-message");
  message.textContent = t("skills_downloading");
  try {
    const preview = await api("/api/skills/preview", { method: "POST", body: { source: skill.source_text } });
    message.textContent = "";
    openPreview(preview, false);
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

async function downloadSkill(skill) {
  const message = document.getElementById("skills-message");
  message.textContent = t("skills_downloading");
  try {
    const preview = await api("/api/skills/preview", { method: "POST", body: { source: skill.source_text } });
    message.textContent = "";
    openPreview(preview, false);
  } catch (error) {
    message.textContent = t("error", { message: error.message });
  }
}

// -- the images ------------------------------------------------------------

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
/* The types the server takes. The browser and the server have to agree. */
const IMAGE_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp"];

/* An image that goes with the next message. The model takes a data url. */
function addImage(file) {
  if (!IMAGE_TYPES.includes(file.type)) {
    bubble("error", t("image_bad_type"));
    return;
  }
  if (file.size > MAX_IMAGE_BYTES) {
    bubble("error", t("image_too_big"));
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    state.images.push(String(reader.result));
    showImages();
  };
  reader.readAsDataURL(file);
}

/* The images that are waiting to be sent. */
function showImages() {
  const box = document.getElementById("attachments");
  if (!box) return;
  box.innerHTML = "";
  state.images.forEach((url, index) => {
    const item = el("div", "attachment");
    const image = el("img");
    image.src = url;
    image.alt = "";
    item.appendChild(image);
    const remove = el("button", "remove", t("remove_image"));
    remove.onclick = () => {
      state.images.splice(index, 1);
      showImages();
    };
    item.appendChild(remove);
    box.appendChild(item);
  });
}

// -- the wiring ------------------------------------------------------------

function wire() {
  const box = messages();
  if (box) {
    box.addEventListener("scroll", () => {
      const gap = box.scrollHeight - box.scrollTop - box.clientHeight;
      state.stick = gap < 40;
      showLatest();
    });
  }

  const toLatest = document.getElementById("to-latest");
  if (toLatest) {
    toLatest.onclick = () => {
      state.stick = true;
      scrollToBottom(true);
      showLatest();
    };
  }

  const newSession = document.getElementById("new-session");
  if (newSession) {
    newSession.onclick = async () => {
      const data = await api("/api/sessions", { method: "POST" });
      await openSession(data.id);
    };
  }

  const input = document.getElementById("input");
  const composer = document.getElementById("composer");
  if (composer) {
    composer.onsubmit = async (event) => {
      event.preventDefault();
      const text = input.value.trim();
      const images = state.images.slice();
      if ((!text && !images.length) || !state.sessionId) return;
      input.value = "";
      state.images = [];
      showImages();
      try {
        await api(`/api/sessions/${state.sessionId}/messages`, { method: "POST", body: { text, images } });
      } catch (error) {
        bubble("error", error.message);
      }
    };
  }

  const attach = document.getElementById("attach");
  const attachButton = document.getElementById("attach-image");
  if (attach && attachButton) {
    attachButton.onclick = () => attach.click();
    attach.onchange = () => {
      for (const file of attach.files || []) addImage(file);
      attach.value = "";
    };
  }

  if (input) {
    input.addEventListener("paste", (event) => {
      /* The items carry what was copied: a picture of a web page comes as an
         item of its own, not as a file. */
      const items = Array.from((event.clipboardData || {}).items || []).filter((item) => item.kind === "file");
      const files = items.map((item) => item.getAsFile()).filter(Boolean);
      if (!files.length) return;
      event.preventDefault();
      files.forEach(addImage);
    });
  }

  const runCommand = document.getElementById("run-command");
  if (runCommand) {
    runCommand.onclick = () => {
      const select = document.getElementById("command-list");
      input.value = select.value;
      document.getElementById("composer").requestSubmit();
    };
  }

  const review = document.getElementById("review");
  if (review) {
    review.onclick = async () => {
      if (!state.sessionId) return;
      try {
        await api(`/api/sessions/${state.sessionId}/review`, { method: "POST" });
      } catch (error) {
        bubble("error", error.message);
      }
    };
  }

  const interrupt = document.getElementById("interrupt");
  if (interrupt) {
    interrupt.onclick = async () => {
      if (state.sessionId) await api(`/api/sessions/${state.sessionId}/interrupt`, { method: "POST" });
    };
  }

  const listButton = document.getElementById("list-files");
  if (listButton) {
    listButton.onclick = () => {
      const path = document.getElementById("file-path").value || ".";
      listFiles(path).catch((error) => bubble("error", error.message));
    };
  }

  const modeSelect = document.getElementById("permission-mode");
  if (modeSelect) {
    modeSelect.onchange = async () => {
      const mode = modeSelect.value;
      const previous = state.mode;
      if (!state.sessionId) {
        modeSelect.value = previous || "default";
        return;
      }
      if (mode === "bypass" && !window.confirm(t("bypass_confirm"))) {
        modeSelect.value = previous || "default";
        return;
      }
      try {
        await api(`/api/sessions/${state.sessionId}/mode`, {
          method: "POST",
          body: { mode, confirm: mode === "bypass" },
        });
        showMode(mode);
      } catch (error) {
        modeSelect.value = previous || "default";
        bubble("error", error.message);
      }
    };
  }
}

// -- the settings ----------------------------------------------------------

function parseKeyValues(text) {
  const trimmed = (text || "").trim();
  if (!trimmed) return {};
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object") return parsed;
  } catch (error) {
    /* not json, so it is a list of `key: value` lines */
  }
  const result = {};
  for (const line of trimmed.split("\n")) {
    const index = line.indexOf(":");
    if (index < 0) continue;
    const key = line.slice(0, index).trim();
    const value = line.slice(index + 1).trim();
    if (!key) continue;
    try {
      result[key] = JSON.parse(value);
    } catch (error) {
      result[key] = value;
    }
  }
  return result;
}

function formatKeyValues(object) {
  return Object.entries(object || {})
    .map(([key, value]) => `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`)
    .join("\n");
}

function splitLines(text) {
  return (text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function renderTest(answer, target = "model-test") {
  // What the test found out: the settings, the file, the call and the tools.
  const box = document.getElementById(target);
  box.innerHTML = "";
  const resolved = answer.resolved || {};
  const file = answer.file || {};
  const tools = answer.tools || {};
  let fileText;
  if (file.ok) {
    fileText = `${file.path || "none"}${file.aliases && file.aliases.length ? ` — ${file.aliases.join(", ")}` : ""}`;
  } else if ((file.error || "").includes("not one of the aliases")) {
    fileText = `${file.path || "none"} — ${t("not_an_alias")}`;
  } else {
    fileText = `${file.path || "none"} — ${file.error}`;
  }
  const rows = [
    [t("row_model"), `${resolved.model_name || "?"}${resolved.alias ? ` (alias ${resolved.alias})` : ""}`],
    [t("row_api_base"), resolved.api_base || t("not_set")],
    [t("row_api_key"), resolved.api_key_set ? `set (${resolved.api_key_hint})` : t("not_set")],
    [t("row_aliases"), fileText],
    [t("row_tools"), tools.ok ? t("tools_ok") : tools.error || t("not_tried")],
  ];
  const list = el("dl");
  for (const [key, value] of rows) {
    list.appendChild(el("dt", "", key));
    list.appendChild(el("dd", "", value));
  }
  box.appendChild(list);
}

function wireApiKey(input, placeholder, note) {
  // A click shows the key of the settings, a second click hides it again.
  let revealed = false;
  input.onclick = async () => {
    if (revealed) {
      revealed = false;
      input.value = "";
      input.type = "password";
      input.placeholder = placeholder();
      return;
    }
    if (input.value.trim()) return;
    // A key that is being typed is left alone.
    try {
      const answer = await api("/api/config/model/key");
      if (!answer.api_key) {
        if (note) note.textContent = t("no_key");
        return;
      }
      input.value = answer.api_key;
      input.type = "text";
      input.select();
      revealed = true;
    } catch (error) {
      if (note) note.textContent = t("error", { message: error.message });
    }
  };
}

async function startSettings() {
  const data = await api("/api/config");
  const model = data.model;
  const permissions = data.permissions || {};
  document.getElementById("config-path").textContent = data.user_config_path;
  document.getElementById("model-name").value = model.model_name || "";
  document.getElementById("litellm-config").value = model.litellm_config || "";
  document.getElementById("api-base").value = model.api_base || "";
  const aliasBase = document.getElementById("alias-api_base");
  if (aliasBase) {
    aliasBase.textContent = model.alias_api_base ? t("alias_base", { base: model.alias_api_base }) : "";
  }
  document.getElementById("max-retries").value = model.max_retries;
  document.getElementById("set-cache-control").value = model.set_cache_control || "";
  document.getElementById("reasoning-effort").value = model.reasoning_effort || "";
  document.getElementById("verbosity").value = model.verbosity || "";
  document.getElementById("review-model").value = model.review_model || "";
  document.getElementById("routing").value = formatKeyValues(model.routing);
  document.getElementById("routing-rules").value = (model.routing_rules || [])
    .map((rule) => `${rule.when}: ${rule.purpose}`)
    .join("\n");
  document.getElementById("model-kwargs").value = formatKeyValues(model.model_kwargs);

  document.getElementById("permission-mode").value = permissions.mode || "default";
  document.getElementById("deny-paths").value = (permissions.deny_paths || []).join("\n");
  document.getElementById("include-dirs").value = (permissions.include_dirs || []).join("\n");
  document.getElementById("network").value = permissions.network || "allow";
  const permissionSource = document.getElementById("source-mode");
  if (permissionSource) {
    permissionSource.textContent = t("from", { source: (permissions.source || {}).mode || "defaults" });
  }
  const networkSource = document.getElementById("source-network");
  if (networkSource) {
    networkSource.textContent = t("from", { source: (permissions.source || {}).network || "defaults" });
  }
  const serverNote = document.getElementById("server-mode-note");
  if (serverNote) {
    serverNote.textContent = permissions.server_mode
      ? t("server_mode", { mode: permissions.server_mode })
      : "";
  }

  for (const [field, source] of Object.entries(data.sources || {})) {
    const node = document.getElementById(`source-${field}`);
    if (node) node.textContent = t("from", { source });
  }

  const body = document.querySelector("#layers tbody");
  if (body) {
    body.innerHTML = "";
    for (const layer of data.layers || []) {
      const row = el("tr");
      row.appendChild(el("td", "", layer.layer));
      const cell = el("td");
      cell.appendChild(el("pre", "", JSON.stringify(layer.model, null, 2)));
      row.appendChild(cell);
      body.appendChild(row);
    }
  }

  const keyInput = document.getElementById("api-key");
  keyInput.type = "password";
  keyInput.value = "";
  const keyPlaceholder = () =>
    model.api_key_set ? t("key_set", { hint: model.api_key_hint }) : t("key_not_set");
  keyInput.placeholder = keyPlaceholder();

  const message = document.getElementById("config-message");
  const payload = () => {
    const form = {
      model_name: document.getElementById("model-name").value.trim(),
      litellm_config: document.getElementById("litellm-config").value.trim(),
      api_base: document.getElementById("api-base").value.trim(),
      max_retries: Number(document.getElementById("max-retries").value || 0),
      set_cache_control: document.getElementById("set-cache-control").value,
      reasoning_effort: document.getElementById("reasoning-effort").value,
      verbosity: document.getElementById("verbosity").value,
      review_model: document.getElementById("review-model").value.trim(),
      routing: parseKeyValues(document.getElementById("routing").value),
      routing_rules: Object.entries(parseKeyValues(document.getElementById("routing-rules").value)).map(
        ([when, purpose]) => ({ when, purpose })
      ),
      model_kwargs: parseKeyValues(document.getElementById("model-kwargs").value),
    };
    const key = keyInput.value.trim();
    if (key) form.api_key = key;
    return form;
  };

  wireApiKey(keyInput, keyPlaceholder, message);

  document.getElementById("model-form").onsubmit = async (event) => {
    event.preventDefault();
    try {
      const answer = await api("/api/config/model", { method: "PUT", body: payload() });
      message.textContent = t("saved", { path: answer.path });
      document.getElementById("api-key").value = "";
      startSettings();
    } catch (error) {
      message.textContent = t("error", { message: error.message });
    }
  };

  document.getElementById("test-connection").onclick = async () => {
    message.textContent = t("trying");
    try {
      const answer = await api("/api/config/model/test", { method: "POST", body: payload() });
      message.textContent = answer.ok
        ? t("ok_ms", { ms: answer.latency_ms })
        : t("error", { message: answer.error });
      renderTest(answer);
    } catch (error) {
      message.textContent = t("error", { message: error.message });
    }
  };

  const testEndpoint = document.getElementById("test-endpoint");
  const testKey = document.getElementById("test-api-key");
  const testName = document.getElementById("test-model-name");
  const testNote = document.getElementById("test-message");
  testEndpoint.value = model.api_base || "";
  testName.value = model.model_name || "";
  testKey.type = "password";
  testKey.value = "";
  wireApiKey(testKey, () => t("key_of_endpoint"), testNote);

  document.getElementById("test-form").onsubmit = async (event) => {
    event.preventDefault();
    const body = { model_name: testName.value.trim() };
    if (body.model_name && !body.model_name.includes("/")) {
      // The endpoint is an OpenAI compatible one, so that is the provider.
      body.model_name = `openai/${body.model_name}`;
    }
    const endpoint = testEndpoint.value.trim();
    if (endpoint) body.api_base = endpoint;
    const key = testKey.value.trim();
    if (key) body.api_key = key;
    testNote.textContent = t("trying");
    try {
      const answer = await api("/api/config/model/test", { method: "POST", body });
      testNote.textContent = answer.ok ? t("ok_ms", { ms: answer.latency_ms }) : t("error", { message: answer.error });
      renderTest(answer, "test-result");
    } catch (error) {
      testNote.textContent = t("error", { message: error.message });
    }
  };

  document.getElementById("permissions-form").onsubmit = async (event) => {
    event.preventDefault();
    const note = document.getElementById("permissions-message");
    try {
      const answer = await api("/api/config/permissions", {
        method: "PUT",
        body: {
          mode: document.getElementById("permission-mode").value,
          deny_paths: splitLines(document.getElementById("deny-paths").value),
          include_dirs: splitLines(document.getElementById("include-dirs").value),
          network: document.getElementById("network").value,
        },
      });
      note.textContent = t("saved", { path: answer.path });
      startSettings();
    } catch (error) {
      note.textContent = t("error", { message: error.message });
    }
  };
}

async function start() {
  wire();
  await loadCommands().catch(() => {});
  await loadAgents().catch(() => {});
  await loadSessions().catch(() => {});
  const data = await api("/api/sessions", { method: "POST" });
  await openSession(data.id);
  setInterval(refreshStatus, 2000);
}

document.addEventListener("DOMContentLoaded", async () => {
  /* The language of the visitor is remembered in the browser: it wins over the
     one the server rendered, so a refresh does not change it back. */
  const saved = localStorage.getItem(LANGUAGE_KEY);
  if (saved && saved !== document.documentElement.lang) {
    await switchLanguage(saved).catch(() => {});
  }
  if (document.getElementById("messages")) start();
  if (document.getElementById("model-form")) startSettings();
  if (document.getElementById("skills-page")) startSkills();
});
