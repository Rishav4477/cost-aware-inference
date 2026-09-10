const $ = (id) => document.getElementById(id);

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "—";
}

function dollars(value) {
  if (value === undefined || value === null) return "—";
  if (value === 0) return "$0.000000";
  return `$${Number(value).toFixed(6)}`;
}

function setText(id, value) {
  const element = $(id);
  if (element) element.textContent = value;
}

function setHidden(id, hidden) {
  const element = $(id);
  if (element) element.classList.toggle("hidden", hidden);
}

function renderStatus(data) {
  setText("systemStatus", "Gateway online");

  const providerList = $("providerList");
  if (providerList) {
    providerList.innerHTML = "";
    (data.providers || []).forEach((provider) => {
      const card = document.createElement("div");
      card.className = "provider";
      const input = Number(provider.input_usd_per_million).toFixed(2);
      const output = Number(provider.output_usd_per_million).toFixed(2);
      card.innerHTML = `
        <div class="provider-top">
          <div><span class="provider-name">${provider.label}</span><div class="provider-id">${provider.id}</div></div>
          <span class="health ${provider.healthy ? "" : "down"}">● ${provider.healthy ? "eligible" : "circuit open"}</span>
        </div>
        <div class="provider-meta">
          <div><span>Latency</span><strong>${provider.latency_ms} ms</strong></div>
          <div><span>Utilization</span><strong>${Math.round(provider.utilization * 100)}%</strong></div>
          <div><span>Input / 1M</span><strong>$${input}</strong></div>
          <div><span>Output / 1M</span><strong>$${output}</strong></div>
        </div>
        <span class="trust ${provider.trusted ? "trusted" : ""}">${provider.trusted ? "Trusted for sensitive traffic" : "Standard provider"}</span>`;
      providerList.appendChild(card);
    });
  }

  const weights = $("weights");
  if (weights) {
    weights.innerHTML = "";
    Object.entries(data.weights || {}).forEach(([name, value]) => {
      const row = document.createElement("div");
      row.className = "weight-row";
      row.innerHTML = `<span>${titleCase(name)}</span><div class="bar"><div class="fill" style="width:${Math.round(value * 100)}%"></div></div><strong>${Math.round(value * 100)}%</strong>`;
      weights.appendChild(row);
    });
  }

  const services = $("services");
  if (services) {
    services.innerHTML = "";
    Object.entries(data.services || {}).forEach(([name, active]) => {
      const item = document.createElement("span");
      item.className = `service ${active ? "on" : "off"}`;
      item.textContent = name.replaceAll("_", " ");
      services.appendChild(item);
    });
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/public/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status unavailable");
    renderStatus(await response.json());
  } catch (error) {
    setText("systemStatus", "Gateway unavailable");
    const dot = document.querySelector(".dot");
    if (dot) dot.style.background = "var(--bad)";
  }
}

async function runInference() {
  const promptElement = $("prompt");
  const prompt = promptElement ? promptElement.value.trim() : "";
  if (!prompt) {
    setHidden("errorBox", false);
    setText("errorBox", "Enter a prompt first.");
    return;
  }

  const allowedClouds = [...document.querySelectorAll("#cloudChecks input:checked")].map((item) => item.value);
  if (!allowedClouds.length) {
    setHidden("errorBox", false);
    setText("errorBox", "Select at least one eligible cloud.");
    return;
  }

  const failureCloud = $("failureCloud");
  const cacheMode = $("cacheMode");
  const maxTokens = $("maxTokens");
  const sensitiveToggle = $("sensitiveToggle");
  const button = $("runBtn");

  if (button) {
    button.disabled = true;
    button.innerHTML = "<span>Routing…</span><b>→</b>";
  }
  setHidden("errorBox", true);

  const started = performance.now();
  try {
    const response = await fetch("/public/infer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        allowed_clouds: allowedClouds,
        fail_clouds: failureCloud?.value ? [failureCloud.value] : [],
        cache: cacheMode?.value || "exact",
        max_tokens: Number(maxTokens?.value || 128),
        sensitive: Boolean(sensitiveToggle?.checked),
      }),
    });

    const roundTrip = performance.now() - started;
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Inference failed");

    const routing = data.routing || {};
    const usage = data.usage || {};
    const message = data.choices?.[0]?.message?.content || "No response content";

    setText("answer", message);
    setText("routeBadge", `${String(routing.cloud || "?").toUpperCase()} selected`);
    setText("metricCloud", String(routing.cloud || "—").toUpperCase());
    setText("metricProvider", routing.provider || "—");
    setText("metricAttempts", (routing.attempts || []).join(" → ") || "—");
    setText("metricCache", routing.cache_hit || "miss");
    setText("metricCost", dollars(routing.estimated_cost_usd));
    setText("metricReserved", dollars(routing.reserved_cost_usd));
    setText("metricPromptTokens", usage.prompt_tokens ?? "—");
    setText("metricOutputTokens", usage.completion_tokens ?? "—");
    setText("metricRoundTrip", `${Math.round(roundTrip)} ms`);

    setHidden("resultBox", false);
    await loadStatus();
  } catch (error) {
    setHidden("errorBox", false);
    setText("errorBox", error.message || "Inference failed");
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = "<span>Run inference</span><b>→</b>";
    }
  }
}

const runButton = $("runBtn");
if (runButton) runButton.addEventListener("click", runInference);

const exampleButton = $("exampleBtn");
if (exampleButton) {
  exampleButton.addEventListener("click", () => {
    const prompt = $("prompt");
    if (!prompt) return;
    prompt.value = "Explain why a cost-aware router might choose a slightly slower cloud provider for an AI inference request.";
    prompt.dispatchEvent(new Event("input"));
  });
}

const prompt = $("prompt");
if (prompt) {
  const updateCount = () => setText("promptCount", `${prompt.value.length} / 4000`);
  prompt.addEventListener("input", updateCount);
  updateCount();
}

loadStatus();
setInterval(loadStatus, 15000);
