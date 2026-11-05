"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

let currentPayload = null;
let isFetching = false;
let pendingFetch = false;
let dashboardPanel = null;
let statusBarItem = null;
let sessionsProvider = null;
let artifactsProvider = null;
let fsWatchers = [];
let debounceTimer = null;

function getActiveWorkspaceFolder() {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders || folders.length === 0) return null;
  const activeEditor = vscode.window.activeTextEditor;
  if (activeEditor && activeEditor.document) {
    const matched = vscode.workspace.getWorkspaceFolder(activeEditor.document.uri);
    if (matched) return matched;
  }
  return folders[0];
}

function resolveSyncScriptPath(context) {
  const home = os.homedir();
  const candidates = [
    path.join(home, ".gemini", "config", "skills", "agy-project-hub", "scripts", "sync_local_notes.py"),
    path.resolve(context.extensionPath, "..", "scripts", "sync_local_notes.py"),
    path.join(context.extensionPath, "scripts", "sync_local_notes.py")
  ];
  const wf = getActiveWorkspaceFolder();
  if (wf) {
    candidates.push(path.join(wf.uri.fsPath, "scripts", "sync_local_notes.py"));
  }
  for (const cand of candidates) {
    try {
      if (fs.existsSync(cand)) return cand;
    } catch (_) {}
  }
  return candidates[0];
}

function getPythonCommand() {
  try {
    const cfg = vscode.workspace.getConfiguration("agyProjectHub");
    const custom = cfg.get("pythonPath");
    if (custom && String(custom).trim()) return String(custom).trim();
  } catch (_) {}
  return process.platform === "win32" ? "python" : "python3";
}

function runTelemetryScan(context, { syncHubs = true } = {}) {
  return new Promise((resolve) => {
    const wf = getActiveWorkspaceFolder();
    if (!wf) {
      resolve(null);
      return;
    }
    const scriptPath = resolveSyncScriptPath(context);
    if (!fs.existsSync(scriptPath)) {
      resolve(null);
      return;
    }

    const pyCmd = getPythonCommand();
    const args = [scriptPath, "--workspace", wf.uri.fsPath, "--dump-json"];
    if (!syncHubs) {
      args.push("--no-sync");
    }

    cp.execFile(
      pyCmd,
      args,
      {
        cwd: wf.uri.fsPath,
        timeout: 15000,
        maxBuffer: 16 * 1024 * 1024
      },
      (err, stdout) => {
        if (err || !stdout) {
          resolve(null);
          return;
        }
        try {
          const parsed = JSON.parse(String(stdout).trim());
          resolve(parsed);
        } catch (_) {
          resolve(null);
        }
      }
    );
  });
}

async function refreshTelemetry(context, { syncHubs = true, selectSessionId = "" } = {}) {
  if (isFetching) {
    pendingFetch = true;
    return currentPayload;
  }
  isFetching = true;
  try {
    const payload = await runTelemetryScan(context, { syncHubs });
    if (payload) {
      currentPayload = payload;
      updateStatusBar(payload);
      if (sessionsProvider) sessionsProvider.refresh();
      if (artifactsProvider) artifactsProvider.refresh();
      if (dashboardPanel) {
        dashboardPanel.webview.postMessage({
          type: "updatePayload",
          payload,
          selectSessionId: selectSessionId || undefined
        });
      }
    }
    return payload;
  } finally {
    isFetching = false;
    if (pendingFetch) {
      pendingFetch = false;
      refreshTelemetry(context, { syncHubs: false });
    }
  }
}

