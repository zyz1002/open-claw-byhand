// ============================================================
// Yuu's Robots — Agent Dashboard
// ============================================================

const WS_URL = `ws://${location.host}/ws`;

// --- Canvas animation state ---
let ws = null;
let agentState = "idle";
let agentDetail = "waiting...";
let bubbleText = "";
let bubbleTimer = 0;
let animFrame = 0;
let charX = 120;
let charY = 352;
let targetX = 120;
let targetY = 352;
let facingRight = true;
let isMoving = false;
let walkTick = 0;
let auraPulse = 0;

const canvas = document.getElementById("roomCanvas");
const ctx = canvas.getContext("2d");
const W = canvas.width;
const H = canvas.height;

const roomBg = new Image();
roomBg.src = "room_bg.png";
let bgLoaded = false;
roomBg.onload = () => { bgLoaded = true; };

const STATE_LABELS = { idle: "IDLE", thinking: "THINKING", tool_use: "TOOL USE", responding: "RESPONDING", done: "DONE" };

const STATE_SCENES = {
  idle: { x: 122, y: 352, glow: "#6f8f7b", bubble: "resting..." },
  thinking: { x: 355, y: 342, glow: "#f4a261", bubble: "thinking..." },
  tool_use: { x: 560, y: 342, glow: "#7c6cf2", bubble: "using tool" },
  responding: { x: 430, y: 342, glow: "#4da3ff", bubble: "writing..." },
  done: { x: 430, y: 342, glow: "#36b37e", bubble: "done!" },
};

// --- Panel state ---
const pendingToolCalls = {};  // tool_id -> DOM element
let currentPersonaTab = "SOUL.md";
let personaData = {};
let currentToolGroup = null;  // current conversation group in toolCallList
let deepResearchActive = false;

// ============================================================
// Tab switching
// ============================================================

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  document.querySelectorAll(".tab-content").forEach(tc => {
    tc.classList.toggle("active", tc.id === `tab-${tabName}`);
  });
  if (tabName === "memories") loadMemories();
}

// ============================================================
// WebSocket connection
// ============================================================

function connectWS() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    document.getElementById("wsDot").className = "status-indicator connected";
    document.getElementById("wsStatus").textContent = "CONNECTED";
  };
  ws.onclose = () => {
    document.getElementById("wsDot").className = "status-indicator disconnected";
    document.getElementById("wsStatus").textContent = "RECONNECTING...";
    setTimeout(connectWS, 3000);
  };
  ws.onerror = () => ws.close();
  ws.onmessage = (e) => handleWSMessage(JSON.parse(e.data));
}

function handleWSMessage(data) {
  if (data.type === "init") {
    agentState = data.state || "idle";
    agentDetail = data.detail || "waiting...";
    updateStatusUI();
    onStateChange(agentState, true);
    if (data.logs) data.logs.forEach(e => addLogEntry(e.role, e.content, e.timestamp));
    if (data.conversations) data.conversations.forEach(e => addConversationEntry(e.role, e.content, e.timestamp));
    if (data.thinking_steps) data.thinking_steps.forEach(e => addThinkingStep(e.content, e.step, e.timestamp));
    if (data.tool_calls) {
      // Load tool calls — they'll go into currentToolGroup if a user message was loaded
      data.tool_calls.forEach(e => {
        addToolCall(e.tool_name, e.tool_id, e.input, e.step, e.timestamp);
        if (e.result !== null && e.result !== undefined) updateToolResult(e.tool_id, e.result, e.is_error);
      });
    }
    if (data.persona) showPersona(data.persona);
    if (data.deep_research_active !== undefined) {
      deepResearchActive = data.deep_research_active;
      updateDeepResearchToggle();
    }
    if (data.plan) updatePlanDisplay(data.plan);
    showReminders([]);
    return;
  }

  if (data.type === "status_update") {
    agentState = data.state || "idle";
    agentDetail = data.detail || "";
    updateStatusUI();
    onStateChange(agentState, false);
    return;
  }

  if (data.type === "log_entry") { addLogEntry(data.log.role, data.log.content, data.log.timestamp); return; }

  if (data.type === "conversation") { addConversationEntry(data.role, data.content, data.timestamp); return; }
  if (data.type === "thinking_step") { addThinkingStep(data.content, data.step, data.timestamp); return; }
  if (data.type === "tool_call") { addToolCall(data.tool_name, data.tool_id, data.input, data.step, data.timestamp); return; }
  if (data.type === "tool_result") { updateToolResult(data.tool_id, data.result, data.is_error); return; }
  if (data.type === "memory_snapshot") {
    if (data.reminders) showReminders(data.reminders);
    return;
  }
  if (data.type === "persona_update") { showPersona(data.files); return; }
  if (data.type === "deep_research_toggle") {
    deepResearchActive = data.active;
    updateDeepResearchToggle();
    return;
  }
  if (data.type === "plan_update") { updatePlanDisplay(data); return; }
}

