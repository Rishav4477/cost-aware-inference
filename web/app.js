const $ = (id) => document.getElementById(id);

function titleCase(value) {
  return value ? value.charAt(0).toUpperCase() + value.slice(1) : "—";
}

function dollars(value) {
  if (value === undefined || value === null) return "—";
  if (value === 0) return "$0.000000";
  return `$${Number(value).toFixed(6)}`;
}

function setHidden(id, hidden) {
  $(id).classList.toggle("hidden", hidden);
}

function renderStatus(data) {
  $("systemStatus").textContent = "Gateway online";

  const providerList = $("providerList");
  providerList.innerHTML = "";
  data.providers.forEach((provider) => {
    const card = document.createElement("div");
    card.className = "provider";
    const input = Number(provider.input_usd_per_million).toFixed(2);
    card.innerHTML = `
      <div class="provider-top">
        <span class="provider-name">${provider.label}</span>
        <span class="health">● ${provider.healthy ? "eligible" : "circuit open"}</span>
      </div>
      <div class="provider-meta">
        <div><span>Latency</span><strong>${provider.latency_ms} ms</strong></div>
        <div><span>Load</span><strong>${Math.round(provider.utilization * 100)}%</strong></div>
        <div><span>Input / 1M</span><strong>$${input}</strong></div>
      </div>`;
    providerList.appendChild(card);
  });

  const weights = $("weights");
  weights.innerHTML = "";
  Object.entries(data.weights).forEach(([name, value]) => {
    const row = document.createElement("div");
    row.className = "weight-row";
    row.innerHTML = `<span>${titleCase(name)}</span><div class="bar"><div class="fill" style="width:${Math.round(value * 100)}%"></div></div><strong>${Math.round(value * 100)}%</strong>`;
    weights.appendChild(row);
  });

  const services = $("services");
  services.innerHTML = "";
  Object.entries(data.services).forEach(([name, active]) => {
    const item = document.createElement("span");
    item.className = `service ${active ? "on" : "off"}`;
    item.textContent = name.replaceAll("_", " ");
    services.appendChild(item);
  });
}

async function loadStatus() {
  try {
    const response = await fetch("/public/status", { cache: "no-store" });
    if (!response.ok) throw new Error("status unavailable");
    renderStatus(await response.json());
  } catch (error) {
    $("systemStatus").textContent = "Gateway unavailable";
    document.querySelector(".dot").style.background = "var(--bad)";
  }
}

async function runInference() {
  const prompt = $("prompt").value.trim();
  if (!prompt) {
    setHidden("errorBox", false);
    $("errorBox").textContent = "Enter a prompt first.";
    return;
  }

  const allowedClouds = [...document.querySelectorAll("#cloudChecks input:checked")].map((item) => item.value);
  if (!allowedClouds.length) {
    setHidden("errorBox", false);
    $("errorBox").textContent = "Select at least one eligible cloud.";
    return;
  }

  const failCloud = $("failureCloud").value;
  const button = $("runBtn");
  button.disabled = true;
  button.textContent = "Routing…";
  setHidden("errorBox", true);

  try {
    const response = await fetch("/public/infer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt,
        allowed_clouds: allowedClouds,
        fail_clouds: failCloud ? [failCloud] : [],
        cache: $("cacheMode").value,
        max_tokens: 128,
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Inference failed");

    const routing = data.routing || {};
    const message = data.choices?.[0]?.message?.content || "No response content";
    $("answer").textContent = message;
    $("routeBadge").textContent = `${String(routing.cloud || "?").toUpperCase()} selected`;
    $("metricCloud").textContent = String(routing.cloud || "—").toUpperCase();
    $("metricProvider").textContent = routing.provider || "—";
    $("metricAttempts").textContent = (routing.attempts || []).join(" → ") || "—";
    $("metricCache").textContent = routing.cache_hit || "miss";
    $("metricCost").textContent = dollars(routing.estimated_cost_usd);
    $("metricTokens").textContent = data.usage?.total_tokens ?? "—";
    setHidden("resultBox", false);
    await loadStatus();
  } catch (error) {
    setHidden("errorBox", false);
    $("errorBox").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Run inference";
  }
}

$("runBtn").addEventListener("click", runInference);
$("exampleBtn").addEventListener("click", () => {
  $("prompt").value = "Explain why a cost-aware router might choose a slightly slower cloud provider for an AI inference request.";
});

loadStatus();
setInterval(loadStatus, 15000);
