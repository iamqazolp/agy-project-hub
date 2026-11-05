(function () {
  const vscode = acquireVsCodeApi();

  const LANE_COLORS = [
    "#3b82f6", // blue
    "#10b981", // emerald
    "#a855f7", // purple
    "#f59e0b", // amber
    "#06b6d4", // cyan
    "#ec4899", // pink
    "#84cc16"  // lime
  ];

  const ICONS = {
    trace: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M1.5 2.75a1.25 1.25 0 1 1 2.5 0 1.25 1.25 0 0 1-2.5 0ZM2.75 0a2.75 2.75 0 0 0-.75 5.396v5.208a2.75 2.75 0 1 0 1.5 0V8.75h5.25A2.75 2.75 0 0 0 11.496 6.5h.608a2.75 2.75 0 1 0 0-1.5h-.608A2.75 2.75 0 0 0 8.75 2.75H5.396A2.751 2.751 0 0 0 2.75 0Zm0 12a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Zm11.25-7.5a1.25 1.25 0 1 1 0 2.5 1.25 1.25 0 0 1 0-2.5Z"/></svg>`,
    branch: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.5 0v1.836A2.493 2.493 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/></svg>`,
    terminal: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M0 2.75C0 1.784.784 1 1.75 1h12.5c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 14.25 15H1.75A1.75 1.75 0 0 1 0 13.25Zm1.75-.25a.25.25 0 0 0-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25V2.75a.25.25 0 0 0-.25-.25ZM7.25 8a.749.749 0 0 1-.22.53l-2.25 2.25a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L5.44 8 3.72 6.28a.749.749 0 0 1 .326-1.275.749.749 0 0 1 .734.215l2.25 2.25c.141.14.22.331.22.53Zm1.5 1.5h3a.75.75 0 0 1 0 1.5h-3a.75.75 0 0 1 0-1.5Z"/></svg>`,
    copy: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg>`,
    file: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg>`,
    refresh: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z"/></svg>`,
    table: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v12.5A1.75 1.75 0 0 1 14.25 16H1.75A1.75 1.75 0 0 1 0 14.25ZM1.5 6.5v7.75c0 .138.112.25.25.25H6v-8Zm6 8h6.75a.25.25 0 0 0 .25-.25V6.5H7.5ZM14.5 5V1.75a.25.25 0 0 0-.25-.25H1.75a.25.25 0 0 0-.25.25V5Z"/></svg>`
  };

  let state = {
    payload: window.__INITIAL_PAYLOAD__ || null,
    mainView: "trace",        // "trace" | "table" | "repo"
    selectedSessionId: "",
    treeFilterType: "all",    // "all" | "root" | "fork" | "agent"
    treeSearch: "",
    railDrawerTab: "docs",    // "docs" | "hot"
    bottomSplitMode: "split", // "split" | "prompts" | "git"
    promptScope: "selected",  // "selected" | "all"
    promptSearch: "",
    selectedGitNode: "",
    commitDetailsCache: {}
  };

  let chartResizeObserver = null;

  function fmtTokens(n) {
    const val = Number(n) || 0;
    if (val >= 1000000) return (val / 1000000).toFixed(2) + "M";
    if (val >= 1000) return (val / 1000).toFixed(1) + "k";
    return String(val);
  }

  function esc(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showToast(msg) {
    const el = document.getElementById("hub-toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("visible");
    clearTimeout(el._timer);
    el._timer = setTimeout(() => el.classList.remove("visible"), 1500);
  }

  function getSelectedSession() {
    if (!state.payload || !Array.isArray(state.payload.sessions)) return null;
    const list = state.payload.sessions;
    if (!list.length) return null;
    const found = list.find((s) => s.id === state.selectedSessionId);
    if (found) return found;
    const active = list.find((s) => s.id === state.payload.activeSessionId);
    const chosen = active || list[0];
    state.selectedSessionId = chosen.id;
    return chosen;
  }

  function getSessionBadgeHtml(s) {
    if (s.isSubagent) {
      return `<span class="lf-badge lf-badge-agent">AGENT${s.forkStep !== null && s.forkStep !== undefined ? ` @${s.forkStep}` : ""}</span>`;
    }
    if (s.parentId) {
      return `<span class="lf-badge lf-badge-fork">FORK @#${s.forkStep ?? "?"}</span>`;
    }
    return `<span class="lf-badge lf-badge-trace">TRACE #${s.treeNum || 1}</span>`;
  }

  /* ------------------------------------------------------------------
   * Hierarchical Tree Ordering (Root -> Child Forks & Subagents)
   * ------------------------------------------------------------------ */
  function buildHierarchicalSessions(sessions) {
    const byId = new Map();
    sessions.forEach((s) => byId.set(s.id, s));

    const childrenMap = new Map();
    const roots = [];
    for (const s of sessions) {
      if (s.parentId && byId.has(s.parentId) && s.parentId !== s.id) {
        if (!childrenMap.has(s.parentId)) childrenMap.set(s.parentId, []);
        childrenMap.get(s.parentId).push(s);
      } else {
        roots.push(s);
      }
    }

    const result = [];
    const visited = new Set();

    function walk(node, depth) {
      if (visited.has(node.id)) return;
      visited.add(node.id);
      result.push({ session: node, depth: Math.min(2, depth) });
      const kids = childrenMap.get(node.id) || [];
      kids.sort((a, b) => (a.firstStep || 0) - (b.firstStep || 0));
      for (const k of kids) {
        walk(k, depth + 1);
      }
    }

    for (const r of roots) {
      walk(r, 0);
    }
    for (const s of sessions) {
      if (!visited.has(s.id)) {
        walk(s, s.parentId ? 1 : 0);
      }
    }
    return result;
  }

  /* ------------------------------------------------------------------
   * Langfuse 1:1 Pixel-Accurate Context & Cache Trajectory SVG Chart
   * ------------------------------------------------------------------ */
  function drawLangfuseTrajectoryChart(sess) {
    const container = document.getElementById("lf-chart-container");
    if (!container) return;

    if (!sess || !Array.isArray(sess.trajectory) || sess.trajectory.length === 0) {
      container.innerHTML = `<div style="padding:26px;text-align:center;color:var(--lf-fg-subtle);font-family:var(--lf-font-mono);font-size:11px;">No token observations recorded for this trace.</div>`;
      return;
    }

    const rect = container.getBoundingClientRect();
    const W = Math.max(320, Math.round(rect.width || 680));
    const H = Math.max(96, Math.round(rect.height || 126));
    const padL = 44;
    const padR = 14;
    const padT = 10;
    const padB = 18;
    const plotW = Math.max(40, W - padL - padR);
    const plotH = Math.max(30, H - padT - padB);

    const pts = sess.trajectory;
    const minStep = pts[0].step;
    const maxStep = Math.max(minStep + 1, pts[pts.length - 1].step);
    const peakTok = Math.max(265000, sess.peakCtxTokens || 0, ...pts.map((p) => p.tokens));
    const maxY = Math.ceil(peakTok / 50000) * 50000;

    const xOf = (step) => padL + ((step - minStep) / Math.max(1, maxStep - minStep)) * plotW;
    const yOf = (tok) => padT + plotH - (Math.min(maxY, Math.max(0, tok)) / maxY) * plotH;
    const yBase = (padT + plotH).toFixed(1);

    const gridLevels = [128000, 256000].filter((v) => v <= maxY);
    const gridLines = gridLevels
      .map((gv) => {
        const y = yOf(gv).toFixed(1);
        const isCeiling = gv === 256000;
        const stroke = isCeiling ? "var(--lf-amber)" : "var(--lf-border-strong)";
        const dash = isCeiling ? 'stroke-dasharray="4 3"' : 'stroke-dasharray="2 3"';
        const fill = isCeiling ? "var(--lf-amber)" : "var(--lf-fg-subtle)";
        const label = isCeiling ? "256k" : "128k";
        return `
          <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${stroke}" stroke-width="1" ${dash} opacity="${isCeiling ? 0.85 : 0.45}" />
          <text x="${padL - 6}" y="${Number(y) + 3.5}" text-anchor="end" font-family="var(--lf-font-mono)" font-size="9.5" fill="${fill}">${label}</text>
        `;
      })
      .join("");

    const inheritedPts = pts.filter((p) => p.inherited);
    const ownPts = pts.filter((p) => !p.inherited);
    if (inheritedPts.length > 0 && ownPts.length > 0) {
      ownPts.unshift(inheritedPts[inheritedPts.length - 1]);
    }

    const buildPath = (arr, accessor) => {
      if (!arr.length) return "";
      if (arr.length === 1) {
        const x = xOf(arr[0].step).toFixed(1);
        const y = yOf(accessor(arr[0])).toFixed(1);
        return `M ${x} ${y} L ${Number(x) + 1} ${y}`;
      }
      return arr
        .map((p, idx) => `${idx === 0 ? "M" : "L"} ${xOf(p.step).toFixed(1)} ${yOf(accessor(p)).toFixed(1)}`)
        .join(" ");
    };

    const buildArea = (arr, accessor) => {
      if (arr.length < 2) return "";
      const lineD = buildPath(arr, accessor);
      const firstX = xOf(arr[0].step).toFixed(1);
      const lastX = xOf(arr[arr.length - 1].step).toFixed(1);
      return `${lineD} L ${lastX} ${yBase} L ${firstX} ${yBase} Z`;
    };

    const inhLine = buildPath(inheritedPts, (p) => p.tokens);
    const inhArea = buildArea(inheritedPts, (p) => p.tokens);
    const ownLine = buildPath(ownPts, (p) => p.tokens);
    const ownArea = buildArea(ownPts, (p) => p.tokens);

    // Cache Read sub-curve across all points
    const hasCacheData = pts.some((p) => (p.cacheTokens || 0) > 0);
    const cacheLine = hasCacheData ? buildPath(pts, (p) => p.cacheTokens || 0) : "";
    const cacheArea = hasCacheData ? buildArea(pts, (p) => p.cacheTokens || 0) : "";

    let forkMarker = "";
    if (sess.parentId && sess.forkStep !== null && sess.forkStep !== undefined) {
      const fx = xOf(sess.forkStep).toFixed(1);
      forkMarker = `
        <line x1="${fx}" y1="${padT}" x2="${fx}" y2="${yBase}" stroke="var(--lf-purple)" stroke-width="1.2" stroke-dasharray="3 3" />
        <text x="${Number(fx) + 4}" y="${padT + 9}" font-family="var(--lf-font-mono)" font-size="9" font-weight="600" fill="var(--lf-purple)">FORK @#${sess.forkStep}</text>
      `;
    }

    const compactMarkers = pts
      .filter((p) => p.compacted)
      .map((p) => {
        const cx = xOf(p.step).toFixed(1);
        const cy = yOf(p.tokens).toFixed(1);
        return `
          <line x1="${cx}" y1="${padT}" x2="${cx}" y2="${yBase}" stroke="var(--lf-rose)" stroke-width="1" stroke-dasharray="2 2" opacity="0.65" />
          <circle cx="${cx}" cy="${cy}" r="3.2" fill="var(--lf-rose)" stroke="var(--lf-bg)" stroke-width="1.2" />
        `;
      })
      .join("");

    const lastPt = pts[pts.length - 1];
    const lx = xOf(lastPt.step).toFixed(1);
    const ly = yOf(lastPt.tokens).toFixed(1);
    const midStep = Math.round((minStep + maxStep) / 2);

    container.innerHTML = `
      <svg class="lf-chart-svg" id="lf-chart-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        <defs>
          <linearGradient id="lfOwnFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--lf-blue)" stop-opacity="0.24"/>
            <stop offset="100%" stop-color="var(--lf-blue)" stop-opacity="0.01"/>
          </linearGradient>
          <linearGradient id="lfInhFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--lf-purple)" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="var(--lf-purple)" stop-opacity="0.01"/>
          </linearGradient>
          <linearGradient id="lfCacheFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--lf-emerald)" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="var(--lf-emerald)" stop-opacity="0.02"/>
          </linearGradient>
        </defs>
        <line x1="${padL}" y1="${yBase}" x2="${W - padR}" y2="${yBase}" stroke="var(--lf-border-strong)" stroke-width="1" />
        ${gridLines}
        ${inhArea ? `<path d="${inhArea}" fill="url(#lfInhFill)" />` : ""}
        ${ownArea ? `<path d="${ownArea}" fill="url(#lfOwnFill)" />` : ""}
        ${cacheArea ? `<path d="${cacheArea}" fill="url(#lfCacheFill)" />` : ""}
        ${cacheLine ? `<path d="${cacheLine}" fill="none" stroke="var(--lf-emerald)" stroke-width="1.15" stroke-dasharray="2 2" opacity="0.8" />` : ""}
        ${inhLine ? `<path d="${inhLine}" fill="none" stroke="var(--lf-purple)" stroke-width="1.6" stroke-dasharray="4 3" />` : ""}
        ${ownLine ? `<path d="${ownLine}" fill="none" stroke="var(--lf-blue)" stroke-width="1.8" stroke-linejoin="round" />` : ""}
        ${forkMarker}
        ${compactMarkers}
        <circle cx="${lx}" cy="${ly}" r="3.4" fill="var(--lf-blue)" stroke="var(--lf-bg)" stroke-width="1.4" />
        <line id="lf-hover-line" x1="0" y1="${padT}" x2="0" y2="${yBase}" stroke="var(--lf-fg-muted)" stroke-width="1" stroke-dasharray="2 2" style="display:none;" />
        <circle id="lf-hover-dot" cx="0" cy="0" r="3.8" fill="var(--lf-blue)" stroke="var(--lf-bg)" stroke-width="1.5" style="display:none;" />
        <text x="${padL}" y="${H - 4}" text-anchor="start" font-family="var(--lf-font-mono)" font-size="9.5" fill="var(--lf-fg-subtle)">step #${minStep}</text>
        <text x="${xOf(midStep).toFixed(1)}" y="${H - 4}" text-anchor="middle" font-family="var(--lf-font-mono)" font-size="9.5" fill="var(--lf-fg-subtle)">step #${midStep}</text>
        <text x="${W - padR}" y="${H - 4}" text-anchor="end" font-family="var(--lf-font-mono)" font-size="9.5" fill="var(--lf-fg-subtle)">step #${maxStep}</text>
      </svg>
      <div class="lf-chart-tooltip" id="lf-chart-tooltip"></div>
    `;

    const svg = document.getElementById("lf-chart-svg");
    const tooltip = document.getElementById("lf-chart-tooltip");
    const hoverLine = document.getElementById("lf-hover-line");
    const hoverDot = document.getElementById("lf-hover-dot");
    if (!svg || !tooltip) return;

    svg.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect();
      const relX = ev.clientX - r.left;
      const targetStep = minStep + ((relX - padL) / Math.max(1, plotW)) * (maxStep - minStep);

      let nearest = pts[0];
      let bestDist = Math.abs(nearest.step - targetStep);
      for (const p of pts) {
        const d = Math.abs(p.step - targetStep);
        if (d < bestDist) {
          bestDist = d;
          nearest = p;
        }
      }

      const cx = xOf(nearest.step);
      const cy = yOf(nearest.tokens);
      hoverLine.setAttribute("x1", cx.toFixed(1));
      hoverLine.setAttribute("x2", cx.toFixed(1));
      hoverLine.style.display = "block";
      hoverDot.setAttribute("cx", cx.toFixed(1));
      hoverDot.setAttribute("cy", cy.toFixed(1));
      hoverDot.style.display = "block";

      const pct = Math.round((nearest.tokens / 256000) * 100);
      const stateTag = nearest.compacted
        ? `<span style="color:var(--lf-rose);">COMPACTED</span>`
        : nearest.inherited
        ? `<span style="color:var(--lf-purple);">INHERITED</span>`
        : `<span style="color:var(--lf-blue);">ACTIVE</span>`;
      const toolsStr =
        Array.isArray(nearest.tools) && nearest.tools.length
          ? nearest.tools.slice(0, 3).join(", ")
          : "";

      tooltip.innerHTML = `
        <div class="lf-tt-head">
          <span>Step #${nearest.step}</span>
          ${stateTag}
        </div>
        <div class="lf-tt-row"><span>Context Total</span><strong>${fmtTokens(nearest.tokens)} (${pct}%)</strong></div>
        ${
          nearest.cacheTokens !== undefined
            ? `<div class="lf-tt-row"><span>Cache / Input</span><strong>${fmtTokens(nearest.cacheTokens)} / ${fmtTokens(nearest.inputTokens || 0)}</strong></div>`
            : ""
        }
        ${
          nearest.outputTokens
            ? `<div class="lf-tt-row"><span>Step Output</span><strong>+${fmtTokens(nearest.outputTokens)}</strong></div>`
            : ""
        }
        ${
          toolsStr
            ? `<div class="lf-tt-row"><span>Tools</span><strong style="color:var(--lf-cyan);">${esc(toolsStr)}</strong></div>`
            : ""
        }
      `;
      tooltip.style.display = "block";
      const leftPx = Math.min(W - 205, Math.max(8, relX + 12));
      const topPx = Math.max(4, Math.min(H - 95, ev.clientY - r.top - 36));
      tooltip.style.left = leftPx + "px";
      tooltip.style.top = topPx + "px";
    });

    svg.addEventListener("mouseleave", () => {
      hoverLine.style.display = "none";
      hoverDot.style.display = "none";
      tooltip.style.display = "none";
    });
  }

  /* ------------------------------------------------------------------
   * Deduplicated Ref Badges & Topological Swimlane Git Graph
   * ------------------------------------------------------------------ */
  function parseCleanRefBadges(rawRefs) {
    if (!rawRefs) return [];
    const cleaned = String(rawRefs).replace(/^\s*\(|\)\s*$/g, "").trim();
    if (!cleaned) return [];

    const parts = cleaned
      .split(",")
      .map((r) => r.trim())
      .filter((r) => r && r !== "origin/HEAD");

    const localBranches = new Set();
    for (const p of parts) {
      if (p.startsWith("HEAD -> ")) {
        localBranches.add(p.slice(8).trim());
      } else if (!p.startsWith("tag:") && !p.includes("/") && p !== "HEAD") {
        localBranches.add(p);
      }
    }

    const badges = [];
    for (const p of parts) {
      if (p.startsWith("HEAD -> ")) {
        const bName = p.slice(8).trim();
        const hasRemote = parts.includes(`origin/${bName}`);
        badges.push({
          text: hasRemote ? `${bName} ⇅` : bName,
          cls: "lf-badge-gen",
          isHead: true
        });
      } else if (p === "HEAD") {
        badges.push({ text: "HEAD", cls: "lf-badge-gen", isHead: true });
      } else if (p.startsWith("tag:")) {
        badges.push({
          text: p.replace(/^tag:\s*/, ""),
          cls: "lf-badge-warn",
          isHead: false
        });
      } else if (p.startsWith("origin/")) {
        const shortRemote = p.slice(7);
        if (localBranches.has(shortRemote)) continue;
        badges.push({ text: p, cls: "lf-badge-fork", isHead: false });
      } else {
        const hasRemote = parts.includes(`origin/${p}`);
        badges.push({
          text: hasRemote ? `${p} ⇅` : p,
          cls: "lf-badge-fork",
          isHead: false
        });
      }
    }
    return badges;
  }

  function computeGitGraphLayout(git) {
    const rawCommits = (git && (git.graphCommits || git.commits)) || [];
    const dirtyCount =
      (git?.modified || 0) +
      (git?.added || 0) +
      (git?.deleted || 0) +
      (git?.untracked || 0);

    const nodes = [];
    if (dirtyCount > 0 && rawCommits.length > 0) {
      const headCommit =
        rawCommits.find((c) => String(c.refs || "").includes("HEAD")) || rawCommits[0];
      const diffLabel =
        git.insertions || git.deletions
          ? ` (+${git.insertions || 0} / -${git.deletions || 0})`
          : "";
      nodes.push({
        sha: "WIP",
        parents: headCommit ? [headCommit.sha] : [],
        date: "working tree",
        author: "local",
        refs: "",
        subject: `${dirtyCount} uncommitted file${dirtyCount === 1 ? "" : "s"}${diffLabel}`,
        isWip: true,
        badges: [{ text: "WIP", cls: "lf-badge-warn", isHead: false }]
      });
    }

    for (const c of rawCommits) {
      if (!c.subject && !c.refs) continue;
      nodes.push({
        sha: c.sha,
        parents: Array.isArray(c.parents) ? c.parents : [],
        date: c.date || "",
        author: c.author || "",
        refs: c.refs || "",
        subject: c.subject || "(no message)",
        isWip: false,
        badges: parseCleanRefBadges(c.refs)
      });
    }

    const rowBySha = new Map();
    nodes.forEach((n, idx) => rowBySha.set(n.sha, idx));

    const activeLanes = [];
    const laneColorByCol = [];
    let nextColorCounter = 0;

    function allocLane(targetSha, preferredColor) {
      let idx = activeLanes.indexOf(null);
      if (idx === -1) {
        idx = activeLanes.length;
        activeLanes.push(targetSha);
      } else {
        activeLanes[idx] = targetSha;
      }
      laneColorByCol[idx] =
        preferredColor || LANE_COLORS[nextColorCounter++ % LANE_COLORS.length];
      return idx;
    }

    let maxCol = 0;
    for (let r = 0; r < nodes.length; r++) {
      const node = nodes[r];
      const matchingCols = [];
      for (let c = 0; c < activeLanes.length; c++) {
        if (activeLanes[c] === node.sha) {
          matchingCols.push(c);
        }
      }

      let col;
      if (matchingCols.length > 0) {
        col = matchingCols[0];
        for (let i = 1; i < matchingCols.length; i++) {
          activeLanes[matchingCols[i]] = null;
        }
      } else {
        col = allocLane(node.sha, node.isWip ? "var(--lf-amber)" : undefined);
      }

      node.col = col;
      node.color = node.isWip ? "var(--lf-amber)" : laneColorByCol[col] || LANE_COLORS[0];
      if (col > maxCol) maxCol = col;

      const knownParents = (node.parents || []).filter((p) => rowBySha.has(p));
      if (knownParents.length === 0) {
        activeLanes[col] = null;
      } else {
        const p0 = knownParents[0];
        if (node.isWip) {
          laneColorByCol[col] = LANE_COLORS[0];
        }
        activeLanes[col] = p0;

        for (let pi = 1; pi < knownParents.length; pi++) {
          const pm = knownParents[pi];
          if (!activeLanes.includes(pm)) {
            const mCol = allocLane(pm);
            if (mCol > maxCol) maxCol = mCol;
          }
        }
      }
    }

    return { nodes, rowBySha, maxCol };
  }

  function renderGitPaneBody(git) {
    const { nodes, rowBySha, maxCol } = computeGitGraphLayout(git);
    if (!nodes.length) {
      return `<div style="padding:20px;text-align:center;color:var(--lf-fg-subtle);">No commits found.</div>`;
    }

    if (!state.selectedGitNode || !rowBySha.has(state.selectedGitNode)) {
      state.selectedGitNode = nodes[0].sha;
      if (state.selectedGitNode !== "WIP" && !state.commitDetailsCache[state.selectedGitNode]) {
        vscode.postMessage({ type: "inspectCommit", sha: state.selectedGitNode });
      }
    }

    const ROW_H = 25;
    const COL_W = 14;
    const PAD_X = 12;
    const svgW = Math.max(26, (maxCol + 1) * COL_W + PAD_X * 2);
    const svgH = nodes.length * ROW_H;

    const xOfCol = (col) => PAD_X + col * COL_W;
    const yOfRow = (row) => row * ROW_H + ROW_H / 2;

    const edgePaths = [];
    for (let r = 0; r < nodes.length; r++) {
      const n = nodes[r];
      const x1 = xOfCol(n.col);
      const y1 = yOfRow(r);

      for (let pi = 0; pi < (n.parents || []).length; pi++) {
        const pSha = n.parents[pi];
        const pRow = rowBySha.get(pSha);
        if (pRow === undefined) continue;
        const pNode = nodes[pRow];
        const x2 = xOfCol(pNode.col);
        const y2 = yOfRow(pRow);
        const dash = n.isWip ? 'stroke-dasharray="3 2"' : "";
        const edgeColor =
          n.isWip
            ? "var(--lf-amber)"
            : pi === 0
            ? n.color
            : pNode.color || LANE_COLORS[(n.col + pi) % LANE_COLORS.length];

        let d = "";
        if (x1 === x2) {
          d = `M ${x1} ${y1} L ${x2} ${y2}`;
        } else if (pi > 0 && x2 > x1) {
          const bendY = Math.min(y2, y1 + ROW_H);
          d = `M ${x1} ${y1} C ${x1} ${y1 + 10}, ${x2} ${bendY - 10}, ${x2} ${bendY} L ${x2} ${y2}`;
        } else {
          const bendY = Math.max(y1, y2 - ROW_H);
          d = `M ${x1} ${y1} L ${x1} ${bendY} C ${x1} ${bendY + 10}, ${x2} ${y2 - 10}, ${x2} ${y2}`;
        }
        edgePaths.push(
          `<path d="${d}" fill="none" stroke="${edgeColor}" stroke-width="1.6" stroke-linecap="round" ${dash} />`
        );
      }
    }

    const nodeCircles = nodes
      .map((n, r) => {
        const cx = xOfCol(n.col);
        const cy = yOfRow(r);
        const isHead = n.badges.some((b) => b.isHead);
        const isSelected = state.selectedGitNode === n.sha;

        if (n.isWip) {
          return `<circle cx="${cx}" cy="${cy}" r="${isSelected ? 4.4 : 3.8}" fill="var(--lf-bg)" stroke="var(--lf-amber)" stroke-width="1.8" />`;
        }
        if (isHead) {
          return `
            <circle cx="${cx}" cy="${cy}" r="4.8" fill="var(--lf-bg)" stroke="var(--lf-emerald)" stroke-width="1.5" />
            <circle cx="${cx}" cy="${cy}" r="2.3" fill="var(--lf-emerald)" />
          `;
        }
        return `<circle cx="${cx}" cy="${cy}" r="${isSelected ? 4 : 3.1}" fill="${n.color}" stroke="var(--lf-bg)" stroke-width="1.2" />`;
      })
      .join("");

    const rowsHtml = nodes
      .map((n) => {
        const isSel = state.selectedGitNode === n.sha;
        const badgesHtml = n.badges
          .map((b) => `<span class="lf-badge ${b.cls}" style="height:15px;font-size:9px;padding:0 4px;">${esc(b.text)}</span>`)
          .join("");
        const shortDate = n.isWip ? "" : String(n.date || "").slice(5);
        return `
          <div class="lf-git-row ${n.isWip ? "is-wip" : ""} ${isSel ? "selected" : ""}" data-git-node="${esc(n.sha)}">
            <div class="lf-git-row-left">
              ${badgesHtml}
              <span class="lf-git-subject" title="${esc(n.subject)}">${esc(n.subject)}</span>
            </div>
            <div class="lf-git-row-right">
              ${shortDate ? `<span>${esc(shortDate)}</span>` : ""}
              <span class="lf-git-sha" data-copy-sha="${esc(n.sha)}" title="Click to copy SHA">${esc(n.sha)}</span>
            </div>
          </div>
        `;
      })
      .join("");

    let drawerHead = "";
    let drawerFilesHtml = "";
    if (state.selectedGitNode === "WIP") {
      const changed = git.changedFiles || [];
      drawerHead = `
        <span><strong style="color:var(--lf-amber);">WIP Working Tree</strong> · ${changed.length} uncommitted files (+${git.insertions || 0} / -${git.deletions || 0})</span>
        <span>Click file to open</span>
      `;
      drawerFilesHtml = changed.length
        ? changed
            .map((f) => {
              const code = (f.badge || "M")[0].toUpperCase();
              return `
                <div class="lf-diff-item" data-open-file="${esc(f.abs)}" title="${esc(f.rel)} (${esc(f.badge)})">
                  <span class="lf-diff-code lf-diff-${code}">${code}</span>
                  <span class="lf-diff-path">${esc(f.rel)}</span>
                </div>
              `;
            })
            .join("")
        : `<div style="color:var(--lf-fg-subtle);font-size:11px;">Working tree is clean.</div>`;
    } else {
      const selNode = nodes.find((n) => n.sha === state.selectedGitNode);
      const details = state.commitDetailsCache[state.selectedGitNode];
      const files = details ? details.files || [] : [];
      drawerHead = `
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <strong style="color:var(--lf-blue);font-family:var(--lf-font-mono);">${esc(state.selectedGitNode)}</strong>
          · ${esc(selNode ? selNode.subject : "")}
        </span>
        <span style="flex-shrink:0;font-family:var(--lf-font-mono);">${esc(selNode?.author || "")}</span>
      `;
      drawerFilesHtml = !details
        ? `<div style="color:var(--lf-fg-subtle);font-size:10.5px;">Loading commit diff…</div>`
        : files.length
        ? files
            .map(
              (f) => `
            <div class="lf-diff-item" data-open-file="${esc(f.abs)}" title="${esc(f.rel)} (${esc(f.badge)})">
              <span class="lf-diff-code lf-diff-${esc(f.status)}">${esc(f.status)}</span>
              <span class="lf-diff-path">${esc(f.rel)}</span>
            </div>
          `
            )
            .join("")
        : `<div style="color:var(--lf-fg-subtle);font-size:10.5px;">No modified files in commit.</div>`;
    }

    return `
      <div class="lf-git-scroll">
        <div class="lf-git-stage">
          <svg class="lf-git-svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">
            ${edgePaths.join("")}
            ${nodeCircles}
          </svg>
          <div class="lf-git-rows">
            ${rowsHtml}
          </div>
        </div>
      </div>
      <div class="lf-git-drawer">
        <div class="lf-git-drawer-head">${drawerHead}</div>
        <div class="lf-git-drawer-files">${drawerFilesHtml}</div>
      </div>
    `;
  }

  /* ------------------------------------------------------------------
   * View 2: Langfuse Full-Width Traces / Sessions Data Table
   * ------------------------------------------------------------------ */
  function renderTracesTableView(data, selected) {
    const sessions = data.sessions || [];
    const kpis = data.kpis || {};
    const q = (state.treeSearch || "").trim().toLowerCase();

    const filtered = sessions.filter((s) => {
      if (state.treeFilterType === "root" && (s.parentId || s.isSubagent)) return false;
      if (state.treeFilterType === "fork" && (!s.parentId || s.isSubagent)) return false;
      if (state.treeFilterType === "agent" && !s.isSubagent) return false;
      if (q) {
        const hay = `${s.id} ${s.title} ${s.agentName || ""} ${(s.topTools || []).map((t) => t.name).join(" ")}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });

    const rowsHtml = filtered
      .map((s) => {
        const isSel = selected && s.id === selected.id;
        const isAct = s.id === data.activeSessionId;
        const pct256 = Math.min(100, Math.round(((s.currentCtxTokens || 0) / 256000) * 100));
        const cachePct = Math.min(pct256, Math.round(((s.cacheReadTokens || 0) / 256000) * 100));
        const freshPct = Math.max(0, pct256 - cachePct);
        const lineageText = s.isSubagent
          ? `parent ${(s.parentId || "").slice(0, 8)} @#${s.forkStep ?? "?"}`
          : s.parentId
          ? `fork of ${s.parentId.slice(0, 8)} @#${s.forkStep ?? "?"}`
          : `Root Tree #${s.treeNum || 1}`;

        return `
          <tr class="lf-tr-row ${isSel ? "selected" : ""}" data-table-select-sid="${esc(s.id)}">
            <td>${getSessionBadgeHtml(s)}</td>
            <td style="font-family:var(--lf-font-mono);">
              <span style="display:inline-flex;align-items:center;gap:5px;">
                ${isAct ? `<span class="lf-live-dot" title="Active Session"></span>` : ""}
                <strong>${esc(s.shortId)}</strong>
                <span class="lf-badge lf-badge-neutral" style="height:15px;font-size:9px;">${esc((s.source || "cli").toUpperCase())}</span>
              </span>
            </td>
            <td style="max-width:260px;overflow:hidden;text-overflow:ellipsis;" title="${esc(s.title)}">
              <strong>${esc(s.title)}</strong>
            </td>
            <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-muted);">${esc(lineageText)}</td>
            <td style="font-family:var(--lf-font-mono);">
              <div style="display:inline-flex;align-items:center;gap:7px;">
                <div class="lf-dual-bar" style="width:56px;">
                  <div class="lf-dual-bar-seg" style="width:${cachePct}%;background:var(--lf-emerald);"></div>
                  <div class="lf-dual-bar-seg" style="width:${freshPct}%;background:var(--lf-blue);"></div>
                </div>
                <strong>${esc(s.currentCtxFormatted)}</strong>
                <span style="color:var(--lf-fg-subtle);">(${pct256}%)</span>
              </div>
            </td>
            <td style="font-family:var(--lf-font-mono);">
              <span class="lf-badge ${s.cacheHitPct >= 75 ? "lf-badge-gen" : "lf-badge-neutral"}">${s.cacheHitPct || 0}% hit</span>
            </td>
            <td style="font-family:var(--lf-font-mono);">
              <span>${esc(s.peakCtxFormatted)}</span>
              ${s.compactionCount > 0 ? `<span class="lf-badge lf-badge-danger" style="margin-left:4px;">${s.compactionCount}x cmp</span>` : ""}
            </td>
            <td style="font-family:var(--lf-font-mono);">${esc(s.totalOutputFormatted)}</td>
            <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-muted);">
              ${s.stepSpan} steps · ${s.userChats}t · ${s.totalToolCalls || 0} tools
            </td>
            <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-muted);">${esc(s.lastActive)}</td>
            <td>
              <div style="display:inline-flex;align-items:center;gap:4px;">
                <button type="button" class="lf-btn" style="height:21px;padding:0 6px;font-size:10px;" data-resume-sid="${esc(s.id)}" title="Resume in agy CLI">${ICONS.terminal} CLI</button>
                <button type="button" class="lf-icon-btn" data-copy-sid="${esc(s.id)}" title="Copy UUID">${ICONS.copy}</button>
              </div>
            </td>
          </tr>
        `;
      })
      .join("");

    return `
      <div class="lf-table-view">
        <div class="lf-table-toolbar">
          <div style="display:flex;align-items:center;gap:8px;">
            <input type="search" class="lf-input" id="lf-tree-search" style="width:240px;" placeholder="Search traces by title, UUID, tool…" value="${esc(state.treeSearch)}" />
            <div class="lf-seg-group">
              <button type="button" class="lf-seg-btn ${state.treeFilterType === "all" ? "active" : ""}" data-tree-filter="all">All (${sessions.length})</button>
              <button type="button" class="lf-seg-btn ${state.treeFilterType === "root" ? "active" : ""}" data-tree-filter="root">Roots (${kpis.rootTreeCount || 0})</button>
              <button type="button" class="lf-seg-btn ${state.treeFilterType === "fork" ? "active" : ""}" data-tree-filter="fork">Forks (${kpis.forkCount || 0})</button>
              <button type="button" class="lf-seg-btn ${state.treeFilterType === "agent" ? "active" : ""}" data-tree-filter="agent">Agents (${kpis.subagentCount || 0})</button>
            </div>
          </div>
          <div style="font-family:var(--lf-font-mono);font-size:11px;color:var(--lf-fg-muted);">
            Total Output: <strong style="color:var(--lf-fg);">${esc(kpis.totalOutputFormatted || "0")}</strong> · Total Turns: <strong style="color:var(--lf-fg);">${kpis.totalChats || 0}</strong> · Click any row to open Trace Inspector
          </div>
        </div>
        <div class="lf-table-scroll">
          <table class="lf-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Trace ID</th>
                <th>Title</th>
                <th>Lineage</th>
                <th>Context (256k)</th>
                <th>Cache</th>
                <th>Peak / Compact</th>
                <th>Output</th>
                <th>Observations</th>
                <th>Last Active</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml || `<tr><td colspan="11" style="padding:24px;text-align:center;color:var(--lf-fg-subtle);">No traces matching filter.</td></tr>`}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  /* ------------------------------------------------------------------
   * View 3: Git Commit Graph + Synced Knowledge Base Explorer
   * ------------------------------------------------------------------ */
  function renderRepoAndArtifactsView(data) {
    const git = data.git || {};
    const branches = git.branches || [];
    const artifacts = data.artifacts || [];
    const media = data.richMedia || [];
    const hotFiles = data.hotFiles || [];

    const branchChipsHtml = branches
      .map(
        (b) => `
        <span class="lf-branch-chip ${b.active ? "active" : ""}" data-jump-sha="${esc(b.sha)}" title="${esc(b.name)} (${esc(b.sha)})">
          ${ICONS.branch} ${esc(b.name)}
        </span>
      `
      )
      .join("");

    const docRows = artifacts
      .map(
        (d) => `
        <tr class="lf-tr-row" data-open-file="${esc(d.localPath)}">
          <td><span class="lf-badge lf-badge-trace">${esc(d.category.replace(/^[^\w]+/, "").trim() || "DOC")}</span></td>
          <td style="font-family:var(--lf-font-mono);"><strong>${esc(d.name)}</strong></td>
          <td style="max-width:240px;overflow:hidden;text-overflow:ellipsis;color:var(--lf-fg-muted);" title="${esc(d.summary)}">${esc(d.title)}</td>
          <td style="font-family:var(--lf-font-mono);">${d.lineCount}L · ${d.visualCount || 0} viz</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-blue);">${esc((d.originSid || "").slice(0, 8))}</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-subtle);">${esc(d.updatedStr)}</td>
        </tr>
      `
      )
      .join("");

    const mediaRows = media
      .map(
        (m) => `
        <tr class="lf-tr-row" data-open-file="${esc(m.path)}">
          <td><span class="lf-badge lf-badge-agent">${esc((m.ext || "HTML").replace(".", "").toUpperCase())}</span></td>
          <td style="font-family:var(--lf-font-mono);"><strong>${esc(m.name)}</strong></td>
          <td style="color:var(--lf-fg-muted);">${esc(m.relLabel)}</td>
          <td style="font-family:var(--lf-font-mono);">${esc(m.sizeStr)}</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-blue);">${esc((m.originSid || "").slice(0, 8))}</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-subtle);">${esc(m.updatedLocal)}</td>
        </tr>
      `
      )
      .join("");

    const hotRows = hotFiles
      .map(
        (h) => `
        <tr class="lf-tr-row" data-open-file="${esc(h.abs)}">
          <td><span class="lf-badge lf-badge-warn">HOT FILE</span></td>
          <td style="font-family:var(--lf-font-mono);" colspan="2"><strong>${esc(h.rel)}</strong></td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-muted);">Workspace Edit</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-blue);">${esc((h.sessionId || "").slice(0, 8))}</td>
          <td style="font-family:var(--lf-font-mono);color:var(--lf-fg-subtle);">${esc(h.tsLocal)}</td>
        </tr>
      `
      )
      .join("");

    return `
      <div class="lf-repo-view">
        <div class="lf-git-pane" style="border-right:1px solid var(--lf-border);">
          <div class="lf-pane-header">
            <span class="lf-pane-header-title">${ICONS.branch} Git Commit Graph</span>
            <div class="lf-branch-chips">${branchChipsHtml}</div>
          </div>
          ${renderGitPaneBody(git)}
        </div>
        <div class="lf-table-view">
          <div class="lf-pane-header">
            <span class="lf-pane-header-title">${ICONS.file} Synced Knowledge Base (.local-notes/) & Hot Files</span>
            <span class="lf-badge lf-badge-neutral">${artifacts.length + media.length + hotFiles.length} items</span>
          </div>
          <div class="lf-table-scroll">
            <table class="lf-table">
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Artifact / File</th>
                  <th>Title / Path</th>
                  <th>Size / Metrics</th>
                  <th>Origin Trace</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                ${docRows}${mediaRows}${hotRows}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  }

  /* ------------------------------------------------------------------
   * Main Render Entrypoint
   * ------------------------------------------------------------------ */
  function render() {
    const root = document.getElementById("app");
    if (!root) return;
    const data = state.payload;
    if (!data) {
      root.innerHTML = `<div style="padding:32px;text-align:center;color:var(--lf-fg-subtle);font-family:var(--lf-font-mono);">Loading Antigravity Project Hub…</div>`;
      return;
    }

    const ws = data.workspace || {};
    const kpis = data.kpis || {};
    const git = data.git || {};
    const sessions = data.sessions || [];
    const selected = getSelectedSession();
    const activeSess = sessions.find((s) => s.id === data.activeSessionId) || selected;

    const curTok = activeSess ? activeSess.currentCtxTokens : 0;
    const pct256 = Math.min(100, Math.round((curTok / 256000) * 100));
    const cachePctTop = activeSess
      ? Math.min(pct256, Math.round(((activeSess.cacheReadTokens || 0) / 256000) * 100))
      : 0;
    const freshPctTop = Math.max(0, pct256 - cachePctTop);

    // Top Navigation Bar (persistent across all 3 views)
    const topBarHtml = `
      <header class="lf-topbar">
        <div class="lf-topbar-left">
          <div class="lf-breadcrumb">
            <span class="lf-breadcrumb-logo">${ICONS.trace}</span>
            <span>${esc(ws.name || "Workspace")}</span>
            <span class="lf-breadcrumb-sep">/</span>
            <span style="color:var(--lf-fg-muted);font-weight:500;">Langfuse Trace Hub</span>
          </div>
          <span class="lf-badge lf-badge-gen" title="Last synced at ${esc(ws.syncedAt || "")}">
            <span class="lf-live-dot" style="width:5px;height:5px;"></span> LIVE
          </span>
          <nav class="lf-nav-tabs">
            <button type="button" class="lf-nav-tab ${state.mainView === "trace" ? "active" : ""}" data-main-view="trace">
              ${ICONS.trace} Trace Inspector
            </button>
            <button type="button" class="lf-nav-tab ${state.mainView === "table" ? "active" : ""}" data-main-view="table">
              ${ICONS.table} Traces Table <span class="lf-nav-count">${sessions.length}</span>
            </button>
            <button type="button" class="lf-nav-tab ${state.mainView === "repo" ? "active" : ""}" data-main-view="repo">
              ${ICONS.branch} Git & Artifacts <span class="lf-nav-count">${(data.artifacts || []).length}</span>
            </button>
          </nav>
        </div>

        <div class="lf-topbar-right">
          <div class="lf-ctx-meter-pill" title="Active Session Context Window: ${activeSess ? esc(activeSess.cacheReadFormatted || "0") : "0"} cached + ${activeSess ? esc(activeSess.freshInputFormatted || "0") : "0"} fresh / 256k ceiling">
            <span style="color:var(--lf-fg-muted);">Active Ctx</span>
            <strong>${activeSess ? esc(activeSess.currentCtxFormatted) : "0"}</strong>
            <span style="color:var(--lf-fg-subtle);">(${pct256}%)</span>
            <div class="lf-dual-bar">
              <div class="lf-dual-bar-seg" style="width:${cachePctTop}%;background:var(--lf-emerald);"></div>
              <div class="lf-dual-bar-seg" style="width:${freshPctTop}%;background:var(--lf-blue);"></div>
            </div>
          </div>
          ${
            selected
              ? `<button type="button" class="lf-btn lf-btn-primary" data-resume-sid="${esc(selected.id)}">${ICONS.terminal} Resume ${esc(selected.shortId)}</button>`
              : ""
          }
          <button type="button" class="lf-btn" id="btn-open-md">${ICONS.file} PROJECT_HUB.md</button>
          <button type="button" class="lf-btn" id="btn-refresh">${ICONS.refresh} Sync</button>
        </div>
      </header>
    `;

    if (state.mainView === "table") {
      root.innerHTML = topBarHtml + renderTracesTableView(data, selected);
      bindDomEvents();
      return;
    }

    if (state.mainView === "repo") {
      root.innerHTML = topBarHtml + renderRepoAndArtifactsView(data);
      bindDomEvents();
      return;
    }

    /* ----------------------------------------------------------------
     * View 1 (Default): Langfuse Split Trace Inspector Workbench
     * ---------------------------------------------------------------- */
    const hierarchy = buildHierarchicalSessions(sessions);
    const qTree = (state.treeSearch || "").trim().toLowerCase();
    const filteredHierarchy = hierarchy.filter(({ session: s }) => {
      if (state.treeFilterType === "root" && (s.parentId || s.isSubagent)) return false;
      if (state.treeFilterType === "fork" && (!s.parentId || s.isSubagent)) return false;
      if (state.treeFilterType === "agent" && !s.isSubagent) return false;
      if (qTree) {
        const hay = `${s.id} ${s.title} ${s.agentName || ""}`.toLowerCase();
        if (!hay.includes(qTree)) return false;
      }
      return true;
    });

    const treeNodesHtml = filteredHierarchy
      .map(({ session: s, depth }) => {
        const isSel = selected && s.id === selected.id;
        const isAct = s.id === data.activeSessionId;
        const pct = Math.min(100, Math.round(((s.currentCtxTokens || 0) / 256000) * 100));
        const cPct = Math.min(pct, Math.round(((s.cacheReadTokens || 0) / 256000) * 100));
        const fPct = Math.max(0, pct - cPct);
        const depthCls = depth === 1 ? "depth-1" : depth >= 2 ? "depth-2" : "";

        return `
          <div class="lf-tree-node ${depthCls} ${isSel ? "selected" : ""}" data-select-sid="${esc(s.id)}">
            <div class="lf-tree-row1">
              <div class="lf-tree-row1-left">
                ${getSessionBadgeHtml(s)}
                <span class="lf-tree-sid">${esc(s.shortId)}</span>
                ${isAct ? `<span class="lf-live-dot" title="Active Session"></span>` : ""}
              </div>
              <div class="lf-tree-row1-right">
                <span class="lf-tree-actions">
                  <button type="button" class="lf-icon-btn" data-resume-sid="${esc(s.id)}" title="Resume in agy CLI">${ICONS.terminal}</button>
                  <button type="button" class="lf-icon-btn" data-copy-sid="${esc(s.id)}" title="Copy Trace UUID">${ICONS.copy}</button>
                </span>
                <span class="lf-tok-pill">${esc(s.currentCtxFormatted)}</span>
              </div>
            </div>
            <div class="lf-tree-title" title="${esc(s.title)}">${esc(s.title)}</div>
            <div class="lf-tree-row3">
              <span>#${s.firstStep}..#${s.lastStep} · ${s.userChats}t · ${s.cacheHitPct || 0}% cache</span>
              <div class="lf-tree-microbar" title="${pct}% of 256k context ceiling">
                <div class="lf-dual-bar-seg" style="width:${cPct}%;background:var(--lf-emerald);"></div>
                <div class="lf-dual-bar-seg" style="width:${fPct}%;background:var(--lf-blue);"></div>
              </div>
            </div>
          </div>
        `;
      })
      .join("");

    // Left Rail Bottom Drawer (Artifacts vs Hot Files)
    const artifacts = data.artifacts || [];
    const media = data.richMedia || [];
    const hotFiles = data.hotFiles || [];
    let railDrawerItemsHtml = "";
    if (state.railDrawerTab === "docs") {
      const items = [
        ...artifacts.map(
          (d) => `
          <div class="lf-rail-item" data-open-file="${esc(d.localPath)}" title="${esc(d.title)} — ${esc(d.summary)}">
            <span class="lf-rail-item-name">${ICONS.file} ${esc(d.name)}</span>
            <span class="lf-rail-item-meta">${d.lineCount}L</span>
          </div>
        `
        ),
        ...media.map(
          (m) => `
          <div class="lf-rail-item" data-open-file="${esc(m.path)}" title="${esc(m.relLabel)}">
            <span class="lf-rail-item-name">${ICONS.file} ${esc(m.name)}</span>
            <span class="lf-rail-item-meta">${esc(m.sizeStr)}</span>
          </div>
        `
        )
      ];
      railDrawerItemsHtml = items.join("") || `<div style="padding:10px;color:var(--lf-fg-subtle);">No synced artifacts.</div>`;
    } else {
      railDrawerItemsHtml =
        hotFiles
          .map(
            (h) => `
          <div class="lf-rail-item" data-open-file="${esc(h.abs)}" title="Edited in trace ${esc((h.sessionId || "").slice(0, 8))}">
            <span class="lf-rail-item-name">${esc(h.rel)}</span>
            <span class="lf-rail-item-meta">${esc(String(h.tsLocal || "").slice(11))}</span>
          </div>
        `
          )
          .join("") || `<div style="padding:10px;color:var(--lf-fg-subtle);">No recent file edits.</div>`;
    }

    // Selected Trace Header & 5-Column Langfuse Attribute Strip
    const selPct = selected ? Math.min(100, Math.round(((selected.currentCtxTokens || 0) / 256000) * 100)) : 0;
    const selCachePct = selected ? Math.min(selPct, Math.round(((selected.cacheReadTokens || 0) / 256000) * 100)) : 0;
    const selFreshPct = Math.max(0, selPct - selCachePct);
    const topToolsHtml =
      selected && Array.isArray(selected.topTools) && selected.topTools.length
        ? selected.topTools
            .slice(0, 4)
            .map((t) => `<span class="lf-tool-chip">${esc(t.name)} ×${t.count}</span>`)
            .join("")
        : `<span class="lf-attr-sub">No tool calls recorded</span>`;

    // Observations / Prompt Log (Bottom Left of Right Stage)
    let promptsPool = [];
    if (state.promptScope === "selected" && selected) {
      promptsPool = (selected.prompts || []).map((p) => ({
        ...p,
        sessionShort: selected.shortId
      }));
    } else {
      for (const s of sessions) {
        for (const p of s.prompts || []) {
          promptsPool.push({ ...p, sessionShort: s.shortId });
        }
      }
      promptsPool.sort((a, b) =>
        String(b.timestamp || "").localeCompare(String(a.timestamp || ""))
      );
    }
    const qPrompt = (state.promptSearch || "").trim().toLowerCase();
    if (qPrompt) {
      promptsPool = promptsPool.filter(
        (p) =>
          String(p.text || "").toLowerCase().includes(qPrompt) ||
          String(p.sessionShort || "").toLowerCase().includes(qPrompt)
      );
    }

    const obsCardsHtml = promptsPool.length
      ? promptsPool
          .map(
            (p) => `
          <div class="lf-obs-card">
            <div class="lf-obs-card-head">
              <div class="lf-obs-head-left">
                <span class="lf-badge lf-badge-gen" style="height:15px;font-size:9px;">USER_INPUT</span>
                <span>step #${p.step}</span>
                ${p.ctxFormatted ? `<span class="lf-badge lf-badge-neutral" style="height:15px;font-size:9px;">${esc(p.ctxFormatted)} ctx</span>` : ""}
                <span>· ${esc(String(p.timestamp || "").slice(5))}</span>
                <span style="color:var(--lf-blue);">${esc(p.sessionShort)}</span>
              </div>
              <button type="button" class="lf-icon-btn" data-copy-text="${esc(p.text)}" title="Copy input prompt">${ICONS.copy}</button>
            </div>
            <div class="lf-obs-body">${esc(p.text)}</div>
          </div>
        `
          )
          .join("")
      : `<div style="padding:20px;text-align:center;color:var(--lf-fg-subtle);">No prompt observations matching filter.</div>`;

    const branches = git.branches || [];
    const branchChipsHtml = branches
      .map(
        (b) => `
        <span class="lf-branch-chip ${b.active ? "active" : ""}" data-jump-sha="${esc(b.sha)}" title="${esc(b.name)} (${esc(b.sha)})">
          ${ICONS.branch} ${esc(b.name)}
        </span>
      `
      )
      .join("");

    const showPromptsPane = state.bottomSplitMode !== "git";
    const showGitPane = state.bottomSplitMode !== "prompts";
    const splitModeCls =
      state.bottomSplitMode === "prompts"
        ? "mode-prompts"
        : state.bottomSplitMode === "git"
        ? "mode-git"
        : "";

    root.innerHTML = `
      ${topBarHtml}
      <div class="lf-workbench">
        <aside class="lf-tree-pane">
          <div class="lf-pane-header">
            <span class="lf-pane-header-title">Traces & Lineage</span>
            <span class="lf-badge lf-badge-neutral">${filteredHierarchy.length}/${sessions.length}</span>
          </div>
          <div class="lf-tree-filters">
            <input type="search" class="lf-input" id="lf-tree-search" placeholder="Filter traces by title or ID…" value="${esc(state.treeSearch)}" />
            <div class="lf-filter-pills">
              <button type="button" class="lf-filter-pill ${state.treeFilterType === "all" ? "active" : ""}" data-tree-filter="all">All</button>
              <button type="button" class="lf-filter-pill ${state.treeFilterType === "root" ? "active" : ""}" data-tree-filter="root">Roots</button>
              <button type="button" class="lf-filter-pill ${state.treeFilterType === "fork" ? "active" : ""}" data-tree-filter="fork">Forks</button>
              <button type="button" class="lf-filter-pill ${state.treeFilterType === "agent" ? "active" : ""}" data-tree-filter="agent">Agents</button>
            </div>
          </div>
          <div class="lf-tree-scroll">
            ${treeNodesHtml || `<div style="padding:14px;text-align:center;color:var(--lf-fg-subtle);">No matching traces.</div>`}
          </div>
          <div class="lf-rail-drawer">
            <div class="lf-pane-header">
              <div class="lf-mini-tabs">
                <button type="button" class="lf-mini-tab ${state.railDrawerTab === "docs" ? "active" : ""}" data-rail-tab="docs">
                  Artifacts (${artifacts.length + media.length})
                </button>
                <button type="button" class="lf-mini-tab ${state.railDrawerTab === "hot" ? "active" : ""}" data-rail-tab="hot">
                  Hot Files (${hotFiles.length})
                </button>
              </div>
            </div>
            <div class="lf-rail-list">
              ${railDrawerItemsHtml}
            </div>
          </div>
        </aside>

        <main class="lf-stage">
          ${
            selected
              ? `
            <section class="lf-trace-header">
              <div class="lf-trace-toprow">
                <div class="lf-trace-title-group">
                  ${getSessionBadgeHtml(selected)}
                  <span class="lf-trace-title" title="${esc(selected.title)}">${esc(selected.title)}</span>
                  <span class="lf-id-chip" data-copy-sid="${esc(selected.id)}" title="Click to copy full Trace UUID">
                    ID: ${esc(selected.id.slice(0, 13))}… ${ICONS.copy}
                  </span>
                  <span class="lf-badge lf-badge-neutral">${esc((selected.source || "cli").toUpperCase())}</span>
                  ${
                    selected.parentId
                      ? `<span class="lf-id-chip" style="color:var(--lf-purple);border-color:var(--lf-purple-border);" data-select-sid="${esc(selected.parentId)}" title="Click to inspect parent trace ${esc(selected.parentId)}">
                          ↗ Parent: ${esc(selected.parentId.slice(0, 8))} @#${selected.forkStep ?? "?"}
                        </span>`
                      : ""
                  }
                </div>
                <div class="lf-trace-actions">
                  <button type="button" class="lf-btn" data-copy-cmd="${esc(selected.id)}" title="Copy 'agy --conversation ${esc(selected.id)}'">
                    ${ICONS.copy} Copy CLI Cmd
                  </button>
                  <div class="lf-seg-group" title="Switch bottom inspector layout">
                    <button type="button" class="lf-seg-btn ${state.bottomSplitMode === "split" ? "active" : ""}" data-split-mode="split">Split</button>
                    <button type="button" class="lf-seg-btn ${state.bottomSplitMode === "prompts" ? "active" : ""}" data-split-mode="prompts">Prompts</button>
                    <button type="button" class="lf-seg-btn ${state.bottomSplitMode === "git" ? "active" : ""}" data-split-mode="git">Git</button>
                  </div>
                </div>
              </div>

              <div class="lf-attr-strip">
                <div class="lf-attr-cell">
                  <span class="lf-attr-label">Context Window</span>
                  <div class="lf-attr-val">
                    <span>${esc(selected.currentCtxFormatted)}</span>
                    <span style="font-size:10.5px;color:var(--lf-fg-muted);font-weight:500;">/ 256k (${selPct}%)</span>
                  </div>
                  <div class="lf-dual-bar" style="width:100%;margin-top:2px;">
                    <div class="lf-dual-bar-seg" style="width:${selCachePct}%;background:var(--lf-emerald);"></div>
                    <div class="lf-dual-bar-seg" style="width:${selFreshPct}%;background:var(--lf-blue);"></div>
                  </div>
                </div>

                <div class="lf-attr-cell">
                  <span class="lf-attr-label">Cache Efficiency</span>
                  <div class="lf-attr-val">
                    <span style="color:var(--lf-emerald);">${selected.cacheHitPct || 0}% hit</span>
                  </div>
                  <span class="lf-attr-sub">${esc(selected.cacheReadFormatted || "0")} read · ${esc(selected.freshInputFormatted || "0")} fresh</span>
                </div>

                <div class="lf-attr-cell">
                  <span class="lf-attr-label">Peak & Compactions</span>
                  <div class="lf-attr-val">
                    <span>${esc(selected.peakCtxFormatted)}</span>
                    ${
                      selected.compactionCount > 0
                        ? `<span class="lf-badge lf-badge-danger" style="height:15px;font-size:9px;">${selected.compactionCount}x cmp</span>`
                        : `<span class="lf-badge lf-badge-gen" style="height:15px;font-size:9px;">0 cmp</span>`
                    }
                  </div>
                  <span class="lf-attr-sub">${selected.inheritedCompactions > 0 ? `${selected.inheritedCompactions}x pre-fork inherited` : "Within 256k ceiling"}</span>
                </div>

                <div class="lf-attr-cell">
                  <span class="lf-attr-label">Output & Span</span>
                  <div class="lf-attr-val">
                    <span>${esc(selected.totalOutputFormatted)}</span>
                    <span style="font-size:10.5px;color:var(--lf-fg-muted);font-weight:500;">out</span>
                  </div>
                  <span class="lf-attr-sub">#${selected.firstStep}..#${selected.lastStep} (${selected.stepSpan} steps · ${selected.userChats} turns)</span>
                </div>

                <div class="lf-attr-cell">
                  <span class="lf-attr-label">Tool Observations (${selected.totalToolCalls || 0})</span>
                  <div class="lf-tool-chips">${topToolsHtml}</div>
                  <span class="lf-attr-sub">${esc(selected.startedLocal)} → ${esc(selected.lastActive)}</span>
                </div>
              </div>
            </section>
          `
              : ""
          }

          <section class="lf-chart-pane">
            <div class="lf-pane-header">
              <div class="lf-legend">
                <span style="color:var(--lf-fg);font-weight:600;">Context & Cache Trajectory</span>
                <span class="lf-legend-item"><span class="lf-swatch" style="background:var(--lf-blue);"></span> Active Ctx</span>
                <span class="lf-legend-item"><span class="lf-swatch" style="background:var(--lf-emerald);"></span> Cache Read</span>
                ${selected && selected.parentId ? `<span class="lf-legend-item"><span class="lf-swatch" style="background:var(--lf-purple);"></span> Pre-Fork</span>` : ""}
                <span class="lf-legend-item"><span class="lf-swatch" style="background:var(--lf-amber);"></span> 256k Ceiling</span>
                ${selected && selected.compactionCount > 0 ? `<span class="lf-legend-item"><span class="lf-swatch" style="background:var(--lf-rose);"></span> Compaction Drop</span>` : ""}
              </div>
              <span style="font-family:var(--lf-font-mono);font-size:10px;color:var(--lf-fg-subtle);">Hover chart to inspect step tokens & tool calls</span>
            </div>
            <div class="lf-chart-body">
              <div class="lf-chart-container" id="lf-chart-container"></div>
            </div>
          </section>

          <section class="lf-bottom-split ${splitModeCls}">
            ${
              showPromptsPane
                ? `
              <div class="lf-obs-pane">
                <div class="lf-pane-header">
                  <span class="lf-pane-header-title">Prompt Observations (USER_INPUT)</span>
                  <span class="lf-badge lf-badge-neutral">${promptsPool.length} turns</span>
                </div>
                <div class="lf-obs-toolbar">
                  <div class="lf-seg-group">
                    <button type="button" class="lf-seg-btn ${state.promptScope === "selected" ? "active" : ""}" data-prompt-scope="selected">
                      Trace ${selected ? esc(selected.shortId) : ""}
                    </button>
                    <button type="button" class="lf-seg-btn ${state.promptScope === "all" ? "active" : ""}" data-prompt-scope="all">
                      All Traces
                    </button>
                  </div>
                  <input type="search" class="lf-input" id="lf-prompt-search" placeholder="Filter prompt inputs…" value="${esc(state.promptSearch)}" />
                </div>
                <div class="lf-obs-scroll">
                  ${obsCardsHtml}
                </div>
              </div>
            `
                : ""
            }

            ${
              showGitPane
                ? `
              <div class="lf-git-pane">
                <div class="lf-pane-header">
                  <span class="lf-pane-header-title">Git Commit Graph</span>
                  <div class="lf-branch-chips">${branchChipsHtml}</div>
                </div>
                ${renderGitPaneBody(git)}
              </div>
            `
                : ""
            }
          </section>
        </main>
      </div>
    `;

    drawLangfuseTrajectoryChart(selected);
    const chartEl = document.getElementById("lf-chart-container");
    if (chartResizeObserver) {
      chartResizeObserver.disconnect();
    }
    if (chartEl && typeof ResizeObserver !== "undefined") {
      chartResizeObserver = new ResizeObserver(() => {
        drawLangfuseTrajectoryChart(getSelectedSession());
      });
      chartResizeObserver.observe(chartEl);
    }

    bindDomEvents();
  }

  function bindDomEvents() {
    const btnRefresh = document.getElementById("btn-refresh");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => {
        vscode.postMessage({ type: "refresh" });
        showToast("Syncing Project Hub…");
      });
    }

    const btnOpenMd = document.getElementById("btn-open-md");
    if (btnOpenMd) {
      btnOpenMd.addEventListener("click", () => {
        vscode.postMessage({ type: "openHubMarkdown" });
      });
    }

    document.querySelectorAll("[data-main-view]").forEach((tab) => {
      tab.addEventListener("click", () => {
        const v = tab.getAttribute("data-main-view");
        if (v && v !== state.mainView) {
          state.mainView = v;
          render();
        }
      });
    });

    document.querySelectorAll("[data-select-sid]").forEach((el) => {
      el.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        const sid = el.getAttribute("data-select-sid");
        if (sid && sid !== state.selectedSessionId) {
          state.selectedSessionId = sid;
          render();
        }
      });
    });

    document.querySelectorAll("[data-table-select-sid]").forEach((row) => {
      row.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        const sid = row.getAttribute("data-table-select-sid");
        if (sid) {
          state.selectedSessionId = sid;
          state.mainView = "trace";
          render();
        }
      });
    });

    document.querySelectorAll("[data-tree-filter]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const f = btn.getAttribute("data-tree-filter");
        if (f) {
          state.treeFilterType = f;
          render();
        }
      });
    });

    const treeSearch = document.getElementById("lf-tree-search");
    if (treeSearch) {
      treeSearch.addEventListener("input", (e) => {
        state.treeSearch = e.target.value;
        const caret = e.target.selectionStart;
        render();
        const next = document.getElementById("lf-tree-search");
        if (next) {
          next.focus();
          try {
            next.setSelectionRange(caret, caret);
          } catch (_) {}
        }
      });
    }

    document.querySelectorAll("[data-rail-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const t = btn.getAttribute("data-rail-tab");
        if (t) {
          state.railDrawerTab = t;
          render();
        }
      });
    });

    document.querySelectorAll("[data-split-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const m = btn.getAttribute("data-split-mode");
        if (m) {
          state.bottomSplitMode = m;
          render();
        }
      });
    });

    document.querySelectorAll("[data-resume-sid]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sid = btn.getAttribute("data-resume-sid");
        if (sid) {
          vscode.postMessage({ type: "resumeInCli", sessionId: sid });
          showToast(`Resuming ${sid.slice(0, 8)} in agy…`);
        }
      });
    });

    document.querySelectorAll("[data-copy-sid]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const sid = el.getAttribute("data-copy-sid");
        if (sid) {
          vscode.postMessage({ type: "copyText", text: sid });
          showToast(`Copied Trace UUID: ${sid.slice(0, 8)}`);
        }
      });
    });

    document.querySelectorAll("[data-copy-cmd]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const sid = el.getAttribute("data-copy-cmd");
        if (sid) {
          const cmd = `agy --conversation ${sid}`;
          vscode.postMessage({ type: "copyText", text: cmd });
          showToast(`Copied: ${cmd}`);
        }
      });
    });

    document.querySelectorAll("[data-copy-sha]").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        const sha = el.getAttribute("data-copy-sha");
        if (sha && sha !== "WIP") {
          vscode.postMessage({ type: "copyText", text: sha });
          showToast(`Copied SHA: ${sha}`);
        }
      });
    });

    document.querySelectorAll("[data-git-node]").forEach((row) => {
      row.addEventListener("click", () => {
        const sha = row.getAttribute("data-git-node");
        if (!sha) return;
        state.selectedGitNode = sha;
        if (sha !== "WIP" && !state.commitDetailsCache[sha]) {
          vscode.postMessage({ type: "inspectCommit", sha });
        }
        render();
      });
    });

    document.querySelectorAll("[data-jump-sha]").forEach((chip) => {
      chip.addEventListener("click", () => {
        const sha = chip.getAttribute("data-jump-sha");
        if (!sha) return;
        state.selectedGitNode = sha;
        if (!state.commitDetailsCache[sha]) {
          vscode.postMessage({ type: "inspectCommit", sha });
        }
        render();
        const rowEl = document.querySelector(`[data-git-node="${sha}"]`);
        if (rowEl) {
          rowEl.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
      });
    });

    document.querySelectorAll("[data-copy-text]").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const txt = btn.getAttribute("data-copy-text");
        if (txt) {
          vscode.postMessage({ type: "copyText", text: txt });
          showToast("Copied prompt");
        }
      });
    });

    document.querySelectorAll("[data-open-file]").forEach((el) => {
      el.addEventListener("click", () => {
        const filePath = el.getAttribute("data-open-file");
        if (filePath) {
          vscode.postMessage({ type: "openFile", path: filePath });
        }
      });
    });

    document.querySelectorAll("[data-prompt-scope]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const scope = btn.getAttribute("data-prompt-scope");
        if (scope) {
          state.promptScope = scope;
          render();
        }
      });
    });

    const searchInput = document.getElementById("lf-prompt-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.promptSearch = e.target.value;
        const caret = e.target.selectionStart;
        render();
        const nextInput = document.getElementById("lf-prompt-search");
        if (nextInput) {
          nextInput.focus();
          try {
            nextInput.setSelectionRange(caret, caret);
          } catch (_) {}
        }
      });
    }
  }

  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg) return;
    if (msg.type === "updatePayload") {
      state.payload = msg.payload;
      if (msg.selectSessionId) {
        state.selectedSessionId = msg.selectSessionId;
      }
      render();
    } else if (msg.type === "selectSession" && msg.sessionId) {
      state.selectedSessionId = msg.sessionId;
      render();
    } else if (msg.type === "commitDetails" && msg.details && msg.details.sha) {
      state.commitDetailsCache[msg.details.sha] = msg.details;
      render();
    }
  });

  render();
})();