// ============================================================
// Status UI
// ============================================================

function updateStatusUI() {
  const badge = document.getElementById("agentStateBadge");
  badge.textContent = STATE_LABELS[agentState] || agentState;
  badge.className = `state-badge ${agentState}`;
  document.getElementById("agentDetail").textContent = agentDetail || "waiting...";
}

function addLogEntry(role, content, timestamp) {
  // kept for backward compat
}

// ============================================================
// Panel renderers
// ============================================================

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text || "");
  return div.innerHTML;
}

// --- Conversation ---
function addConversationEntry(role, content, timestamp) {
  const list = document.getElementById("conversationList");
  const empty = list.querySelector(".panel-empty");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = `conv-entry ${role}`;
  const time = timestamp || new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const roleLabel = role === "user" ? "USR" : "AST";
  const preview = String(content || "").length > 500 ? String(content).slice(0, 500) + "..." : String(content);

  item.innerHTML = `
    <div><span class="conv-time">${escapeHtml(time)}</span><span class="conv-role">${roleLabel}</span></div>
    <div class="conv-content">${escapeHtml(preview)}</div>
  `;
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;

  // When user sends a message, create a new tool group
  if (role === "user") {
    addToolGroup(preview, time);
  }
}

// --- Tool group (separates tool calls by conversation turn) ---
function addToolGroup(userMessage, time) {
  const list = document.getElementById("toolCallList");
  const empty = list.querySelector(".panel-empty");
  if (empty) empty.remove();

  const group = document.createElement("div");
  group.className = "tool-group";
  const msgPreview = String(userMessage).length > 40 ? String(userMessage).slice(0, 40) + "..." : userMessage;

  group.innerHTML = `
    <div class="tool-group-header" onclick="toggleToolGroup(this)">
      <span class="tool-group-arrow">&#9660;</span>
      <span class="tool-group-icon">&#128172;</span>
      <span class="tool-group-msg">${escapeHtml(msgPreview)}</span>
      <span class="tool-group-time">${escapeHtml(time)}</span>
    </div>
    <div class="tool-group-items"></div>
  `;
  list.appendChild(group);
  currentToolGroup = group.querySelector(".tool-group-items");
  list.scrollTop = list.scrollHeight;
}

// --- Thinking / Reasoning (card style with icon) ---
function addThinkingStep(content, step, timestamp) {
  const list = document.getElementById("thinkingList");
  const empty = list.querySelector(".panel-empty");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "thinking-entry";
  const text = String(content || "").length > 400 ? String(content).slice(0, 400) + "..." : String(content);
  const time = timestamp || new Date().toLocaleTimeString("zh-CN", { hour12: false });

  item.innerHTML = `
    <div class="thinking-header">
      <span class="thinking-icon">&#128161;</span>
      <span class="step-num">STEP ${step}</span>
      <span class="conv-time" style="margin-left:auto">${escapeHtml(time)}</span>
    </div>
    <div class="thinking-text">${escapeHtml(text)}</div>
  `;
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;
}

