// ===== WebSocket 连接 =====
const socket = io();

socket.on("connect", () => {
  document.getElementById("ws-status").className = "dot dot-green";
  document.getElementById("ws-status-text").textContent = "已连接";
  // 连接后立即拉取状态
  fetchStatus();
});

socket.on("disconnect", () => {
  document.getElementById("ws-status").className = "dot dot-red";
  document.getElementById("ws-status-text").textContent = "连接断开";
});

// ===== 实时事件 =====

socket.on("login_result", (data) => {
  if (data.success) {
    toast("登录成功: " + data.nickname, "success");
    fetchStatus();
  } else {
    toast("登录失败: " + data.message, "error");
    // 隐藏QR码
    document.getElementById("qr-section").style.display = "none";
  }
});

socket.on("status_update", (data) => {
  updateUI(data);
});

socket.on("new_message", (msg) => {
  appendLog(msg);
});

// 登录状态变更（confirmed / failed）
socket.on("login_status", (data) => {
  const statusEl = document.getElementById("qr-status");
  if (!statusEl) return;

  switch (data.status) {
    case "confirmed":
      statusEl.textContent = "登录确认成功";
      statusEl.className = "qr-status qr-status-confirmed";
      break;
    case "failed":
      statusEl.textContent = "登录失败，请重试";
      statusEl.className = "qr-status qr-status-expired";
      break;
  }
});

// ===== API 调用 =====

async function apiCall(url, method = "GET", body = null) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  return res.json();
}

async function fetchStatus() {
  const data = await apiCall("/api/status");
  updateUI(data);
  // 同时拉取课表
  fetchSchedule();
}

async function fetchSchedule() {
  const data = await apiCall("/api/livestream/schedule");
  renderSchedule(data.schedule || []);
  const nextEl = document.getElementById("next-notify");
  const status = await apiCall("/api/status");
  if (status.livestream && status.livestream.next_notification) {
    const n = status.livestream.next_notification;
    nextEl.textContent = "⏰ 下次通知: " + n.next_run + " (" + n.content + ")";
  } else {
    nextEl.textContent = "";
  }
}

// ===== 登录 =====

function doLogin() {
  const btn = document.getElementById("btn-login");
  btn.disabled = true;
  btn.textContent = "登录中...";

  // 显示QR码区域，提示用户在弹出的图片查看器中扫码
  const qrSection = document.getElementById("qr-section");
  qrSection.style.display = "block";

  const statusEl = document.getElementById("qr-status");
  if (statusEl) {
    statusEl.textContent = "二维码已在弹出的图片查看器中显示，请用微信扫描";
    statusEl.className = "qr-status qr-status-waiting";
  }

  // 隐藏网页上的二维码图片（不再使用）
  const qrImg = document.getElementById("qr-image");
  if (qrImg) qrImg.style.display = "none";

  apiCall("/api/login", "POST").then((data) => {
    if (!data.success) {
      toast(data.message, "error");
      btn.disabled = false;
      btn.textContent = "登录微信";
      qrSection.style.display = "none";
    }
    // 成功时 status=202，登录结果由 login_result 事件推送
  });
}

function doLogout() {
  apiCall("/api/logout", "POST").then((data) => {
    if (data.success) {
      toast("已退出登录", "info");
      fetchStatus();
    }
  });
}

// ===== 自动回复 =====

function toggleAutoReply() {
  const checked = document.getElementById("auto-reply-switch").checked;
  apiCall("/api/auto-reply/toggle", "POST", { enabled: checked }).then((data) => {
    if (data.success) {
      toast("自动回复已" + (data.auto_reply ? "开启" : "关闭"), "info");
    }
  });
}

// ===== 直播状态 =====

function toggleLiveStatus() {
  const checked = document.getElementById("live-switch").checked;
  const activity = document.getElementById("live-activity").value;
  apiCall("/api/livestream/status", "POST", {
    is_live: checked,
    activity: activity,
  }).then((data) => {
    if (data.success) {
      toast(data.is_live ? "已开播" : "已下播", "info");
    }
  });
}

function updateLiveActivity() {
  const activity = document.getElementById("live-activity").value;
  const isLive = document.getElementById("live-switch").checked;
  if (!isLive) {
    toast("请先开播再设置活动", "error");
    return;
  }
  apiCall("/api/livestream/status", "POST", {
    is_live: true,
    activity: activity,
  }).then((data) => {
    if (data.success) toast("活动已更新", "success");
  });
}

// ===== 课表管理 =====

function addSchedule() {
  const day = document.getElementById("sched-day").value;
  const time = document.getElementById("sched-time").value;
  const content = document.getElementById("sched-content").value.trim();

  if (!time) {
    toast("请选择时间", "error");
    return;
  }

  apiCall("/api/livestream/schedule", "POST", { day, time, content }).then((data) => {
    if (data.success) {
      toast("已添加: " + day + " " + time, "success");
      document.getElementById("sched-content").value = "";
      fetchSchedule();
    } else {
      toast(data.message, "error");
    }
  });
}