function updateStatusBar(payload) {
  if (!statusBarItem) return;
  if (!payload || !Array.isArray(payload.sessions) || payload.sessions.length === 0) {
    statusBarItem.text = "$(graph) Agy Hub";
    statusBarItem.backgroundColor = undefined;
    statusBarItem.tooltip = "Open Antigravity Project Hub Visual Dashboard";
    statusBarItem.show();
    return;
  }

  const sessions = payload.sessions;
  const active =
    sessions.find((s) => s.id === payload.activeSessionId) || sessions[0];
  const curTok = active.currentCtxTokens || 0;
  const pct256 = Math.min(100, Math.round((curTok / 256000) * 100));
  const cmpBadge = active.compactionCount > 0 ? ` · ${active.compactionCount}x cmp` : "";
  const lineageTag = active.parentId
    ? `Fork @${active.forkStep ?? "?"}`
    : `Tree #${active.treeNum || 1}`;

  let icon = "$(Pass)";
  if (curTok >= 185000) {
    icon = "$(warning)";
    statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.errorBackground");
  } else if (curTok >= 145000) {
    icon = "$(info)";
    statusBarItem.backgroundColor = new vscode.ThemeColor("statusBarItem.warningBackground");
  } else {
    icon = "$(zap)";
    statusBarItem.backgroundColor = undefined;
  }

  statusBarItem.text = `${icon} Ctx: ${active.currentCtxFormatted} (${pct256}%)${cmpBadge} · ${lineageTag}`;

  const md = new vscode.MarkdownString("", true);
  md.isTrusted = true;
  md.appendMarkdown(`### ⚡ Antigravity Project Hub — \`${payload.workspace?.name || ""}\`\n\n`);
  md.appendMarkdown(
    `- **Active Session (${(active.source || "cli").toUpperCase()}):** \`${active.id}\` (*${active.title}*)\n`
  );
  md.appendMarkdown(
    `- **Context Usage:** **\`${active.currentCtxFormatted}\`** active / \`${active.peakCtxFormatted}\` peak (\`${pct256}%\` of \`256k\` ceiling${cmpBadge})\n`
  );
  md.appendMarkdown(
    `- **Workspace Totals:** \`${payload.kpis?.primarySessionCount || 0}\` sessions (\`${payload.kpis?.rootTreeCount || 0}\` trees, \`${payload.kpis?.forkCount || 0}\` forks) · \`${payload.kpis?.totalChats || 0}\` chats · \`${payload.kpis?.totalOutputFormatted || "0"}\` out\n`
  );
  md.appendMarkdown(
    `- **Git Branch:** \`${payload.git?.currentBranch || "detached"}\` (${payload.git?.clean ? "Clean" : "Uncommitted changes"})\n\n`
  );
  md.appendMarkdown(
    `[📊 Open Visual Dashboard](command:agyProjectHub.openDashboard) · [📄 Open PROJECT_HUB.md](command:agyProjectHub.openHubMarkdown) · [↻ Sync Now](command:agyProjectHub.refresh)`
  );
  statusBarItem.tooltip = md;
  statusBarItem.show();
}

function inspectGitCommit(sha) {
  return new Promise((resolve) => {
    const wf = getActiveWorkspaceFolder();
    if (!wf || !sha || !/^[0-9a-fA-F]{4,40}$/.test(String(sha))) {
      resolve(null);
      return;
    }
    const cwd = wf.uri.fsPath;
    cp.execFile(
      "git",
      [
        "show",
        "--name-status",
        "--date=format:%Y-%m-%d %H:%M",
        "--pretty=format:META%x09%h%x09%H%x09%p%x09%an%x09%ad%x09%s",
        String(sha)
      ],
      { cwd, timeout: 5000, maxBuffer: 2 * 1024 * 1024 },
      (err, stdout) => {
        if (err || !stdout) {
          resolve(null);
          return;
        }
        const lines = String(stdout).split(/\r?\n/);
        let meta = {
          sha: String(sha),
          fullSha: String(sha),
          parents: [],
          author: "",
          date: "",
          subject: "",
          files: []
        };
        for (const line of lines) {
          if (!line.trim()) continue;
          if (line.startsWith("META\t")) {
            const parts = line.split("\t");
            meta.sha = parts[1] || String(sha);
            meta.fullSha = parts[2] || String(sha);
            meta.parents = (parts[3] || "").split(" ").filter(Boolean);
            meta.author = parts[4] || "";
            meta.date = parts[5] || "";
            meta.subject = parts.slice(6).join("\t") || "";
          } else if (/^[ACDMRTUXB][0-9]*\t/.test(line)) {
            const fparts = line.split("\t");
            const statusCode = fparts[0][0];
            const relPath = fparts[fparts.length - 1];
            const badgeMap = {
              M: "modified",
              A: "added",
              D: "deleted",
              R: "renamed",
              C: "copied"
            };
            meta.files.push({
              rel: relPath,
              abs: path.join(cwd, relPath),
              status: statusCode,
              badge: badgeMap[statusCode] || statusCode
            });
          }
        }
        resolve(meta);
      }
    );
  });
}