// --- Tool calls (card style, appended into current group) ---
function addToolCall(toolName, toolId, input, step, timestamp) {
  const target = currentToolGroup || document.getElementById("toolCallList");
  const list = document.getElementById("toolCallList");
  const empty = list.querySelector(".panel-empty");
  if (empty) empty.remove();

  const item = document.createElement("div");
  item.className = "tool-call-item";
  item.dataset.toolId = toolId;

  const inputStr = typeof input === "string" ? input : JSON.stringify(input, null, 2);
  const inputPreview = String(inputStr).length > 300 ? String(inputStr).slice(0, 300) + "..." : inputStr;
  const time = timestamp || new Date().toLocaleTimeString("zh-CN", { hour12: false });

  item.innerHTML = `
    <div class="tool-call-header" onclick="toggleToolExpand(this)">
      <div class="tool-call-left">
        <span class="tool-icon">&#9881;</span>
        <span class="tool-name">${escapeHtml(toolName)}</span>
        <span class="tool-step">Step ${step}</span>
      </div>
      <span class="tool-status-badge running">running</span>
    </div>
    <div class="tool-call-input">
      <div class="tool-section-label">Input</div>
      <div class="tool-section-content">${escapeHtml(inputPreview)}</div>
    </div>
    <div class="tool-call-output">
      <div class="tool-section-label">Output</div>
      <div class="tool-section-content"></div>
    </div>
  `;
  target.appendChild(item);
  pendingToolCalls[toolId] = item;
  list.scrollTop = list.scrollHeight;
}

function updateToolResult(toolId, result, isError) {
  const item = pendingToolCalls[toolId];
  if (!item) return;

  const badge = item.querySelector(".tool-status-badge");
  badge.textContent = isError ? "error" : "done";
  badge.className = `tool-status-badge ${isError ? "error" : "ok"}`;

  const resultStr = typeof result === "string" ? result : JSON.stringify(result, null, 2);
  const resultPreview = String(resultStr).length > 500 ? String(resultStr).slice(0, 500) + "..." : resultStr;
  const outputContent = item.querySelector(".tool-call-output .tool-section-content");
  if (outputContent) outputContent.textContent = resultPreview;
}

function toggleToolExpand(header) {
  header.parentElement.classList.toggle("expanded");
}

function toggleToolGroup(header) {
  const group = header.parentElement;
  const collapsed = group.classList.toggle("collapsed");
  const arrow = header.querySelector(".tool-group-arrow");
  if (arrow) arrow.innerHTML = collapsed ? "&#9654;" : "&#9660;";
}

// --- Reminders ---
function showReminders(reminders) {
  const list = document.getElementById("reminderList");
  if (!list) return;
  list.innerHTML = "";

  if (!reminders || reminders.length === 0) {
    list.innerHTML = '<div class="panel-empty">暂无提醒任务</div>';
    return;
  }

  for (const rem of reminders) {
    const item = document.createElement("div");
    const statusClass = rem.status === "done" || rem.status === "completed" ? "done"
                      : rem.status === "active" || rem.status === "pending" ? "active" : "";
    item.className = `reminder-item ${statusClass}`;
    // DB returns trigger_type ("date"/"cron") + trigger_expr (the actual time/cron string)
    const timeStr = rem.trigger_expr || rem.trigger_at || rem.time || rem.cron || "";
    const typeLabel = rem.trigger_type === "cron" ? "Cron" : rem.trigger_type === "date" ? "" : "";
    const statusLabel = statusClass === "done" ? "已完成"
                      : statusClass === "active" ? "等待中" : (rem.status || "");
    item.innerHTML = `
      <div class="reminder-time">${escapeHtml(timeStr)}</div>
      <div class="reminder-content">${escapeHtml(rem.content || rem.message || "")}</div>
      <div class="reminder-status">${escapeHtml(statusLabel)}</div>
    `;
    list.appendChild(item);
  }
}

// --- Persona ---
function showPersona(files) {
  personaData = files || {};
  renderPersonaPanel();
}

function renderPersonaPanel() {
  const container = document.getElementById("personaContent");
  if (!container) return;

  const tabs = ["SOUL.md", "AGENTS.md", "USER.md"].map(f =>
    `<div class="persona-tab ${f === currentPersonaTab ? 'active' : ''}"
         onclick="switchPersonaTab('${f}')">${f.replace('.md', '')}</div>`
  ).join("");

  const content = personaData[currentPersonaTab] || "";
  container.innerHTML = `
    <div class="persona-tabs">${tabs}</div>
    <textarea class="persona-textarea" id="personaEditor">${escapeHtml(content)}</textarea>
    <div class="persona-actions">
      <button class="persona-btn persona-btn-save" id="personaSaveBtn" onclick="savePersona()">SAVE</button>
    </div>
  `;
}

