"use strict";

const vscode = require("vscode");
const fs = require("fs");
const path = require("path");
const os = require("os");

const BRAIN_UUID_RE = /\/brain\/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\//;

const ALERT_ICONS = {
  note: '<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"></path></svg>',
  tip: '<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z"></path></svg>',
  important: '<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-.25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 9a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"></path></svg>',
  warning: '<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"></path></svg>',
  caution: '<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a.749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z"></path></svg>'
};

const ALERT_LABELS = {
  note: "Note",
  tip: "Tip",
  important: "Important",
  warning: "Warning",
  caution: "Caution"
};

function resolveRealFileInfo(uri) {
  const fsPath = uri.fsPath;
  let realPath = fsPath;
  let isSymlink = false;
  try {
    const lstat = fs.lstatSync(fsPath);
    if (lstat.isSymbolicLink()) {
      isSymlink = true;
      realPath = fs.realpathSync(fsPath);
    } else {
      realPath = fs.realpathSync(fsPath);
    }
  } catch (_) {
    // ignore
  }
  const normalized = realPath.replace(/\\/g, "/");
  const match = normalized.match(BRAIN_UUID_RE);
  const cascadeId = match ? match[1] : null;
  return {
    fsPath,
    realPath,
    isSymlink,
    cascadeId,
    isBrainArtifact: Boolean(cascadeId)
  };
}

function preprocessCarousels(markdownText) {
  return String(markdownText || "").replace(
    /`{3,}carousel\s*\n([\s\S]*?)`{3,}/gi,
    (_, inner) => {
      const slides = inner
        .split(/<!--\s*slide\s*-->/i)
        .map((s) => s.trim())
        .filter(Boolean);
      if (!slides.length) return _;
      const slidesHtml = slides
        .map(
          (slideMd, i) =>
            `<div class="agy-carousel-slide${i === 0 ? " active" : ""}">\n\n${slideMd}\n\n</div>`
        )
        .join("\n");
      return (
        `<div class="agy-carousel">` +
        `<div class="agy-carousel-header">` +
        `<span class="agy-carousel-counter">Slide 1 of ${slides.length}</span>` +
        `<div class="agy-carousel-controls">` +
        `<button type="button" class="agy-btn agy-carousel-prev">← Prev</button>` +
        `<button type="button" class="agy-btn agy-carousel-next">Next →</button>` +
        `</div>` +
        `</div>` +
        `${slidesHtml}` +
        `</div>\n`
      );
    }
  );
}

function postprocessAlertsInHtml(html) {
  return String(html || "").replace(
    /<blockquote>\s*<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s*<br\s*\/?>|\s*\n|\s+)?([\s\S]*?)<\/blockquote>/gi,
    (_, rawType, innerRest) => {
      const type = rawType.toLowerCase();
      const icon = ALERT_ICONS[type] || "";
      const label = ALERT_LABELS[type] || rawType;
      const body = innerRest.trim().startsWith("</p>")
        ? innerRest.trim().slice(4)
        : `<p>${innerRest}`;
      return (
        `<div class="markdown-alert markdown-alert-${type}">` +
        `<p class="markdown-alert-title">${icon}${label}</p>` +
        `${body}` +
        `</div>`
      );
    }
  );
}

class AntigravityMarkdownReviewProvider {
  constructor(context) {
    this.context = context;
  }

  async openCustomDocument(uri) {
    return {
      uri,
      dispose: () => {}
    };
  }