async function openFileSmart(filePath) {
  if (!filePath || !fs.existsSync(filePath)) {
    vscode.window.showWarningMessage(`File not found: ${filePath}`);
    return;
  }
  const uri = vscode.Uri.file(filePath);
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".md" || ext === ".markdown") {
    try {
      await vscode.commands.executeCommand("vscode.openWith", uri, "antigravity.markdownReview");
      return;
    } catch (_) {}
  }
  if (ext === ".html" || ext === ".pdf") {
    try {
      await vscode.env.openExternal(uri);
      return;
    } catch (_) {}
  }
  await vscode.window.showTextDocument(uri, { preview: false });
}

function resumeSessionInTerminal(sessionId) {
  let sid = sessionId;
  if (sid && typeof sid === "object" && sid.session) {
    sid = sid.session.id;
  }
  if (!sid && currentPayload) {
    sid = currentPayload.activeSessionId;
  }
  if (!sid) {
    vscode.window.showInformationMessage("No Antigravity session ID selected.");
    return;
  }
  const wf = getActiveWorkspaceFolder();
  const cwd = wf ? wf.uri.fsPath : os.homedir();
  const shortId = String(sid).slice(0, 8);
  const termName = `agy · ${shortId}`;
  let term = vscode.window.terminals.find((t) => t.name === termName);
  if (!term) {
    term = vscode.window.createTerminal({
      name: termName,
      cwd
    });
  }
  term.show();
  term.sendText(`agy --conversation ${sid}`, true);
}

class SessionsTreeProvider {
  constructor() {
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
  }

  refresh() {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (!currentPayload || !Array.isArray(currentPayload.sessions)) {
      return [];
    }
    const sessions = currentPayload.sessions;
    if (!element) {
      // Root level: Root sessions (no parentId and not subagent), or fallback all primary
      const roots = sessions.filter((s) => !s.parentId && !s.isSubagent);
      const list = roots.length > 0 ? roots : sessions.filter((s) => !s.isSubagent);
      return list.map((s) => this._buildSessionItem(s, sessions));
    }
    if (element.session) {
      const parentId = element.session.id;
      const children = sessions.filter((s) => s.parentId === parentId);
      return children.map((c) => this._buildSessionItem(c, sessions));
    }
    return [];
  }