function switchPersonaTab(filename) {
  currentPersonaTab = filename;
  renderPersonaPanel();
}

function savePersona() {
  const content = document.getElementById("personaEditor").value;
  const btn = document.getElementById("personaSaveBtn");
  btn.textContent = "SAVED!";
  btn.className = "persona-btn persona-btn-saved";

  fetch("/api/persona", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: currentPersonaTab, content: content }),
  }).then(r => r.json()).then(() => {
    setTimeout(() => {
      btn.textContent = "SAVE";
      btn.className = "persona-btn persona-btn-save";
    }, 1500);
  }).catch(() => {
    btn.textContent = "ERROR";
    btn.className = "persona-btn persona-btn-save";
    btn.style.background = "var(--accent)";
    setTimeout(() => {
      btn.textContent = "SAVE";
      btn.style.background = "";
    }, 2000);
  });
}

// ============================================================
// Canvas animation (preserved)
// ============================================================

function onStateChange(newState, immediate) {
  const scene = STATE_SCENES[newState] || STATE_SCENES.idle;
  targetX = scene.x;
  targetY = scene.y;

  if (newState === "tool_use") {
    bubbleText = (agentDetail || scene.bubble).slice(0, 18);
    bubbleTimer = 120;
  } else {
    bubbleText = scene.bubble;
    bubbleTimer = immediate ? 0 : 130;
  }

  if (newState === "done") {
    setTimeout(() => {
      if (agentState === "done" || agentState === "idle") {
        targetX = STATE_SCENES.idle.x;
        targetY = STATE_SCENES.idle.y;
      }
    }, 2600);
  }
}

function drawRoom() {
  if (bgLoaded) {
    ctx.drawImage(roomBg, 0, 0, W, H);
  } else {
    const gradient = ctx.createLinearGradient(0, 0, 0, H);
    gradient.addColorStop(0, "#efe7d8");
    gradient.addColorStop(1, "#d8c7af");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, W, H);
  }

  ctx.fillStyle = "rgba(255, 248, 239, 0.74)";
  ctx.fillRect(0, 0, W, 76);

  const haze = ctx.createLinearGradient(0, 0, W, H);
  haze.addColorStop(0, "rgba(255,255,255,0.26)");
  haze.addColorStop(1, "rgba(123, 88, 57, 0.08)");
  ctx.fillStyle = haze;
  ctx.fillRect(0, 0, W, H);

  drawStations();
  drawFloorGlow();
}

function drawStations() {
  drawStation(112, 362, 96, "SOFA", "#8ba888", agentState === "idle");
  drawStation(354, 350, 110, "THINK", "#eea45d", agentState === "thinking");
  drawStation(560, 350, 110, "TOOLS", "#7d6bff", agentState === "tool_use");
  drawStation(432, 350, 110, "WRITE", "#4798ef", agentState === "responding" || agentState === "done");
}