  async resolveCustomEditor(document, webviewPanel) {
    const webview = webviewPanel.webview;
    const info = resolveRealFileInfo(document.uri);
    const localRoots = [
      vscode.Uri.joinPath(this.context.extensionUri, "media"),
      vscode.Uri.file(path.dirname(info.fsPath)),
      vscode.Uri.file(path.dirname(info.realPath)),
      vscode.Uri.file(os.homedir())
    ];
    if (vscode.workspace.workspaceFolders) {
      for (const wf of vscode.workspace.workspaceFolders) {
        localRoots.push(wf.uri);
      }
    }

    webview.options = {
      enableScripts: true,
      localResourceRoots: localRoots
    };

    const renderToWebview = async () => {
      let rawText = "";
      try {
        rawText = fs.readFileSync(info.realPath, "utf8");
      } catch (err) {
        try {
          rawText = fs.readFileSync(info.fsPath, "utf8");
        } catch (err2) {
          rawText = `# Unable to read file\n\n\`${info.fsPath}\``;
        }
      }

      const prepped = preprocessCarousels(rawText);
      let renderedHtml = "";
      try {
        renderedHtml = await vscode.commands.executeCommand("markdown.api.render", prepped);
      } catch (_) {
        renderedHtml = `<pre>${escapeHtml(rawText)}</pre>`;
      }

      renderedHtml = postprocessAlertsInHtml(renderedHtml);
      renderedHtml = rewriteLocalImageUris(renderedHtml, webview, path.dirname(info.realPath));

      const cssUri = webview.asWebviewUri(
        vscode.Uri.joinPath(this.context.extensionUri, "media", "antigravity-markdown.css")
      );
      const jsUri = webview.asWebviewUri(
        vscode.Uri.joinPath(this.context.extensionUri, "media", "antigravity-markdown.js")
      );

      const displayPath = info.isSymlink
        ? `${path.basename(info.fsPath)} → ${shortenHome(info.realPath)}`
        : shortenHome(info.fsPath);

      webview.html = buildWebviewHtml({
        cssUri,
        jsUri,
        renderedHtml,
        displayPath,
        isBrainArtifact: info.isBrainArtifact,
        isSymlink: info.isSymlink
      });
    };

    await renderToWebview();

    const disposables = [];

    // Watch text document changes in VS Code
    disposables.push(
      vscode.workspace.onDidChangeTextDocument((e) => {
        if (
          e.document.uri.fsPath === info.fsPath ||
          e.document.uri.fsPath === info.realPath
        ) {
          renderToWebview();
        }
      })
    );

    // Watch underlying file on disk (including symlink target in brain)
    const watchedPaths = new Set([info.fsPath, info.realPath]);
    for (const wp of watchedPaths) {
      try {
        if (fs.existsSync(wp)) {
          const watcher = fs.watch(wp, { persistent: false }, () => {
            renderToWebview();
          });
          disposables.push({ dispose: () => watcher.close() });
        }
      } catch (_) {
        // ignore watcher errors
      }
    }

    // Handle toolbar & link clicks from webview
    disposables.push(
      webview.onDidReceiveMessage(async (msg) => {
        if (!msg || !msg.type) return;
        if (msg.type === "editSource") {
          await vscode.commands.executeCommand(
            "vscode.openWith",
            document.uri,
            "default",
            msg.beside ? vscode.ViewColumn.Beside : webviewPanel.viewColumn
          );
        } else if (msg.type === "openNativeArtifact") {
          await openInNativeArtifactViewer(info);
        } else if (msg.type === "copyRaw") {
          try {
            const raw = fs.readFileSync(info.realPath, "utf8");
            await vscode.env.clipboard.writeText(raw);
            vscode.window.setStatusBarMessage("Antigravity: Copied raw Markdown to clipboard", 2500);
          } catch (_) {}
        } else if (msg.type === "openLink") {
          await handleWebviewLinkClick(msg.href, info);
        }
      })
    );

    webviewPanel.onDidDispose(() => {
      for (const d of disposables) {
        try {
          d.dispose();
        } catch (_) {}
      }
    });
  }
}

async function openInNativeArtifactViewer(info) {
  let targetUri = vscode.Uri.file(info.realPath);
  if (info.cascadeId) {
    targetUri = targetUri.with({ query: `cascadeId=${info.cascadeId}` });
  }
  try {
    await vscode.commands.executeCommand("vscode.openWith", targetUri, "antigravity.artifactEditor");
  } catch (_) {
    vscode.window.showInformationMessage("Native Antigravity Artifact Viewer is not available for this file.");
  }
}