  _buildSessionItem(s, allSessions) {
    const hasChildren = allSessions.some((x) => x.parentId === s.id);
    const isAct = s.id === currentPayload.activeSessionId;
    let label = "";
    if (s.isSubagent) {
      const atStep = s.forkStep !== null && s.forkStep !== undefined ? ` @${s.forkStep}` : "";
      label = `${s.agentName || "subagent"}${atStep} · ${s.shortId}`;
    } else if (s.parentId) {
      label = `Fork @#${s.forkStep ?? "?"} · ${s.shortId}`;
    } else {
      label = `Tree #${s.treeNum} · ${s.shortId}`;
    }

    const item = new vscode.TreeItem(
      label,
      hasChildren
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.None
    );
    item.session = s;
    item.contextValue = s.isSubagent ? "sessionSubagent" : "session";

    const cmpTag = s.compactionCount > 0 ? ` · ${s.compactionCount}x cmp` : "";
    const pct256 = Math.min(100, Math.round(((s.currentCtxTokens || 0) / 256000) * 100));
    item.description = `${s.currentCtxFormatted} (${pct256}%) · ${s.userChats} turns`;

    if (s.isSubagent) {
      item.iconPath = new vscode.ThemeIcon("hubot", new vscode.ThemeColor("charts.blue"));
    } else if (isAct) {
      item.iconPath = new vscode.ThemeIcon("zap", new vscode.ThemeColor("charts.blue"));
    } else if (s.parentId) {
      item.iconPath = new vscode.ThemeIcon("git-branch", new vscode.ThemeColor("charts.purple"));
    } else if (s.currentCtxTokens >= 185000) {
      item.iconPath = new vscode.ThemeIcon("flame", new vscode.ThemeColor("charts.orange"));
    } else {
      item.iconPath = new vscode.ThemeIcon("Pulse", new vscode.ThemeColor("charts.green"));
    }

    const md = new vscode.MarkdownString("", true);
    md.appendMarkdown(`**${label}** — *${s.title}*\n\n`);
    md.appendMarkdown(`- **UUID:** \`${s.id}\` (\`${(s.source || "cli").toUpperCase()}\`)\n`);
    md.appendMarkdown(
      `- **Context:** \`${s.currentCtxFormatted}\` active / \`${s.peakCtxFormatted}\` peak${cmpTag}\n`
    );
    md.appendMarkdown(
      `- **Activity:** \`${s.userChats}\` chats · \`${s.stepSpan}\` steps (\`#${s.firstStep}..#${s.lastStep}\`) · \`${s.totalOutputFormatted}\` out\n`
    );
    md.appendMarkdown(`- **Window:** \`${s.startedLocal}\` → \`${s.lastActive}\`\n`);
    item.tooltip = md;

    item.command = {
      command: "agyProjectHub.selectSessionInDashboard",
      title: "Inspect Session in Visual Dashboard",
      arguments: [s.id]
    };

    return item;
  }
}

class ArtifactsTreeProvider {
  constructor() {
    this._onDidChangeTreeData = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._onDidChangeTreeData.event;
  }

  refresh() {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element) {
    return element;
  }

