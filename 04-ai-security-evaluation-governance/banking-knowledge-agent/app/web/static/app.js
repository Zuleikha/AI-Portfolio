// Banking Knowledge Agent - Stage 9 web page.
//
// Displays only what the API returns. Every piece of text is inserted with
// textContent: answer and tool text is untrusted and must never be parsed as
// markup (guide §20.31). The session id is kept in memory and sent in the JSON
// body, never in a URL (guide §20.30).
//
// Stage 13 (guide §20.50): an optional API key, typed into a password box, is
// sent as the X-API-Key header on every /api call. It is kept in
// sessionStorage (this tab only, gone when the tab closes); storage may be
// blocked, so every access is guarded and the page works without it.
"use strict";

const el = (id) => document.getElementById(id);
const API_KEY_HEADER = "X-API-Key";
const KEY_STORAGE = "bka.apiKey";
let sessionId = null;

function loadKey() {
  try {
    return window.sessionStorage.getItem(KEY_STORAGE) || "";
  } catch {
    return "";
  }
}

function saveKey(value) {
  try {
    if (value) window.sessionStorage.setItem(KEY_STORAGE, value);
    else window.sessionStorage.removeItem(KEY_STORAGE);
  } catch {
    // Storage blocked: the key still works for as long as the page is open.
  }
}

function requestHeaders() {
  const headers = { "Content-Type": "application/json" };
  const key = el("api-key").value.trim();
  if (key) headers[API_KEY_HEADER] = key;
  return headers;
}

async function post(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: requestHeaders(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    const error = new Error(describeError(response.status, payload));
    error.status = response.status;
    throw error;
  }
  return payload;
}

function describeError(status, payload) {
  const detail = payload && payload.detail;
  if (status === 401) {
    return "This server needs an API key. Enter it in the \"API key\" box at the top and try again.";
  }
  if (status === 422) return "The question could not be sent: it must not be blank or too long.";
  if (typeof detail === "string") return detail;
  return `The server returned an error (HTTP ${status}).`;
}

function showError(message) {
  const box = el("error");
  box.textContent = message;
  box.hidden = !message;
}

function badge(text, kind) {
  const span = document.createElement("span");
  span.className = `badge ${kind}`;
  span.textContent = text;
  return span;
}

function field(node, name) {
  return node.querySelector(`[data-field="${name}"]`);
}

function renderTool(tool) {
  const box = document.createElement("div");
  box.className = `tool ${tool.ok ? "ok" : "not-ok"}`;
  const head = document.createElement("p");
  const name = document.createElement("strong");
  name.textContent = tool.tool;
  head.append(name, ` - ${tool.summary}`);
  box.append(head);
  if (!tool.ok && tool.error_code) {
    const err = document.createElement("p");
    err.className = "muted";
    err.textContent = `${tool.error_code}: ${tool.error_message || ""}`;
    box.append(err);
  }
  const data = Object.entries(tool.data || {});
  if (data.length) {
    const pre = document.createElement("pre");
    pre.textContent = JSON.stringify(tool.data, null, 2);
    box.append(pre);
  }
  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `source: ${tool.source} · observed ${tool.observed_at}`;
  box.append(meta);
  return box;
}

function renderAnswer(result) {
  const node = el("turn-template").content.firstElementChild.cloneNode(true);
  field(node, "question").textContent = result.question;

  const badges = field(node, "badges");
  badges.append(badge(`Turn ${result.turn}`, "neutral"));
  badges.append(result.rag_used ? badge("RAG used", "rag") : badge("No search", "off"));
  badges.append(result.mcp_used ? badge("MCP tools used", "mcp") : badge("No tools", "off"));
  badges.append(
    result.sources_consulted
      ? badge(`${result.sources.length} source(s) consulted`, "sources")
      : badge("No sources cited", "off"),
  );
  if (result.insufficient) badges.append(badge("Information insufficient", "insufficient"));
  if (result.is_follow_up) badges.append(badge(`Follow-up: ${result.resolution}`, "neutral"));

  if (result.is_follow_up) {
    const resolved = field(node, "resolved");
    resolved.textContent = `Understood as: ${result.resolved_question}`;
    resolved.hidden = false;
  }

  field(node, "text").textContent = result.text;

  const sources = field(node, "sources");
  for (const source of result.sources) {
    const li = document.createElement("li");
    li.textContent = source;
    sources.append(li);
  }
  field(node, "sources-box").hidden = result.sources.length === 0;

  const tools = field(node, "tools");
  for (const tool of result.tools) tools.append(renderTool(tool));
  field(node, "tools-box").hidden = result.tools.length === 0;

  field(node, "decision").textContent =
    `Route: ${result.decision.reason} - ${result.decision.explanation}`;
  const steps = field(node, "steps");
  for (const step of result.steps) {
    const li = document.createElement("li");
    li.textContent = `${step.step} -> ${step.outcome}: ${step.explanation}`;
    steps.append(li);
  }
  const r = result.retrieval;
  field(node, "retrieval").textContent = r.performed
    ? `Search: ${r.passes} pass(es), ${r.chunks_returned} of ${r.candidates_considered} passages cleared ` +
      `the floor ${r.min_score}; top score ${r.top_score ?? "none"}; LLM called: ${result.llm_called}.`
    : `No search was run. LLM called: ${result.llm_called}.`;
  return node;
}

async function startSession() {
  sessionId = (await post("/api/sessions")).session_id;
}

async function newConversation() {
  showError("");
  if (sessionId) {
    try {
      await post("/api/sessions/end", { session_id: sessionId });
    } catch {
      // The old session may already have expired; a new one starts regardless.
    }
  }
  sessionId = null;
  const conversation = el("conversation");
  conversation.replaceChildren(el("empty"));
  el("empty").hidden = false;
}

async function ask(event) {
  event.preventDefault();
  const question = el("question").value;
  if (!question.trim()) {
    showError("Type a question first.");
    return;
  }
  showError("");
  el("ask").disabled = true;
  el("status").textContent = "Thinking... (the first question loads the search model and can take a while)";
  try {
    if (!sessionId) await startSession();
    let result;
    try {
      result = await post("/api/sessions/ask", { session_id: sessionId, question });
    } catch (error) {
      if (error.status !== 404) throw error;
      // Expired or evicted: say so plainly - the earlier context is gone.
      sessionId = null;
      el("conversation").replaceChildren(el("empty"));
      throw new Error(`${error.message} Your earlier conversation has ended; ask again to start a new one.`);
    }
    el("empty").hidden = true;
    el("conversation").append(renderAnswer(result));
    el("question").value = "";
  } catch (error) {
    showError(error instanceof TypeError ? "The server could not be reached." : error.message);
  } finally {
    el("ask").disabled = false;
    el("status").textContent = "";
  }
}

el("api-key").value = loadKey();
el("api-key").addEventListener("change", () => saveKey(el("api-key").value.trim()));
el("ask-form").addEventListener("submit", ask);
el("new-session").addEventListener("click", newConversation);
el("question").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) el("ask-form").requestSubmit();
});