async function handleWebviewLinkClick(href, currentInfo) {
  if (!href) return;

  if (href.startsWith("conversation://")) {
    const convId = href.replace(/^conversation:\/\//i, "").trim().replace(/\/$/, "");
    try {
      await vscode.commands.executeCommand("antigravity.openConversation", convId);
      return;
    } catch (_) {
      // Fallback: open that conversation's brain directory or PROJECT_HUB.md if present
      const candidates = [
        path.join(os.homedir(), ".gemini", "antigravity-cli", "brain", convId, "PROJECT_HUB.md"),
        path.join(os.homedir(), ".gemini", "antigravity", "brain", convId, "PROJECT_HUB.md")
      ];
      for (const c of candidates) {
        if (fs.existsSync(c)) {
          await vscode.commands.executeCommand("vscode.open", vscode.Uri.file(c));
          return;
        }
      }
      return;
    }
  }

  if (/^https?:\/\//i.test(href) || /^mailto:/i.test(href)) {
    await vscode.env.openExternal(vscode.Uri.parse(href));
    return;
  }

  // Handle file:// or relative file paths with optional #L10-L20 line fragments
  let rawPath = href;
  let fragment = "";
  const hashIdx = rawPath.indexOf("#");
  if (hashIdx !== -1) {
    fragment = rawPath.slice(hashIdx + 1);
    rawPath = rawPath.slice(0, hashIdx);
  }

  let targetFsPath = "";
  if (rawPath.startsWith("file://")) {
    try {
      targetFsPath = vscode.Uri.parse(rawPath).fsPath;
    } catch (_) {
      targetFsPath = decodeURIComponent(rawPath.replace(/^file:\/\//i, ""));
    }
  } else if (rawPath) {
    targetFsPath = path.resolve(path.dirname(currentInfo.realPath), decodeURIComponent(rawPath));
  } else {
    return;
  }

  if (!fs.existsSync(targetFsPath)) {
    // Also try resolving relative to the shortcut's directory
    const altPath = path.resolve(path.dirname(currentInfo.fsPath), decodeURIComponent(rawPath));
    if (fs.existsSync(altPath)) {
      targetFsPath = altPath;
    }
  }

  const targetUri = vscode.Uri.file(targetFsPath);
  const lineMatch = fragment.match(/^L(\d+)(?:-L?(\d+))?$/i);
  if (lineMatch) {
    const startLine = Math.max(0, parseInt(lineMatch[1], 10) - 1);
    const endLine = lineMatch[2] ? Math.max(startLine, parseInt(lineMatch[2], 10) - 1) : startLine;
    const doc = await vscode.workspace.openTextDocument(targetUri);
    const editor = await vscode.window.showTextDocument(doc);
    const range = new vscode.Range(startLine, 0, endLine, 999);
    editor.selection = new vscode.Selection(range.start, range.end);
    editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
    return;
  }

  if (/\.(md|markdown)$/i.test(targetFsPath)) {
    await vscode.commands.executeCommand("vscode.openWith", targetUri, "antigravity.markdownReview");
  } else {
    await vscode.commands.executeCommand("vscode.open", targetUri);
  }
}

function rewriteLocalImageUris(html, webview, baseDir) {
  return String(html || "").replace(
    /(<img\b[^>]*?\bsrc=["'])([^"']+)(["'][^>]*>)/gi,
    (full, prefix, src, suffix) => {
      if (/^(?:https?:|data:|vscode-webview-resource:)/i.test(src)) {
        return full;
      }
      let fsPath = src;
      if (src.startsWith("file://")) {
        try {
          fsPath = vscode.Uri.parse(src).fsPath;
        } catch (_) {
          fsPath = decodeURIComponent(src.replace(/^file:\/\//i, ""));
        }
      } else {
        fsPath = path.resolve(baseDir, decodeURIComponent(src));
      }
      const webviewUri = webview.asWebviewUri(vscode.Uri.file(fsPath));
      return `${prefix}${webviewUri}${suffix}`;
    }
  );
}

function shortenHome(p) {
  const home = os.homedir();
  return p.startsWith(home) ? "~" + p.slice(home.length) : p;
}

function escapeHtml(s) {
  return String(s || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function buildWebviewHtml({ cssUri, jsUri, renderedHtml, displayPath, isBrainArtifact, isSymlink }) {
  const brainBadge = isBrainArtifact
    ? `<span class="agy-badge agy-badge-brain" title="Synced with Antigravity Brain">${isSymlink ? "Brain Shortcut" : "Brain Artifact"}</span>`
    : "";
  const nativeBtn = isBrainArtifact
    ? `<button type="button" class="agy-btn" id="btn-native" title="Open in Native Antigravity Artifact Viewer">Native Viewer ↗</button>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <link rel="stylesheet" href="${cssUri}" />
  <title>Antigravity Markdown Review</title>
</head>
<body class="agy-review-body vscode-dark">
  <div class="agy-toolbar">
    <div class="agy-toolbar-left">
      <span class="agy-badge">✦ Antigravity Review</span>
      ${brainBadge}
      <span class="agy-filepath" title="${escapeHtml(displayPath)}">${escapeHtml(displayPath)}</span>
    </div>
    <div class="agy-toolbar-actions">
      ${nativeBtn}
      <button type="button" class="agy-btn" id="btn-copy" title="Copy raw Markdown">Copy MD</button>
      <button type="button" class="agy-btn" id="btn-split" title="Open raw Markdown beside this review">Split Edit</button>
      <button type="button" class="agy-btn" id="btn-edit" title="Switch to raw Markdown editor">Edit Raw</button>
    </div>
  </div>
  <main class="agy-review-container" id="agy-content">
    ${renderedHtml}
  </main>
  <script src="${jsUri}"></script>
  <script>
    (function() {
      const vscode = acquireVsCodeApi();
      const btnEdit = document.getElementById("btn-edit");
      const btnSplit = document.getElementById("btn-split");
      const btnCopy = document.getElementById("btn-copy");
      const btnNative = document.getElementById("btn-native");

      if (btnEdit) btnEdit.addEventListener("click", () => vscode.postMessage({ type: "editSource", beside: false }));
      if (btnSplit) btnSplit.addEventListener("click", () => vscode.postMessage({ type: "editSource", beside: true }));
      if (btnCopy) btnCopy.addEventListener("click", () => vscode.postMessage({ type: "copyRaw" }));
      if (btnNative) btnNative.addEventListener("click", () => vscode.postMessage({ type: "openNativeArtifact" }));

      document.addEventListener("click", (e) => {
        const a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
        if (!a) return;
        const href = a.getAttribute("href") || "";
        if (!href) return;
        if (href.startsWith("#")) {
          const target = document.getElementById(href.slice(1));
          if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: "smooth" });
          }
          return;
        }
        e.preventDefault();
        vscode.postMessage({ type: "openLink", href });
      });
    })();
  </script>
</body>
</html>`;
}

function syncMarkdownPreviewEnhanced(extensionPath) {
  try {
    const crossnoteDir = path.join(os.homedir(), ".local", "state", "crossnote");
    fs.mkdirSync(crossnoteDir, { recursive: true });

    const cssSource = fs.readFileSync(
      path.join(extensionPath, "media", "antigravity-markdown.css"),
      "utf8"
    );

    const styleLessPath = path.join(crossnoteDir, "style.less");
    const beginMarker = "/* BEGIN ANTIGRAVITY MARKDOWN STYLE */";
    const endMarker = "/* END ANTIGRAVITY MARKDOWN STYLE */";
    const styleBlock = `${beginMarker}\n${cssSource}\n${endMarker}`;

    let existingStyle = "";
    if (fs.existsSync(styleLessPath)) {
      existingStyle = fs.readFileSync(styleLessPath, "utf8");
    }
    if (existingStyle.includes(beginMarker) && existingStyle.includes(endMarker)) {
      const startIdx = existingStyle.indexOf(beginMarker);
      const endIdx = existingStyle.indexOf(endMarker) + endMarker.length;
      existingStyle = existingStyle.slice(0, startIdx) + styleBlock + existingStyle.slice(endIdx);
    } else {
      existingStyle = existingStyle.trimEnd() + "\n\n" + styleBlock + "\n";
    }
    fs.writeFileSync(styleLessPath, existingStyle, "utf8");

    // Also configure Crossnote parser.js so [!NOTE]/[!TIP]/[!IMPORTANT]/[!WARNING]/[!CAUTION]
    // and ```carousel blocks render in Markdown Preview Enhanced
    const parserJsPath = path.join(crossnoteDir, "parser.js");
    const parserCode = `({
  // Managed by Antigravity Markdown Review (iamqazolp.agy-markdown-review)
  onWillParseMarkdown: async function(markdown) {
    return String(markdown || "").replace(
      /\`{3,}carousel\\s*\\n([\\s\\S]*?)\`{3,}/gi,
      function(_, inner) {
        const slides = inner.split(/<!--\\s*slide\\s*-->/i).map(s => s.trim()).filter(Boolean);
        if (!slides.length) return _;
        return '<div class="agy-carousel">' +
          '<div class="agy-carousel-header"><span class="agy-carousel-counter">Carousel (' + slides.length + ' slides)</span></div>' +
          slides.map((s) => '<div class="agy-carousel-slide active">\\n\\n' + s + '\\n\\n</div>').join("\\n") +
          '</div>\\n';
      }
    );
  },

  onDidParseMarkdown: async function(html) {
    const icons = ${JSON.stringify(ALERT_ICONS)};
    const labels = ${JSON.stringify(ALERT_LABELS)};
    let out = String(html || "").replace(
      /<blockquote>\\s*<p>\\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\\](?:\\s*<br\\s*\\/?>|\\s*\\n|\\s+)?([\\s\\S]*?)<\\/blockquote>/gi,
      function(_, rawType, rest) {
        const t = rawType.toLowerCase();
        const body = rest.trim().startsWith("</p>") ? rest.trim().slice(4) : "<p>" + rest;
        return '<div class="markdown-alert markdown-alert-' + t + '">' +
          '<p class="markdown-alert-title">' + (icons[t] || "") + (labels[t] || rawType) + '</p>' +
          body + '</div>';
      }
    );
    out = out.replace(/<table(\\b[^>]*)>/gi, '<div class="agy-table-wrapper"><table$1>');
    out = out.replace(/<\\/table>/gi, '</table></div>');
    return out;
  },
})
`;
    fs.writeFileSync(parserJsPath, parserCode, "utf8");
  } catch (_) {
    // Ignore errors if crossnote dir is not writable
  }
}

function extendMarkdownItWithAntigravity(md) {
  const defaultFence =
    md.renderer.rules.fence ||
    function (tokens, idx, options, env, self) {
      return self.renderToken(tokens, idx, options);
    };

  md.renderer.rules.fence = function (tokens, idx, options, env, self) {
    const token = tokens[idx];
    const info = (token.info || "").trim().toLowerCase();
    if (info === "carousel") {
      const slides = (token.content || "")
        .split(/<!--\s*slide\s*-->/i)
        .map((s) => s.trim())
        .filter(Boolean);
      if (slides.length) {
        const slidesHtml = slides
          .map(
            (s, i) =>
              `<div class="agy-carousel-slide${i === 0 ? " active" : ""}">${md.render(s)}</div>`
          )
          .join("");
        return (
          `<div class="agy-carousel">` +
          `<div class="agy-carousel-header">` +
          `<span class="agy-carousel-counter">Slide 1 of ${slides.length}</span>` +
          `<div class="agy-carousel-controls">` +
          `<button type="button" class="agy-btn agy-carousel-prev">← Prev</button>` +
          `<button type="button" class="agy-btn agy-carousel-next">Next →</button>` +
          `</div>` +
          `</div>` +
          `${slidesHtml}` +
          `</div>`
        );
      }
    }
    return defaultFence(tokens, idx, options, env, self);
  };

  return md;
}

function activate(context) {
  const provider = new AntigravityMarkdownReviewProvider(context);

  context.subscriptions.push(
    vscode.window.registerCustomEditorProvider("antigravity.markdownReview", provider, {
      webviewOptions: { retainContextWhenHidden: true },
      supportsMultipleEditorsPerDocument: true
    })
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("agyMarkdown.openReview", async (uri) => {
      const targetUri =
        uri instanceof vscode.Uri
          ? uri
          : vscode.window.activeTextEditor
          ? vscode.window.activeTextEditor.document.uri
          : null;
      if (!targetUri) return;
      await vscode.commands.executeCommand("vscode.openWith", targetUri, "antigravity.markdownReview");
    }),
    vscode.commands.registerCommand("agyMarkdown.openReviewBeside", async (uri) => {
      const targetUri =
        uri instanceof vscode.Uri
          ? uri
          : vscode.window.activeTextEditor
          ? vscode.window.activeTextEditor.document.uri
          : null;
      if (!targetUri) return;
      await vscode.commands.executeCommand(
        "vscode.openWith",
        targetUri,
        "antigravity.markdownReview",
        vscode.ViewColumn.Beside
      );
    }),
    vscode.commands.registerCommand("agyMarkdown.editSource", async (uri) => {
      let targetUri = uri instanceof vscode.Uri ? uri : null;
      if (!targetUri && vscode.window.tabGroups.activeTabGroup.activeTab) {
        const input = vscode.window.tabGroups.activeTabGroup.activeTab.input;
        if (input && input.uri) {
          targetUri = input.uri;
        }
      }
      if (!targetUri) return;
      await vscode.commands.executeCommand("vscode.openWith", targetUri, "default");
    }),
    vscode.commands.registerCommand("agyMarkdown.openNativeArtifactViewer", async (uri) => {
      const targetUri =
        uri instanceof vscode.Uri
          ? uri
          : vscode.window.activeTextEditor
          ? vscode.window.activeTextEditor.document.uri
          : null;
      if (!targetUri) return;
      await openInNativeArtifactViewer(resolveRealFileInfo(targetUri));
    }),
    vscode.commands.registerCommand("agyMarkdown.syncMpeTheme", () => {
      syncMarkdownPreviewEnhanced(context.extensionPath);
      vscode.window.showInformationMessage(
        "Antigravity Markdown style synced to Markdown Preview Enhanced."
      );
    })
  );

  const cfg = vscode.workspace.getConfiguration("agyMarkdown");
  if (cfg.get("syncMarkdownPreviewEnhanced", true)) {
    syncMarkdownPreviewEnhanced(context.extensionPath);
  }

  return {
    extendMarkdownIt(md) {
      return extendMarkdownItWithAntigravity(md);
    }
  };
}

function deactivate() {}

module.exports = {
  activate,
  deactivate
};