function drawStation(x, y, width, label, color, active) {
  ctx.save();
  ctx.translate(x, y);
  ctx.fillStyle = "rgba(57, 41, 26, 0.12)";
  ctx.beginPath();
  ctx.ellipse(0, 0, width * 0.62, 16, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = active ? color : "rgba(77, 63, 51, 0.28)";
  ctx.fillRect(-width / 2, -6, width, 6);
  ctx.fillStyle = active ? "rgba(255,255,255,0.86)" : "rgba(255,255,255,0.6)";
  ctx.font = "11px 'Press Start 2P', monospace";
  ctx.textAlign = "center";
  ctx.fillText(label, 0, -14);
  ctx.restore();
}

function drawFloorGlow() {
  const scene = STATE_SCENES[agentState] || STATE_SCENES.idle;
  const radius = 32 + Math.sin(auraPulse) * 3;
  const glow = ctx.createRadialGradient(charX, charY + 14, 8, charX, charY + 14, radius);
  glow.addColorStop(0, `${scene.glow}88`);
  glow.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.ellipse(charX, charY + 14, radius, 20, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawBot(x, y, state) {
  ctx.save();
  ctx.translate(x, y);
  if (!facingRight) ctx.scale(-1, 1);

  const bounce = Math.sin(animFrame * 0.09) * 1.6;
  const armSwing = isMoving ? Math.sin(walkTick * 0.7) * 5.4 : 0;
  const legSwing = isMoving ? Math.sin(walkTick * 0.7) * 4.2 : 0;
  const eyePulse = state === "thinking" ? (Math.sin(animFrame * 0.24) > 0 ? 1 : 0.65) : 1;

  ctx.translate(0, bounce);
  drawShadowPlate();
  drawToolCompanion(state);

  // Hair
  ctx.fillStyle = "#7a4e36";
  roundRect(ctx, -19, -63, 38, 15, 10); ctx.fill();
  ctx.fillStyle = "#9e6d4b";
  roundRect(ctx, -14, -60, 28, 8, 5); ctx.fill();
  // Face
  ctx.fillStyle = "#f7b48a";
  roundRect(ctx, -17, -57, 34, 41, 14); ctx.fill();
  ctx.fillStyle = "rgba(255,255,255,0.18)";
  roundRect(ctx, -12, -53, 9, 20, 5); ctx.fill();
  // Forehead band
  ctx.fillStyle = "#fff1e7";
  roundRect(ctx, -15, -48, 30, 10, 6); ctx.fill();
  // Shirt
  ctx.fillStyle = "#6aa7d8";
  roundRect(ctx, -12, -16, 24, 30, 10); ctx.fill();
  ctx.fillStyle = "#dff2ff";
  roundRect(ctx, -7, -4, 14, 9, 4); ctx.fill();
  // Pants
  ctx.fillStyle = "#31475e";
  roundRect(ctx, -11, 13, 8, 24, 5); ctx.fill();
  roundRect(ctx, 3, 13, 8, 24, 5); ctx.fill();
  // Shoes
  ctx.fillStyle = "#1c2732";
  roundRect(ctx, -15 - legSwing * 0.12, 34, 13, 7, 4); ctx.fill();
  roundRect(ctx, 2 + legSwing * 0.12, 34, 13, 7, 4); ctx.fill();
  // Left arm
  ctx.save();
  ctx.translate(-15, -8);
  ctx.rotate((-0.2 + armSwing * 0.03) * (state === "tool_use" ? 1.4 : 1));
  ctx.fillStyle = "#f7b48a";
  roundRect(ctx, -3, 0, 6, 22, 4); ctx.fill();
  ctx.restore();
  // Right arm
  ctx.save();
  ctx.translate(15, -8);
  ctx.rotate((0.2 - armSwing * 0.03) * (state === "responding" ? 1.2 : 1));
  ctx.fillStyle = "#f7b48a";
  roundRect(ctx, -3, 0, 6, 22, 4); ctx.fill();
  ctx.restore();
  // Eyes
  ctx.fillStyle = "#ffffff";
  roundRect(ctx, -10, -45, 7, 5 * eyePulse, 3); ctx.fill();
  roundRect(ctx, 3, -45, 7, 5 * eyePulse, 3); ctx.fill();
  // Pupils
  ctx.fillStyle = state === "thinking" ? "#ffb347" : "#5f4b42";
  roundRect(ctx, -8, -44, 3, 3 * eyePulse, 2); ctx.fill();
  roundRect(ctx, 5, -44, 3, 3 * eyePulse, 2); ctx.fill();
  // Mouth
  ctx.strokeStyle = "rgba(123, 78, 54, 0.55)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(-4, -31);
  ctx.quadraticCurveTo(0, -28.5, 4, -31);
  ctx.stroke();
  // Done checkmark
  if (state === "done") {
    ctx.strokeStyle = "#36b37e";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(10, -78);
    ctx.lineTo(16, -72);
    ctx.lineTo(28, -86);
    ctx.stroke();
  }
  if (state === "thinking") drawThinkingOrbs();
  if (state === "responding") drawTypingLines();
  ctx.restore();
}

function drawShadowPlate() {
  ctx.fillStyle = "rgba(15, 12, 10, 0.12)";
  ctx.beginPath();
  ctx.ellipse(0, 42, 24, 8, 0, 0, Math.PI * 2);
  ctx.fill();
}

function drawThinkingOrbs() {
  for (let i = 0; i < 3; i++) {
    const phase = animFrame * 0.08 + i * 0.9;
    ctx.fillStyle = `rgba(255, 193, 106, ${0.35 + Math.sin(phase) * 0.18})`;
    ctx.beginPath();
    ctx.arc(-12 + i * 12, -76 - Math.sin(phase) * 4, 4 - i * 0.5, 0, Math.PI * 2);
    ctx.fill();
  }
}

function drawTypingLines() {
  ctx.strokeStyle = "rgba(130, 208, 255, 0.92)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(24, -18); ctx.lineTo(36, -22);
  ctx.moveTo(24, -10); ctx.lineTo(42, -10);
  ctx.moveTo(24, -2); ctx.lineTo(38, 2);
  ctx.stroke();
}

function drawToolCompanion(state) {
  if (state !== "tool_use") return;
  const bob = Math.sin(animFrame * 0.15) * 4;
  ctx.save();
  ctx.translate(34, -28 + bob);
  ctx.fillStyle = "#ffffff";
  roundRect(ctx, -16, -10, 28, 20, 10); ctx.fill();
  ctx.fillStyle = "#7d6bff";
  roundRect(ctx, -12, -6, 20, 12, 6); ctx.fill();
  ctx.strokeStyle = "rgba(125, 107, 255, 0.35)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(-2, 10); ctx.lineTo(-10, 18);
  ctx.stroke();
  ctx.restore();
}

function drawSpeechBubble() {
  if (!bubbleText || bubbleTimer <= 0) return;
  ctx.save();
  ctx.font = "12px 'Press Start 2P', monospace";
  ctx.textAlign = "center";
  const width = Math.min(240, ctx.measureText(bubbleText).width + 28);
  const height = 34;
  const bx = charX - width / 2;
  const by = charY - 108;
  ctx.fillStyle = "rgba(255, 251, 245, 0.95)";
  roundRect(ctx, bx, by, width, height, 12); ctx.fill();
  ctx.strokeStyle = "rgba(88, 72, 56, 0.25)";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(charX - 8, by + height);
  ctx.lineTo(charX, by + height + 10);
  ctx.lineTo(charX + 10, by + height);
  ctx.closePath();
  ctx.fillStyle = "rgba(255, 251, 245, 0.95)";
  ctx.fill();
  ctx.fillStyle = "#59473a";
  ctx.fillText(bubbleText.toUpperCase(), charX, by + 22);
  ctx.restore();
}

function roundRect(context, x, y, width, height, radius) {
  context.beginPath();
  context.roundRect(x, y, width, height, radius);
}

function update() {
  animFrame += 1;
  auraPulse += 0.07;
  const speed = 3.2;
  const dx = targetX - charX;
  const dy = targetY - charY;
  isMoving = Math.abs(dx) > speed || Math.abs(dy) > speed;
  if (isMoving) {
    facingRight = dx > 0;
    charX += Math.abs(dx) > speed ? Math.sign(dx) * speed : dx;
    charY += Math.abs(dy) > speed ? Math.sign(dy) * speed : dy;
    walkTick += 1;
  }
  if (bubbleTimer > 0) bubbleTimer -= 1;
}

function draw() {
  ctx.clearRect(0, 0, W, H);
  drawRoom();
  drawBot(charX, charY, agentState);
  drawSpeechBubble();
}

function gameLoop() {
  update();
  draw();
  requestAnimationFrame(gameLoop);
}

// ============================================================
// Deep Research toggle + Plan display
// ============================================================

// --- Memory panel ---
const CATEGORY_LABELS = {
  fact: "事实", preference: "偏好", identity: "身份",
  habit: "习惯", goal: "目标", project: "项目", reminder: "提醒",
};
const CATEGORY_COLORS = {
  fact: "#2f88db", preference: "#d85e43", identity: "#6b55e0",
  habit: "#2c966a", goal: "#c48520", project: "#7d6bff", reminder: "#e07c3a",
};

function loadMemories() {
  const status = document.getElementById("memoryStatusFilter").value;

  fetch(`/api/memories?status=${status}`)
    .then(r => r.json())
    .then(data => renderMemories(data.memories || []))
    .catch(() => {
      document.getElementById("memoryList").innerHTML =
        '<div class="panel-empty">加载失败</div>';
    });
}

function renderMemories(memories) {
  const list = document.getElementById("memoryList");
  list.innerHTML = "";

  if (!memories.length) {
    list.innerHTML = '<div class="panel-empty">没有符合条件的记忆</div>';
    return;
  }

  // Group by category
  const groups = {};
  for (const m of memories) {
    const cat = m.category || "fact";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(m);
  }

  // Render each category group
  for (const [cat, items] of Object.entries(groups)) {
    const color = CATEGORY_COLORS[cat] || "#888";
    const label = CATEGORY_LABELS[cat] || cat;

    const groupEl = document.createElement("div");
    groupEl.className = "memory-group";
    groupEl.innerHTML = `
      <div class="memory-group-header">
        <span class="memory-category-dot" style="background:${color}"></span>
        <span class="memory-category-label">${escapeHtml(label)}</span>
        <span class="memory-category-label-en">${escapeHtml(cat)}</span>
        <span class="memory-count">${items.length}</span>
      </div>
    `;

    for (const m of items) {
      const item = document.createElement("div");
      item.className = "memory-item";
      item.dataset.id = m.id;

      const date = m.created_at ? m.created_at.slice(0, 16).replace("T", " ") : "";
      item.innerHTML = `
        <div class="memory-item-header">
          <span class="memory-date">${escapeHtml(date)}</span>
          <span class="memory-status-badge ${m.status}">${escapeHtml(m.status)}</span>
        </div>
        <div class="memory-content">${escapeHtml(m.content)}</div>
        <div class="memory-actions">
          <button class="memory-action-btn" onclick="setMemoryStatus(${m.id}, 'outdated')" title="标记过期">&#9208;</button>
          <button class="memory-action-btn" onclick="setMemoryStatus(${m.id}, 'completed')" title="标记完成">&#10003;</button>
          <button class="memory-action-btn danger" onclick="deleteMemory(${m.id})" title="删除">&#10005;</button>
        </div>
      `;
      groupEl.appendChild(item);
    }

    list.appendChild(groupEl);
  }
}

function deleteMemory(id) {
  fetch(`/api/memories/${id}`, { method: "DELETE" })
    .then(r => r.json())
    .then(() => loadMemories());
}

function setMemoryStatus(id, status) {
  fetch(`/api/memories/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  }).then(r => r.json()).then(() => loadMemories());
}

function toggleDeepResearch() {
  deepResearchActive = !deepResearchActive;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "toggle_deep_research", active: deepResearchActive }));
  }
  updateDeepResearchToggle();
}

function updateDeepResearchToggle() {
  const toggle = document.getElementById("deepResearchToggle");
  if (toggle) toggle.checked = deepResearchActive;
}

function togglePlanSection() {
  const section = document.getElementById("planSection");
  const body = section.querySelector(".plan-section-body");
  const icon = document.getElementById("planToggleIcon");
  if (body.style.display === "none") {
    body.style.display = "block";
    icon.innerHTML = "&#9660;";
  } else {
    body.style.display = "none";
    icon.innerHTML = "&#9654;";
  }
}

function updatePlanDisplay(data) {
  if (!data) return;
  const section = document.getElementById("planSection");
  const container = document.getElementById("planDisplay");
  if (!section || !container) return;

  // Show the plan section
  section.style.display = "block";

  const title = data.title || "Research Plan";
  const subtasks = data.subtasks || [];
  const progress = data.progress || 0;

  let html = `<div class="plan-title">${escapeHtml(title)}</div>`;
  html += `<div class="plan-progress-bar"><div class="plan-progress-fill" style="width: ${progress * 100}%"></div></div>`;
  html += `<div class="plan-subtasks">`;

  subtasks.forEach(st => {
    const statusClass = st.status === "done" ? "done" : st.status === "in_progress" ? "active" : "pending";
    const icon = st.status === "done" ? "&#10003;" : st.status === "in_progress" ? "&#9654;" : "&#9675;";
    html += `<div class="plan-subtask ${statusClass}">
      <span class="plan-subtask-icon">${icon}</span>
      <span class="plan-subtask-name">${escapeHtml(st.name)}</span>
    </div>`;
  });

  html += `</div>`;
  container.innerHTML = html;
}

// ============================================================
// Boot
// ============================================================

connectWS();
updateStatusUI();
onStateChange("idle", true);
gameLoop();
