const messages = document.querySelector("#messages");
const form = document.querySelector("#chat-form");
const question = document.querySelector("#question");
const sendButton = document.querySelector("#send-button");
const statusDot = document.querySelector("#status-dot");
const statusLabel = document.querySelector("#status-label");
const loginOverlay = document.querySelector("#login-overlay");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");

let token = sessionStorage.getItem("policyGuideToken") || "";

function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

function addMessage(role, text, options = {}) {
  const article = document.createElement("article");
  article.className = `message ${role}-message${options.error ? " error" : ""}`;

  if (role === "assistant") {
    article.innerHTML = `
      <div class="avatar">PG</div>
      <div class="message-content">
        <span class="message-author">Policy Guide</span>
        <div class="bubble">${escapeHtml(text)}</div>
      </div>`;
  } else {
    article.innerHTML = `
      <div class="message-content">
        <span class="message-author">You</span>
        <div class="bubble">${escapeHtml(text)}</div>
      </div>`;
  }

  const content = article.querySelector(".message-content");
  if (options.sources?.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "source-list";
    sourceList.innerHTML = options.sources
      .map((source) => `<span class="source-chip">Source: ${escapeHtml(source.chunk_id)}</span>`)
      .join("");
    content.appendChild(sourceList);
  }

  if (options.meta) {
    const meta = document.createElement("p");
    meta.className = "response-meta";
    meta.textContent = options.meta;
    content.appendChild(meta);
  }

  messages.appendChild(article);
  messages.scrollTop = messages.scrollHeight;
  return article;
}

function addTyping() {
  const article = addMessage("assistant", "");
  article.classList.add("typing-message");
  article.querySelector(".bubble").innerHTML = '<span class="typing"><i></i><i></i><i></i></span>';
  return article;
}

async function login(username, password) {
  const response = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new Error("Invalid username or password.");
  token = (await response.json()).access_token;
  sessionStorage.setItem("policyGuideToken", token);
  loginOverlay.classList.add("hidden");
}

async function checkHealth() {
  try {
    const response = await fetch("/api/v1/health");
    const health = await response.json();
    const healthy = health.status === "healthy";
    statusDot.className = `status-dot ${healthy ? "healthy" : "unhealthy"}`;
    statusLabel.textContent = healthy ? "All services ready" : "Some services unavailable";
  } catch {
    statusDot.className = "status-dot unhealthy";
    statusLabel.textContent = "Services unavailable";
  }
}

async function ask(query) {
  sendButton.disabled = true;
  question.disabled = true;
  addMessage("user", query);
  const typing = addTyping();

  try {
    if (!token) throw new Error("Please sign in before asking a question.");
    let response = await fetch("/api/v1/rag/chat", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ query, filters: {} }),
    });

    if (response.status === 401) {
      token = "";
      sessionStorage.removeItem("policyGuideToken");
      loginOverlay.classList.remove("hidden");
      throw new Error("Your session expired. Please sign in again.");
    }

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "The chatbot could not answer that question.");

    typing.remove();
    const citedSources = (data.sources || []).filter((source) => source.cited);
    const seconds = data.latency?.total_ms ? `${(data.latency.total_ms / 1000).toFixed(1)}s` : "";
    addMessage("assistant", data.answer, {
      sources: citedSources,
      meta: [data.cache_hit ? "Cached answer" : "Generated answer", seconds].filter(Boolean).join(" · "),
      error: data.failed,
    });
  } catch (error) {
    typing.remove();
    addMessage("assistant", error.message || "Something went wrong. Please try again.", { error: true });
  } finally {
    sendButton.disabled = false;
    question.disabled = false;
    question.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = question.value.trim();
  if (!query) return;
  question.value = "";
  question.style.height = "auto";
  ask(query);
});

question.addEventListener("input", () => {
  question.style.height = "auto";
  question.style.height = `${Math.min(question.scrollHeight, 140)}px`;
});

question.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll(".suggestion").forEach((button) => {
  button.addEventListener("click", () => ask(button.textContent.trim()));
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const data = new FormData(loginForm);
  try {
    await login(data.get("username"), data.get("password"));
    question.focus();
  } catch (error) {
    loginError.textContent = error.message;
  }
});

if (token) loginOverlay.classList.add("hidden");
checkHealth();