  getChildren(element) {
    if (!currentPayload) return [];
    if (!element) {
      const dashboardItem = new vscode.TreeItem(
        "Open Visual Command Center",
        vscode.TreeItemCollapsibleState.None
      );
      dashboardItem.iconPath = new vscode.ThemeIcon("graph", new vscode.ThemeColor("charts.blue"));
      dashboardItem.description = "Interactive Charts & Forest";
      dashboardItem.command = {
        command: "agyProjectHub.openDashboard",
        title: "Open Visual Dashboard"
      };

      const hubMdItem = new vscode.TreeItem(
        "PROJECT_HUB.md",
        vscode.TreeItemCollapsibleState.None
      );
      hubMdItem.iconPath = new vscode.ThemeIcon("markdown", new vscode.ThemeColor("charts.green"));
      hubMdItem.description = ".local-notes/PROJECT_HUB.md";
      hubMdItem.command = {
        command: "agyProjectHub.openHubMarkdown",
        title: "Open PROJECT_HUB.md"
      };

      const docsGroup = new vscode.TreeItem(
        `Synced Knowledge Base (${(currentPayload.artifacts || []).length})`,
        vscode.TreeItemCollapsibleState.Expanded
      );
      docsGroup.groupKind = "docs";
      docsGroup.iconPath = new vscode.ThemeIcon("book");

      const gitDirtyCount =
        (currentPayload.git?.modified || 0) +
        (currentPayload.git?.added || 0) +
        (currentPayload.git?.deleted || 0) +
        (currentPayload.git?.untracked || 0);
      const gitGroup = new vscode.TreeItem(
        `Git Working Tree (${gitDirtyCount ? `${gitDirtyCount} dirty` : "Clean"})`,
        vscode.TreeItemCollapsibleState.Collapsed
      );
      gitGroup.groupKind = "git";
      gitGroup.iconPath = new vscode.ThemeIcon("source-control");

      const gitCommitsGroup = new vscode.TreeItem(
        `Git Branches & Commit Graph (${(currentPayload.git?.branches || []).length} branches)`,
        vscode.TreeItemCollapsibleState.Expanded
      );
      gitCommitsGroup.groupKind = "gitGraph";
      gitCommitsGroup.iconPath = new vscode.ThemeIcon("git-merge", new vscode.ThemeColor("charts.purple"));

      const hotGroup = new vscode.TreeItem(
        `Recently Touched Code (${(currentPayload.hotFiles || []).length})`,
        vscode.TreeItemCollapsibleState.Collapsed
      );
      hotGroup.groupKind = "hot";
      hotGroup.iconPath = new vscode.ThemeIcon("flame");

      return [dashboardItem, hubMdItem, gitCommitsGroup, docsGroup, gitGroup, hotGroup];
    }

    if (element.groupKind === "gitGraph") {
      const branchItems = (currentPayload.git?.branches || []).map((b) => {
        const it = new vscode.TreeItem(
          `${b.name}${b.active ? " (HEAD)" : ""}`,
          vscode.TreeItemCollapsibleState.None
        );
        it.description = `${b.sha} · ${b.subject}`;
        it.iconPath = new vscode.ThemeIcon(
          "git-branch",
          b.active ? new vscode.ThemeColor("charts.green") : new vscode.ThemeColor("charts.purple")
        );
        it.command = {
          command: "agyProjectHub.openDashboard",
          title: "Open Git Graph in Dashboard"
        };
        return it;
      });
      const commitItems = (currentPayload.git?.graphCommits || currentPayload.git?.commits || [])
        .filter((c) => c.subject || c.refs)
        .slice(0, 10)
        .map((c) => {
          const it = new vscode.TreeItem(c.subject || c.sha, vscode.TreeItemCollapsibleState.None);
          it.description = `${c.sha} · ${String(c.date || "").slice(5)}`;
          it.iconPath = new vscode.ThemeIcon("git-commit");
          it.command = {
            command: "agyProjectHub.openDashboard",
            title: "Inspect Commit in Dashboard"
          };
          return it;
        });
      return [...branchItems, ...commitItems];
    }

    if (element.groupKind === "docs") {
      const docs = (currentPayload.artifacts || []).map((d) => {
        const it = new vscode.TreeItem(d.name, vscode.TreeItemCollapsibleState.None);
        it.description = `${d.category.replace(/^[^\w]+/, "")} · ${d.lineCount}L · ${(d.originSid || "").slice(0, 8)}`;
        it.tooltip = `${d.title}\n\n${d.summary}`;
        it.iconPath = new vscode.ThemeIcon("file-text");
        it.command = {
          command: "agyProjectHub.openArtifact",
          title: "Open Artifact",
          arguments: [d.localPath]
        };
        return it;
      });
      const media = (currentPayload.richMedia || []).map((m) => {
        const it = new vscode.TreeItem(m.name, vscode.TreeItemCollapsibleState.None);
        it.description = `${m.sizeStr} · ${m.updatedLocal}`;
        it.iconPath = new vscode.ThemeIcon("globe");
        it.command = {
          command: "agyProjectHub.openArtifact",
          title: "Open Media",
          arguments: [m.path]
        };
        return it;
      });
      return [...docs, ...media];
    }

    if (element.groupKind === "git") {
      return (currentPayload.git?.changedFiles || []).map((f) => {
        const it = new vscode.TreeItem(f.rel, vscode.TreeItemCollapsibleState.None);
        it.description = f.badge;
        it.iconPath = new vscode.ThemeIcon("diff");
        it.command = {
          command: "agyProjectHub.openArtifact",
          title: "Open File",
          arguments: [f.abs]
        };
        return it;
      });
    }

    if (element.groupKind === "hot") {
      return (currentPayload.hotFiles || []).map((h) => {
        const it = new vscode.TreeItem(h.rel, vscode.TreeItemCollapsibleState.None);
        it.description = `${h.tsLocal} · ${(h.sessionId || "").slice(0, 8)}`;
        it.iconPath = new vscode.ThemeIcon("edit");
        it.command = {
          command: "agyProjectHub.openArtifact",
          title: "Open File",
          arguments: [h.abs]
        };
        return it;
      });
    }

    return [];
  }
}