function deleteSchedule(id) {
  apiCall("/api/livestream/schedule/" + id, "DELETE").then((data) => {
    if (data.success) {
      toast("已删除", "info");
      fetchSchedule();
    }
  });
}

function renderSchedule(list) {
  const el = document.getElementById("schedule-list");
  if (!list.length) {
    el.innerHTML = '<p class="tip">暂无直播安排，添加一个吧~</p>';
    return;
  }
  el.innerHTML = list
    .map(
      (item) => `
    <div class="sched-item">
      <div class="sched-info">
        <span class="sched-day">${item.day}</span>
        <span class="sched-time">${item.time}</span>
        <span class="sched-content">${item.content || ""}</span>
      </div>
      <button class="sched-del" onclick="deleteSchedule('${item.id}')" title="删除">×</button>
    </div>
  `
    )
    .join("");
}

// ===== 手动通知 =====

function sendNotify() {
  const content = document.getElementById("notify-content").value.trim();
  if (!content) {
    toast("请输入通知内容", "error");
    return;
  }
  apiCall("/api/livestream/notify", "POST", { content }).then((data) => {
    if (data.success) {
      toast("通知已发送", "success");
      document.getElementById("notify-content").value = "";
    } else {
      toast(data.message, "error");
    }
  });
}

// ===== UI 更新 =====

function updateUI(data) {
  if (!data) return;

  const wc = data.wechat || {};
  const ls = data.livestream || {};

  // 登录状态
  const loginBadge = document.getElementById("login-badge");
  const qrSection = document.getElementById("qr-section");
  const loginInfo = document.getElementById("login-info");
  const btnLogin = document.getElementById("btn-login");
  const btnLogout = document.getElementById("btn-logout");

  if (wc.logged_in) {
    loginBadge.className = "badge badge-green";
    loginBadge.textContent = "已登录";
    qrSection.style.display = "none";
    loginInfo.style.display = "block";
    document.getElementById("login-nickname").textContent = wc.nickname || "未知";
    btnLogin.style.display = "none";
    btnLogout.style.display = "inline-block";
  } else {
    loginBadge.className = "badge badge-gray";
    loginBadge.textContent = "未登录";
    loginInfo.style.display = "none";
    btnLogin.style.display = "inline-block";
    btnLogin.disabled = false;
    btnLogin.textContent = "登录微信";
    btnLogout.style.display = "none";
  }

  // 自动回复状态
  const replyBadge = document.getElementById("reply-badge");
  const replySwitch = document.getElementById("auto-reply-switch");
  replySwitch.checked = wc.auto_reply;
  if (wc.auto_reply) {
    replyBadge.className = "badge badge-green";
    replyBadge.textContent = "已开启";
  } else {
    replyBadge.className = "badge badge-gray";
    replyBadge.textContent = "已关闭";
  }

  // 消息计数
  document.getElementById("msg-count").textContent = data.message_count || 0;

  // 直播状态
  const liveBadge = document.getElementById("live-badge");
  const liveSwitch = document.getElementById("live-switch");
  liveSwitch.checked = ls.is_live;
  if (ls.is_live) {
    liveBadge.className = "badge badge-red";
    liveBadge.textContent = "直播中";
    document.getElementById("live-activity").value = ls.current_activity || "";
  } else {
    liveBadge.className = "badge badge-gray";
    liveBadge.textContent = "未开播";
  }
}

// ===== 日志 =====

function appendLog(msg) {
  const el = document.getElementById("log-area");
  // 移除 "等待消息..." 提示
  if (el.querySelector(".tip")) el.innerHTML = "";

  const typeMap = { receive: "收到", reply: "回复", notify: "通知" };
  const typeClass = "type-" + msg.type;

  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.innerHTML = `<span class="time">${msg.time}</span><span class="type ${typeClass}">[${typeMap[msg.type] || msg.type}]</span><span class="nickname">${msg.nickname}</span><span>${msg.content}</span>`;

  el.appendChild(entry);
  el.scrollTop = el.scrollHeight;

  // 最多保留200条
  while (el.children.length > 200) el.removeChild(el.firstChild);
}

function clearLogs() {
  document.getElementById("log-area").innerHTML = '<p class="tip">等待消息...</p>';
}

// ===== Toast 通知 =====

(function createToastContainer() {
  const c = document.createElement("div");
  c.className = "toast-container";
  c.id = "toast-container";
  document.body.appendChild(c);
})();

function toast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = "toast toast-" + type;
  el.textContent = message;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transition = "opacity 0.3s";
    setTimeout(() => el.remove(), 300);
  }, 3000);
}

// ===== 初始化 =====
fetchStatus();
