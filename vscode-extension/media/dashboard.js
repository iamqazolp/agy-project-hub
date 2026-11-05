(function () {
  const vscode = acquireVsCodeApi();

  const LANE_COLORS = [
    "#2563eb", // blue
    "#059669", // emerald
    "#7c3aed", // purple
    "#d97706", // amber
    "#0891b2", // cyan
    "#db2777", // pink
    "#65a30d"  // lime
  ];

  const ICONS = {
    branch: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M9.5 3.25a2.25 2.25 0 1 1 3 2.122V6A2.5 2.5 0 0 1 10 8.5H6a1 1 0 0 0-1 1v1.128a2.251 2.251 0 1 1-1.5 0V5.372a2.25 2.25 0 1 1 1.5 0v1.836A2.493 2.493 0 0 1 6 7h4a1 1 0 0 0 1-1v-.628A2.25 2.25 0 0 1 9.5 3.25Zm-6 0a.75.75 0 1 0 1.5 0 .75.75 0 0 0-1.5 0Zm8.25-.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5ZM4.25 12a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Z"/></svg>`,
    terminal: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M0 2.75C0 1.784.784 1 1.75 1h12.5c.966 0 1.75.784 1.75 1.75v10.5A1.75 1.75 0 0 1 14.25 15H1.75A1.75 1.75 0 0 1 0 13.25Zm1.75-.25a.25.25 0 0 0-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25V2.75a.25.25 0 0 0-.25-.25ZM7.25 8a.749.749 0 0 1-.22.53l-2.25 2.25a.749.749 0 0 1-1.275-.326.749.749 0 0 1 .215-.734L5.44 8 3.72 6.28a.749.749 0 0 1 .326-1.275.749.749 0 0 1 .734.215l2.25 2.25c.141.14.22.331.22.53Zm1.5 1.5h3a.75.75 0 0 1 0 1.5h-3a.75.75 0 0 1 0-1.5Z"/></svg>`,
    copy: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg>`,
    file: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16h-9.5A1.75 1.75 0 0 1 2 14.25Zm1.75-.25a.25.25 0 0 0-.25.25v12.5c0 .138.112.25.25.25h9.5a.25.25 0 0 0 .25-.25V6h-2.75A1.75 1.75 0 0 1 9 4.25V1.5Zm6.75.062V4.25c0 .138.112.25.25.25h2.688l-.011-.013-2.914-2.914-.013-.011Z"/></svg>`,
    refresh: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M1.705 8.005a.75.75 0 0 1 .834.656 5.5 5.5 0 0 0 9.592 2.97l-1.204-1.204a.25.25 0 0 1 .177-.427h3.646a.25.25 0 0 1 .25.25v3.646a.25.25 0 0 1-.427.177l-1.38-1.38A7.002 7.002 0 0 1 1.05 8.84a.75.75 0 0 1 .656-.834ZM8 2.5a5.487 5.487 0 0 0-4.131 1.869l1.204 1.204A.25.25 0 0 1 4.896 6H1.25A.25.25 0 0 1 1 5.75V2.104a.25.25 0 0 1 .427-.177l1.38 1.38A7.002 7.002 0 0 1 14.95 7.16a.75.75 0 0 1-1.49.178A5.5 5.5 0 0 0 8 2.5Z"/></svg>`,
    pulse: `<svg class="svg-icon" viewBox="0 0 16 16" fill="currentColor"><path d="M6 2c.306 0 .582.187.696.471L10 10.731l1.304-3.26A.751.751 0 0 1 12 7h3.25a.75.75 0 0 1 0 1.5h-2.742l-1.812 4.528a.751.751 0 0 1-1.392 0L6 4.77 4.696 8.03A.75.75 0 0 1 4 8.5H.75a.75.75 0 0 1 0-1.5h2.742l1.812-4.529A.751.751 0 0 1 6 2Z"/></svg>`
  };

  let state = {
    payload: window.__INITIAL_PAYLOAD__ || null,
    selectedSessionId: "",
    promptScope: "selected",
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

  /* ------------------------------------------------------------------
   * 1:1 Pixel-Accurate Context Trajectory SVG Chart (No Distortion!)
   * ------------------------------------------------------------------ */
  function drawCrispTrajectorySvg(sess) {
    const container = document.getElementById("wb-chart-container");
    if (!container) return;

    if (!sess || !Array.isArray(sess.trajectory) || sess.trajectory.length === 0) {
      container.innerHTML = `<div style="padding:28px;text-align:center;color:var(--fg-muted);">No context trajectory points recorded for this session.</div>`;
      return;
    }

    const rect = container.getBoundingClientRect();
    const W = Math.max(320, Math.round(rect.width || 680));
    const H = Math.max(105, Math.round(rect.height || 132));
    const padL = 44;
    const padR = 14;
    const padT = 12;
    const padB = 20;
    const plotW = Math.max(40, W - padL - padR);
    const plotH = Math.max(30, H - padT - padB);

    const pts = sess.trajectory;
    const minStep = pts[0].step;
    const maxStep = Math.max(minStep + 1, pts[pts.length - 1].step);
    const peakTok = Math.max(265000, sess.peakCtxTokens || 0, ...pts.map((p) => p.tokens));
    const maxY = Math.ceil(peakTok / 50000) * 50000;

    const xOf = (step) => padL + ((step - minStep) / Math.max(1, maxStep - minStep)) * plotW;
    const yOf = (tok) => padT + plotH - (Math.min(maxY, Math.max(0, tok)) / maxY) * plotH;

    // Baseline + 128k + 256k reference lines
    const yBase = (padT + plotH).toFixed(1);
    const gridLevels = [128000, 256000].filter((v) => v <= maxY);
    const gridLines = gridLevels
      .map((gv) => {
        const y = yOf(gv).toFixed(1);
        const isCompact = gv === 256000;
        const stroke = isCompact ? "var(--amber)" : "var(--border-strong)";
        const dash = isCompact ? 'stroke-dasharray="4 3"' : 'stroke-dasharray="2 3"';
        const label = isCompact ? "256k" : "128k";
        const fill = isCompact ? "var(--amber)" : "var(--fg-muted)";
        return `
          <line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="${stroke}" stroke-width="1" ${dash} opacity="${isCompact ? 0.85 : 0.45}" />
          <text x="${padL - 6}" y="${Number(y) + 3.5}" text-anchor="end" font-family="var(--font-mono)" font-size="10" fill="${fill}">${label}</text>
        `;
      })
      .join("");

    const inheritedPts = pts.filter((p) => p.inherited);
    const ownPts = pts.filter((p) => !p.inherited);
    if (inheritedPts.length > 0 && ownPts.length > 0) {
      ownPts.unshift(inheritedPts[inheritedPts.length - 1]);
    }

    const buildPath = (arr) => {
      if (!arr.length) return "";
      if (arr.length === 1) {
        const x = xOf(arr[0].step).toFixed(1);
        const y = yOf(arr[0].tokens).toFixed(1);
        return `M ${x} ${y} L ${Number(x) + 1} ${y}`;
      }
      return arr
        .map((p, idx) => `${idx === 0 ? "M" : "L"} ${xOf(p.step).toFixed(1)} ${yOf(p.tokens).toFixed(1)}`)
        .join(" ");
    };

    const buildArea = (arr) => {
      if (arr.length < 2) return "";
      const lineD = buildPath(arr);
      const firstX = xOf(arr[0].step).toFixed(1);
      const lastX = xOf(arr[arr.length - 1].step).toFixed(1);
      return `${lineD} L ${lastX} ${yBase} L ${firstX} ${yBase} Z`;
    };

    const inhLine = buildPath(inheritedPts);
    const inhArea = buildArea(inheritedPts);
    const ownLine = buildPath(ownPts);
    const ownArea = buildArea(ownPts);

    let forkMarker = "";
    if (sess.parentId && sess.forkStep !== null && sess.forkStep !== undefined) {
      const fx = xOf(sess.forkStep).toFixed(1);
      forkMarker = `
        <line x1="${fx}" y1="${padT}" x2="${fx}" y2="${yBase}" stroke="var(--purple)" stroke-width="1.2" stroke-dasharray="3 3" />
        <text x="${Number(fx) + 4}" y="${padT + 10}" font-family="var(--font-mono)" font-size="9.5" font-weight="600" fill="var(--purple)">fork @#${sess.forkStep}</text>
      `;
    }

    const compactMarkers = pts
      .filter((p) => p.compacted)
      .map((p) => {
        const cx = xOf(p.step).toFixed(1);
        const cy = yOf(p.tokens).toFixed(1);
        return `
          <line x1="${cx}" y1="${padT}" x2="${cx}" y2="${yBase}" stroke="var(--rose)" stroke-width="1" stroke-dasharray="2 2" opacity="0.6" />
          <circle cx="${cx}" cy="${cy}" r="3.2" fill="var(--rose)" stroke="var(--bg)" stroke-width="1.2" />
        `;
      })
      .join("");

    const lastPt = pts[pts.length - 1];
    const lx = xOf(lastPt.step).toFixed(1);
    const ly = yOf(lastPt.tokens).toFixed(1);
    const midStep = Math.round((minStep + maxStep) / 2);

    container.innerHTML = `
      <svg class="wb-chart-svg" id="wb-chart-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
        <defs>
          <linearGradient id="ownFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.22"/>
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.01"/>
          </linearGradient>
          <linearGradient id="inhFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--purple)" stop-opacity="0.18"/>
            <stop offset="100%" stop-color="var(--purple)" stop-opacity="0.01"/>
          </linearGradient>
        </defs>
        <line x1="${padL}" y1="${yBase}" x2="${W - padR}" y2="${yBase}" stroke="var(--border-strong)" stroke-width="1" />
        ${gridLines}
        ${inhArea ? `<path d="${inhArea}" fill="url(#inhFill)" />` : ""}
        ${ownArea ? `<path d="${ownArea}" fill="url(#ownFill)" />` : ""}
        ${inhLine ? `<path d="${inhLine}" fill="none" stroke="var(--purple)" stroke-width="1.6" stroke-dasharray="4 3" />` : ""}
        ${ownLine ? `<path d="${ownLine}" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linejoin="round" />` : ""}
        ${forkMarker}
        ${compactMarkers}
        <circle cx="${lx}" cy="${ly}" r="3.5" fill="var(--accent)" stroke="var(--bg)" stroke-width="1.4" />
        <line id="wb-hover-line" x1="0" y1="${padT}" x2="0" y2="${yBase}" stroke="var(--fg-muted)" stroke-width="1" stroke-dasharray="2 2" style="display:none;" />
        <circle id="wb-hover-dot" cx="0" cy="0" r="3.8" fill="var(--accent)" stroke="var(--bg)" stroke-width="1.5" style="display:none;" />
        <text x="${padL}" y="${H - 5}" text-anchor="start" font-family="var(--font-mono)" font-size="9.5" fill="var(--fg-muted)">step #${minStep}</text>
        <text x="${xOf(midStep).toFixed(1)}" y="${H - 5}" text-anchor="middle" font-family="var(--font-mono)" font-size="9.5" fill="var(--fg-muted)">step #${midStep}</text>
        <text x="${W - padR}" y="${H - 5}" text-anchor="end" font-family="var(--font-mono)" font-size="9.5" fill="var(--fg-muted)">step #${maxStep}</text>
      </svg>
      <div class="wb-chart-tooltip" id="wb-chart-tooltip"></div>
    `;

    const svg = document.getElementById("wb-chart-svg");
    const tooltip = document.getElementById("wb-chart-tooltip");
    const hoverLine = document.getElementById("wb-hover-line");
    const hoverDot = document.getElementById("wb-hover-dot");
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
      const extra = nearest.compacted
        ? " · Compacted"
        : nearest.inherited
        ? " · Inherited"
        : "";
      tooltip.textContent = `#${nearest.step} · ${fmtTokens(nearest.tokens)} (${pct}%)${extra}`;
      tooltip.style.display = "block";
      const leftPx = Math.min(W - 165, Math.max(8, relX + 10));
      const topPx = Math.max(4, ev.clientY - r.top - 28);
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
    let headBranch = "";
    for (const p of parts) {
      if (p.startsWith("HEAD -> ")) {
        headBranch = p.slice(8).trim();
        localBranches.add(headBranch);
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
          cls: "wb-ref-head",
          isHead: true
        });
      } else if (p === "HEAD") {
        badges.push({ text: "HEAD", cls: "wb-ref-head", isHead: true });
      } else if (p.startsWith("tag:")) {
        badges.push({
          text: p.replace(/^tag:\s*/, ""),
          cls: "wb-ref-tag",
          isHead: false
        });
      } else if (p.startsWith("origin/")) {
        const shortRemote = p.slice(7);
        // Skip origin/<branch> if local <branch> is on this exact same commit
        if (localBranches.has(shortRemote)) continue;
        badges.push({ text: p, cls: "wb-ref-branch", isHead: false });
      } else {
        const hasRemote = parts.includes(`origin/${p}`);
        badges.push({
          text: hasRemote ? `${p} ⇅` : p,
          cls: "wb-ref-branch",
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
        badges: [{ text: "WIP", cls: "wb-ref-tag", isHead: false }]
      });
    }

    for (const c of rawCommits) {
      // Skip empty/dangling snapshot commits if any
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
        col = allocLane(node.sha, node.isWip ? "var(--amber)" : undefined);
      }

      node.col = col;
      node.color = node.isWip ? "var(--amber)" : laneColorByCol[col] || LANE_COLORS[0];
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

  function renderGitPane(git) {
    const { nodes, rowBySha, maxCol } = computeGitGraphLayout(git);
    if (!nodes.length) {
      return `<div style="padding:20px;text-align:center;color:var(--fg-muted);">No commits found.</div>`;
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
            ? "var(--amber)"
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
          return `<circle cx="${cx}" cy="${cy}" r="${isSelected ? 4.4 : 3.8}" fill="var(--bg)" stroke="var(--amber)" stroke-width="1.8" />`;
        }
        if (isHead) {
          return `
            <circle cx="${cx}" cy="${cy}" r="4.8" fill="var(--bg)" stroke="var(--emerald)" stroke-width="1.5" />
            <circle cx="${cx}" cy="${cy}" r="2.3" fill="var(--emerald)" />
          `;
        }
        return `<circle cx="${cx}" cy="${cy}" r="${isSelected ? 4 : 3.1}" fill="${n.color}" stroke="var(--bg)" stroke-width="1.2" />`;
      })
      .join("");

    const rowsHtml = nodes
      .map((n) => {
        const isSel = state.selectedGitNode === n.sha;
        const badgesHtml = n.badges
          .map((b) => `<span class="wb-ref-badge ${b.cls}">${esc(b.text)}</span>`)
          .join("");
        const shortDate = n.isWip ? "" : String(n.date || "").slice(5);
        return `
          <div class="wb-git-row ${n.isWip ? "is-wip" : ""} ${isSel ? "selected" : ""}" data-git-node="${esc(n.sha)}">
            <div class="wb-git-row-left">
              ${badgesHtml}
              <span class="wb-git-subject" title="${esc(n.subject)}">${esc(n.subject)}</span>
            </div>
            <div class="wb-git-row-right">
              ${shortDate ? `<span>${esc(shortDate)}</span>` : ""}
              <span class="wb-git-sha" data-copy-sha="${esc(n.sha)}" title="Click to copy SHA">${esc(n.sha)}</span>
            </div>
          </div>
        `;
      })
      .join("");

    // Drawer for selected commit or WIP
    let drawerHead = "";
    let drawerFilesHtml = "";
    if (state.selectedGitNode === "WIP") {
      const changed = git.changedFiles || [];
      drawerHead = `
        <span><strong>Working Tree</strong> · ${changed.length} uncommitted files (+${git.insertions || 0} / -${git.deletions || 0})</span>
        <span>Click file to open</span>
      `;
      drawerFilesHtml = changed.length
        ? changed
            .map((f) => {
              const code = (f.badge || "M")[0].toUpperCase();
              return `
                <div class="wb-diff-item" data-open-file="${esc(f.abs)}" title="${esc(f.rel)} (${esc(f.badge)})">
                  <span class="wb-diff-code wb-diff-${code}">${code}</span>
                  <span class="wb-diff-path">${esc(f.rel)}</span>
                </div>
              `;
            })
            .join("")
        : `<div style="color:var(--fg-muted);font-size:11px;">Working tree is clean.</div>`;
    } else {
      const selNode = nodes.find((n) => n.sha === state.selectedGitNode);
      const details = state.commitDetailsCache[state.selectedGitNode];
      const files = details ? details.files || [] : [];
      drawerHead = `
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
          <strong style="color:var(--accent);font-family:var(--font-mono);">${esc(state.selectedGitNode)}</strong>
          · ${esc(selNode ? selNode.subject : "")}
        </span>
        <span style="flex-shrink:0;font-family:var(--font-mono);">${esc(selNode?.author || "")}</span>
      `;
      drawerFilesHtml = !details
        ? `<div style="color:var(--fg-muted);font-size:10.5px;">Loading commit diff…</div>`
        : files.length
        ? files
            .map(
              (f) => `
            <div class="wb-diff-item" data-open-file="${esc(f.abs)}" title="${esc(f.rel)} (${esc(f.badge)})">
              <span class="wb-diff-code wb-diff-${esc(f.status)}">${esc(f.status)}</span>
              <span class="wb-diff-path">${esc(f.rel)}</span>
            </div>
          `
            )
            .join("")
        : `<div style="color:var(--fg-muted);font-size:10.5px;">No modified files in commit.</div>`;
    }

    return `
      <div class="wb-git-scroll">
        <div class="wb-git-stage">
          <svg class="wb-git-svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}">
            ${edgePaths.join("")}
            ${nodeCircles}
          </svg>
          <div class="wb-git-rows">
            ${rowsHtml}
          </div>
        </div>
      </div>
      <div class="wb-git-drawer">
        <div class="wb-git-drawer-head">${drawerHead}</div>
        <div class="wb-git-drawer-files">${drawerFilesHtml}</div>
      </div>
    `;
  }

  /* ------------------------------------------------------------------
   * Full-Viewport Workbench Render
   * ------------------------------------------------------------------ */
  function render() {
    const root = document.getElementById("app");
    if (!root) return;
    const data = state.payload;
    if (!data) {
      root.innerHTML = `<div style="padding:32px;text-align:center;color:var(--fg-muted);">Loading Antigravity Project Hub…</div>`;
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
    const meterColor =
      curTok >= 185000 ? "var(--amber)" : curTok >= 100000 ? "var(--accent)" : "var(--emerald)";

    // Sessions list in Left Rail
    const sessionsListHtml = sessions
      .map((s) => {
        const isSel = selected && s.id === selected.id;
        const isAct = s.id === data.activeSessionId;
        const dotColor = s.isSubagent
          ? "var(--cyan)"
          : s.currentCtxTokens >= 185000
          ? "var(--amber)"
          : s.parentId
          ? "var(--purple)"
          : isAct
          ? "var(--emerald)"
          : "var(--accent)";
        const label = s.isSubagent
          ? `${s.agentName || "sub"} · ${s.shortId}`
          : s.parentId
          ? `Fork @#${s.forkStep ?? "?"} · ${s.shortId}`
          : `Tree #${s.treeNum} · ${s.shortId}`;
        const cmpStr = s.compactionCount > 0 ? ` · ${s.compactionCount}x cmp` : "";

        return `
          <div class="wb-sess-item ${s.parentId || s.isSubagent ? "is-fork" : ""} ${isSel ? "selected" : ""}" data-select-sid="${esc(s.id)}">
            <div class="wb-sess-row1">
              <span class="wb-sess-id">
                <span class="wb-dot" style="background:${dotColor};"></span>
                <span>${esc(label)}</span>
              </span>
              <span class="wb-sess-actions">
                <button type="button" class="wb-icon-btn" data-resume-sid="${esc(s.id)}" title="Resume in agy CLI (agy --conversation ${esc(s.id)})">${ICONS.terminal}</button>
                <button type="button" class="wb-icon-btn" data-copy-sid="${esc(s.id)}" title="Copy Session UUID">${ICONS.copy}</button>
              </span>
            </div>
            <div class="wb-sess-title" title="${esc(s.title)}">${esc(s.title)}</div>
            <div class="wb-sess-row3">
              <span>${s.userChats} turns · ${s.stepSpan} steps</span>
              <span><strong>${esc(s.currentCtxFormatted)}</strong>/${esc(s.peakCtxFormatted)}${esc(cmpStr)}</span>
            </div>
          </div>
        `;
      })
      .join("");

    // Left Rail Bottom: Synced Artifacts + Recently Edited Files
    const artifacts = data.artifacts || [];
    const media = data.richMedia || [];
    const hotFiles = data.hotFiles || [];
    const railItems = [];
    for (const d of artifacts) {
      railItems.push(`
        <div class="wb-rail-file" data-open-file="${esc(d.localPath)}" title="${esc(d.title)}: ${esc(d.summary)}">
          <span class="wb-rail-file-name">${ICONS.file} ${esc(d.name)}</span>
          <span class="wb-rail-file-meta">${d.lineCount}L</span>
        </div>
      `);
    }
    for (const m of media) {
      railItems.push(`
        <div class="wb-rail-file" data-open-file="${esc(m.path)}" title="${esc(m.relLabel)}">
          <span class="wb-rail-file-name">${ICONS.file} ${esc(m.name)}</span>
          <span class="wb-rail-file-meta">${esc(m.sizeStr)}</span>
        </div>
      `);
    }
    for (const h of hotFiles) {
      railItems.push(`
        <div class="wb-rail-file" data-open-file="${esc(h.abs)}" title="Recently edited in session ${esc((h.sessionId || "").slice(0, 8))}">
          <span class="wb-rail-file-name">${esc(h.rel)}</span>
          <span class="wb-rail-file-meta">${esc(String(h.tsLocal || "").slice(11))}</span>
        </div>
      `);
    }

    // Prompts Timeline (Bottom Right)
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
    const q = (state.promptSearch || "").trim().toLowerCase();
    if (q) {
      promptsPool = promptsPool.filter(
        (p) =>
          String(p.text || "").toLowerCase().includes(q) ||
          String(p.sessionShort || "").toLowerCase().includes(q)
      );
    }

    const promptsHtml = promptsPool.length
      ? promptsPool
          .map(
            (p) => `
          <div class="wb-prompt-row">
            <div class="wb-prompt-meta">
              <span>#${p.step} · ${esc(String(p.timestamp || "").slice(5))} · ${esc(p.sessionShort)}</span>
              <button type="button" class="wb-icon-btn wb-prompt-copy" data-copy-text="${esc(p.text)}" title="Copy prompt">${ICONS.copy}</button>
            </div>
            <div class="wb-prompt-body">${esc(p.text)}</div>
          </div>
        `
          )
          .join("")
      : `<div style="padding:20px;text-align:center;color:var(--fg-muted);">No prompts matching filter.</div>`;

    const branches = git.branches || [];
    const branchChipsHtml = branches
      .map(
        (b) => `
        <span class="wb-branch-chip ${b.active ? "active" : ""}" data-jump-sha="${esc(b.sha)}" title="${esc(b.name)} (${esc(b.sha)})">
          ${ICONS.branch} ${esc(b.name)}
        </span>
      `
      )
      .join("");

    root.innerHTML = `
      <header class="wb-topbar">
        <div class="wb-topbar-left">
          <span class="wb-brand">${ICONS.pulse} ${esc(ws.name || "Workspace")}</span>
          <span class="wb-divider"></span>
          <div class="wb-ctx-pill" title="Active Session Context Window (256k auto-compaction ceiling)">
            <span>Ctx <strong>${activeSess ? esc(activeSess.currentCtxFormatted) : "0"}</strong> / 256k (${pct256}%)</span>
            <div class="wb-ctx-mini-track">
              <div class="wb-ctx-mini-fill" style="width:${pct256}%;background:${meterColor};"></div>
            </div>
            ${activeSess && activeSess.compactionCount > 0 ? `<span style="color:var(--rose);">${activeSess.compactionCount}x cmp</span>` : ""}
          </div>
          <div class="wb-stat-strip">
            <span class="wb-stat-item"><strong>${kpis.primarySessionCount || 0}</strong> sessions (${kpis.forkCount || 0} forks)</span>
            <span>·</span>
            <span class="wb-stat-item"><strong>${kpis.totalChats || 0}</strong> turns (${kpis.totalSteps || 0} steps)</span>
            <span>·</span>
            <span class="wb-stat-item"><strong>${esc(kpis.totalOutputFormatted || "0")}</strong> out</span>
          </div>
        </div>
        <div class="wb-topbar-right">
          ${
            selected
              ? `<button type="button" class="wb-btn wb-btn-primary" data-resume-sid="${esc(selected.id)}">${ICONS.terminal} Resume ${esc(selected.shortId)}</button>`
              : ""
          }
          <button type="button" class="wb-btn" id="btn-open-md">${ICONS.file} PROJECT_HUB.md</button>
          <button type="button" class="wb-btn" id="btn-refresh">${ICONS.refresh} Sync</button>
        </div>
      </header>

      <div class="wb-body">
        <aside class="wb-rail">
          <div class="wb-section-head">
            <span>Sessions & Forks</span>
            <span>${sessions.length}</span>
          </div>
          <div class="wb-rail-sessions">
            ${sessionsListHtml || `<div style="padding:12px;color:var(--fg-muted);">No sessions found.</div>`}
          </div>
          <div class="wb-rail-bottom">
            <div class="wb-section-head">
              <span>Artifacts & Hot Files</span>
              <span>${railItems.length}</span>
            </div>
            <div class="wb-rail-list">
              ${railItems.join("") || `<div style="padding:12px;color:var(--fg-muted);">No artifacts or recent edits.</div>`}
            </div>
          </div>
        </aside>

        <main class="wb-stage">
          <section class="wb-chart-pane">
            <div class="wb-section-head">
              <div class="wb-legend">
                <span style="color:var(--fg);">Context Trajectory — ${selected ? esc(selected.shortId) : ""}</span>
                <span class="wb-legend-item"><span class="wb-swatch" style="background:var(--accent);"></span> Active</span>
                ${selected && selected.parentId ? `<span class="wb-legend-item"><span class="wb-swatch" style="background:var(--purple);"></span> Pre-Fork</span>` : ""}
                <span class="wb-legend-item"><span class="wb-swatch" style="background:var(--amber);"></span> 256k Ceiling</span>
                ${selected && selected.compactionCount > 0 ? `<span class="wb-legend-item"><span class="wb-swatch" style="background:var(--rose);"></span> ${selected.compactionCount}x Compacted</span>` : ""}
              </div>
              ${
                selected
                  ? `<div class="wb-chart-meta">
                      <span>Peak ${esc(selected.peakCtxFormatted)}</span>
                      <span>·</span>
                      <span>${esc(selected.startedLocal)} → ${esc(selected.lastActive)}</span>
                    </div>`
                  : ""
              }
            </div>
            <div class="wb-chart-body">
              <div class="wb-chart-container" id="wb-chart-container"></div>
            </div>
          </section>

          <section class="wb-bottom-split">
            <div class="wb-git-pane">
              <div class="wb-section-head">
                <span>Git Commit Graph</span>
                <div class="wb-branch-chips">${branchChipsHtml}</div>
              </div>
              ${renderGitPane(git)}
            </div>

            <div class="wb-prompts-pane">
              <div class="wb-section-head">
                <span>Prompt History</span>
                <span>${promptsPool.length} turns</span>
              </div>
              <div class="wb-prompts-toolbar">
                <div class="wb-seg-group">
                  <button type="button" class="wb-seg-btn ${state.promptScope === "selected" ? "active" : ""}" data-prompt-scope="selected">
                    ${selected ? esc(selected.shortId) : "Selected"}
                  </button>
                  <button type="button" class="wb-seg-btn ${state.promptScope === "all" ? "active" : ""}" data-prompt-scope="all">
                    All
                  </button>
                </div>
                <input type="search" class="wb-search" id="wb-prompt-search" placeholder="Filter prompts…" value="${esc(state.promptSearch)}" />
              </div>
              <div class="wb-prompts-scroll">
                ${promptsHtml}
              </div>
            </div>
          </section>
        </main>
      </div>
    `;

    drawCrispTrajectorySvg(selected);
    const chartEl = document.getElementById("wb-chart-container");
    if (chartResizeObserver) {
      chartResizeObserver.disconnect();
    }
    if (chartEl && typeof ResizeObserver !== "undefined") {
      chartResizeObserver = new ResizeObserver(() => {
        drawCrispTrajectorySvg(getSelectedSession());
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

    document.querySelectorAll("[data-select-sid]").forEach((card) => {
      card.addEventListener("click", (e) => {
        if (e.target.closest("button")) return;
        const sid = card.getAttribute("data-select-sid");
        if (sid && sid !== state.selectedSessionId) {
          state.selectedSessionId = sid;
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
          showToast(`Copied UUID: ${sid.slice(0, 8)}`);
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

    const searchInput = document.getElementById("wb-prompt-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.promptSearch = e.target.value;
        const caret = e.target.selectionStart;
        render();
        const nextInput = document.getElementById("wb-prompt-search");
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