function buildDashboardWebviewHtml(webview, context, initialPayload) {
  const cssUri = webview.asWebviewUri(
    vscode.Uri.file(path.join(context.extensionPath, "media", "dashboard.css"))
  );
  const jsUri = webview.asWebviewUri(
    vscode.Uri.file(path.join(context.extensionPath, "media", "dashboard.js"))
  );
  const safeJson = JSON.stringify(initialPayload || null).replace(/</g, "\\u003c");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Antigravity Project Hub</title>
  <link rel="stylesheet" href="${cssUri}" />
</head>
<body>
  <div id="app"></div>
  <div id="hub-toast" class="hub-toast"></div>
  <script>window.__INITIAL_PAYLOAD__ = ${safeJson};</script>
  <script src="${jsUri}"></script>
</body>
</html>`;
}

async function openDashboardWebview(context, selectSessionId = "") {
  if (!currentPayload) {
    await refreshTelemetry(context, { syncHubs: true });
  }
  if (dashboardPanel) {
    dashboardPanel.reveal(vscode.ViewColumn.One);
    if (currentPayload) {
      dashboardPanel.webview.postMessage({
        type: "updatePayload",
        payload: currentPayload,
        selectSessionId: selectSessionId || undefined
      });
    }
    return;
  }

  const wsName = currentPayload?.workspace?.name || "Workspace";
  dashboardPanel = vscode.window.createWebviewPanel(
    "agyProjectHub.dashboard",
    `${wsName} — Project Hub`,
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, "media"))]
    }
  );

  if (selectSessionId && currentPayload) {
    currentPayload = { ...currentPayload };
  }
  dashboardPanel.webview.html = buildDashboardWebviewHtml(
    dashboardPanel.webview,
    context,
    currentPayload
  );
  if (selectSessionId) {
    setTimeout(() => {
      if (dashboardPanel) {
        dashboardPanel.webview.postMessage({
          type: "selectSession",
          sessionId: selectSessionId
        });
      }
    }, 80);
  }

  dashboardPanel.webview.onDidReceiveMessage(async (msg) => {
    if (!msg) return;
    if (msg.type === "refresh") {
      await refreshTelemetry(context, { syncHubs: true });
    } else if (msg.type === "openHubMarkdown") {
      vscode.commands.executeCommand("agyProjectHub.openHubMarkdown");
    } else if (msg.type === "resumeInCli" && msg.sessionId) {
      resumeSessionInTerminal(msg.sessionId);
    } else if (msg.type === "copyText" && msg.text) {
      await vscode.env.clipboard.writeText(String(msg.text));
    } else if (msg.type === "openFile" && msg.path) {
      await openFileSmart(msg.path);
    } else if (msg.type === "inspectCommit" && msg.sha) {
      const details = await inspectGitCommit(msg.sha);
      if (details && dashboardPanel) {
        dashboardPanel.webview.postMessage({
          type: "commitDetails",
          details
        });
      }
    }
  });

  dashboardPanel.onDidDispose(() => {
    dashboardPanel = null;
  });
}

function setupBackgroundWatchers(context) {
  const scheduleRefresh = (syncHubs = false) => {
    const autoSync = vscode.workspace
      .getConfiguration("agyProjectHub")
      .get("autoSync", true);
    if (!autoSync) return;
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      refreshTelemetry(context, { syncHubs });
    }, 2200);
  };

  // Watch ~/.gemini/antigravity-cli/brain and ~/.gemini/antigravity/brain
  const home = os.homedir();
  const brainRoots = [
    path.join(home, ".gemini", "antigravity-cli", "brain"),
    path.join(home, ".gemini", "antigravity", "brain")
  ];
  for (const bRoot of brainRoots) {
    try {
      if (fs.existsSync(bRoot)) {
        const w = fs.watch(bRoot, { recursive: true }, (_eventType, filename) => {
          if (!filename) return;
          const low = String(filename).toLowerCase();
          if (low.endsWith("project_hub.md") || low.endsWith(".metadata.json")) {
            return;
          }
          if (low.endsWith("transcript.jsonl") || low.endsWith(".md") || low.endsWith(".html")) {
            scheduleRefresh(true);
          }
        });
        fsWatchers.push(w);
      }
    } catch (_) {}
  }

  // Watch active workspace .git changes
  const wf = getActiveWorkspaceFolder();
  if (wf) {
    const gitWatcher = vscode.workspace.createFileSystemWatcher(
      new vscode.RelativePattern(wf, ".git/{HEAD,index,refs/**}")
    );
    gitWatcher.onDidChange(() => scheduleRefresh(false));
    gitWatcher.onDidCreate(() => scheduleRefresh(false));
    context.subscriptions.push(gitWatcher);
  }
}

function activate(context) {
  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left,
    98
  );
  statusBarItem.command = "agyProjectHub.openDashboard";
  statusBarItem.text = "$(zap) Agy Hub";
  context.subscriptions.push(statusBarItem);

  sessionsProvider = new SessionsTreeProvider();
  artifactsProvider = new ArtifactsTreeProvider();

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("agyProjectHub.sessionsView", sessionsProvider),
    vscode.window.registerTreeDataProvider("agyProjectHub.artifactsView", artifactsProvider)
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("agyProjectHub.openDashboard", () =>
      openDashboardWebview(context)
    ),
    vscode.commands.registerCommand(
      "agyProjectHub.selectSessionInDashboard",
      (sessionId) => openDashboardWebview(context, sessionId)
    ),
    vscode.commands.registerCommand("agyProjectHub.refresh", async () => {
      await refreshTelemetry(context, { syncHubs: true });
      vscode.window.setStatusBarMessage("$(check) Antigravity Project Hub synced", 2500);
    }),
    vscode.commands.registerCommand("agyProjectHub.openHubMarkdown", async () => {
      if (!currentPayload) {
        await refreshTelemetry(context, { syncHubs: true });
      }
      const wf = getActiveWorkspaceFolder();
      const hubPath =
        currentPayload?.workspace?.localNotesHubPath ||
        (wf ? path.join(wf.uri.fsPath, ".local-notes", "PROJECT_HUB.md") : "");
      if (hubPath && fs.existsSync(hubPath)) {
        await openFileSmart(hubPath);
      } else {
        vscode.window.showInformationMessage("Generating PROJECT_HUB.md…");
        const p = await refreshTelemetry(context, { syncHubs: true });
        if (p?.workspace?.localNotesHubPath && fs.existsSync(p.workspace.localNotesHubPath)) {
          await openFileSmart(p.workspace.localNotesHubPath);
        }
      }
    }),
    vscode.commands.registerCommand("agyProjectHub.resumeSessionInCli", (itemOrSid) => {
      resumeSessionInTerminal(itemOrSid);
    }),
    vscode.commands.registerCommand("agyProjectHub.copySessionId", async (itemOrSid) => {
      const sid =
        typeof itemOrSid === "string"
          ? itemOrSid
          : itemOrSid?.session?.id || currentPayload?.activeSessionId;
      if (sid) {
        await vscode.env.clipboard.writeText(sid);
        vscode.window.setStatusBarMessage(`$(check) Copied Session ID: ${sid}`, 2500);
      }
    }),
    vscode.commands.registerCommand("agyProjectHub.copyResumeCommand", async (itemOrSid) => {
      const sid =
        typeof itemOrSid === "string"
          ? itemOrSid
          : itemOrSid?.session?.id || currentPayload?.activeSessionId;
      if (sid) {
        const cmd = `agy --conversation ${sid}`;
        await vscode.env.clipboard.writeText(cmd);
        vscode.window.setStatusBarMessage(`$(check) Copied: ${cmd}`, 2500);
      }
    }),
    vscode.commands.registerCommand("agyProjectHub.openArtifact", async (filePath) => {
      if (filePath) {
        await openFileSmart(filePath);
      }
    })
  );

  setupBackgroundWatchers(context);
  refreshTelemetry(context, { syncHubs: true });
}

function deactivate() {
  if (debounceTimer) clearTimeout(debounceTimer);
  for (const w of fsWatchers) {
    try {
      w.close();
    } catch (_) {}
  }
  fsWatchers = [];
}

module.exports = {
  activate,
  deactivate
};
