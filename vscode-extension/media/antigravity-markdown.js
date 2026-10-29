/* ==========================================================================
   Antigravity Markdown Review — Client Enhancer
   Runs in VS Code Built-in Markdown Preview, Antigravity Custom Editor,
   and Markdown Preview Enhanced.
   ========================================================================== */
(function () {
  "use strict";

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

  function transformAlerts(root) {
    const blockquotes = root.querySelectorAll("blockquote:not(.markdown-alert)");
    blockquotes.forEach((bq) => {
      const firstP = bq.querySelector("p:first-child");
      if (!firstP) return;
      const text = firstP.innerHTML.trim();
      const match = text.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s*<br\s*\/?>|\s*\n|\s+)?([\s\S]*)$/i);
      if (!match) return;

      const type = match[1].toLowerCase();
      const remainder = match[2] || "";

      const alertDiv = document.createElement("div");
      alertDiv.className = "markdown-alert markdown-alert-" + type;

      const titleP = document.createElement("p");
      titleP.className = "markdown-alert-title";
      titleP.innerHTML = (ALERT_ICONS[type] || "") + ALERT_LABELS[type];
      alertDiv.appendChild(titleP);

      if (remainder.trim()) {
        firstP.innerHTML = remainder.trim();
      } else {
        firstP.remove();
      }

      while (bq.firstChild) {
        alertDiv.appendChild(bq.firstChild);
      }
      bq.replaceWith(alertDiv);
    });
  }

  function transformTables(root) {
    const tables = root.querySelectorAll("table");
    tables.forEach((table) => {
      if (table.parentElement && table.parentElement.classList.contains("agy-table-wrapper")) {
        return;
      }
      const wrapper = document.createElement("div");
      wrapper.className = "agy-table-wrapper";
      table.parentNode.insertBefore(wrapper, table);
      wrapper.appendChild(table);
    });
  }

  function detectLanguage(pre, code) {
    const classes = ((code ? code.className : "") + " " + pre.className).split(/\s+/);
    for (const cls of classes) {
      const m = cls.match(/^(?:language-|lang-)(.+)$/i);
      if (m && m[1] && m[1] !== "text" && m[1] !== "plaintext") {
        return m[1].toLowerCase();
      }
    }
    return pre.getAttribute("data-lang") || "";
  }

  function transformCodeBlocks(root) {
    const pres = root.querySelectorAll("pre");
    pres.forEach((pre) => {
      if (
        pre.parentElement &&
        (pre.parentElement.classList.contains("agy-code-block") ||
          pre.classList.contains("mermaid"))
      ) {
        return;
      }
      const code = pre.querySelector("code");
      const lang = detectLanguage(pre, code);

      if (lang === "carousel") {
        transformCarouselPre(pre, code ? code.textContent : pre.textContent);
        return;
      }
      if (lang === "mermaid") {
        return;
      }

      const wrapper = document.createElement("div");
      wrapper.className = "agy-code-block";

      const header = document.createElement("div");
      header.className = "agy-code-header";

      const langSpan = document.createElement("span");
      langSpan.className = "agy-code-lang";
      langSpan.textContent = lang || "code";

      const copyBtn = document.createElement("button");
      copyBtn.className = "agy-copy-btn";
      copyBtn.type = "button";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", () => {
        const raw = code ? code.innerText : pre.innerText;
        navigator.clipboard.writeText(raw).then(() => {
          copyBtn.textContent = "Copied!";
          setTimeout(() => {
            copyBtn.textContent = "Copy";
          }, 1500);
        });
      });

      header.appendChild(langSpan);
      header.appendChild(copyBtn);

      pre.parentNode.insertBefore(wrapper, pre);
      wrapper.appendChild(header);
      wrapper.appendChild(pre);
    });
  }

  function transformCarouselPre(pre, rawText) {
    const slides = String(rawText || "")
      .split(/<!--\s*slide\s*-->/i)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!slides.length) return;

    const container = document.createElement("div");
    container.className = "agy-carousel";

    let idx = 0;
    const header = document.createElement("div");
    header.className = "agy-carousel-header";

    const counter = document.createElement("span");
    counter.textContent = "Slide 1 of " + slides.length;

    const controls = document.createElement("div");
    controls.className = "agy-carousel-controls";

    const prevBtn = document.createElement("button");
    prevBtn.className = "agy-btn";
    prevBtn.textContent = "← Prev";

    const nextBtn = document.createElement("button");
    nextBtn.className = "agy-btn";
    nextBtn.textContent = "Next →";

    controls.appendChild(prevBtn);
    controls.appendChild(nextBtn);
    header.appendChild(counter);
    header.appendChild(controls);
    container.appendChild(header);

    const slideEls = slides.map((slideText, i) => {
      const el = document.createElement("div");
      el.className = "agy-carousel-slide" + (i === 0 ? " active" : "");
      const p = document.createElement("pre");
      p.textContent = slideText;
      el.appendChild(p);
      container.appendChild(el);
      return el;
    });

    function showSlide(nextIdx) {
      idx = (nextIdx + slideEls.length) % slideEls.length;
      slideEls.forEach((el, i) => el.classList.toggle("active", i === idx));
      counter.textContent = "Slide " + (idx + 1) + " of " + slideEls.length;
    }

    prevBtn.addEventListener("click", () => showSlide(idx - 1));
    nextBtn.addEventListener("click", () => showSlide(idx + 1));

    pre.replaceWith(container);
  }

  function bindInteractiveCarousels(root) {
    root.querySelectorAll(".agy-carousel[data-agy-bound!='1']").forEach((carousel) => {
      carousel.setAttribute("data-agy-bound", "1");
      const slideEls = Array.from(carousel.querySelectorAll(".agy-carousel-slide"));
      if (!slideEls.length) return;
      const counter = carousel.querySelector(".agy-carousel-counter");
      const prevBtn = carousel.querySelector(".agy-carousel-prev");
      const nextBtn = carousel.querySelector(".agy-carousel-next");
      let idx = 0;
      function show(nextIdx) {
        idx = (nextIdx + slideEls.length) % slideEls.length;
        slideEls.forEach((el, i) => el.classList.toggle("active", i === idx));
        if (counter) counter.textContent = "Slide " + (idx + 1) + " of " + slideEls.length;
      }
      if (prevBtn) prevBtn.addEventListener("click", () => show(idx - 1));
      if (nextBtn) nextBtn.addEventListener("click", () => show(idx + 1));
    });
  }

  function decorateLinks(root) {
    root.querySelectorAll("a[href]").forEach((a) => {
      const href = a.getAttribute("href") || "";
      if (href.startsWith("file://")) {
        a.classList.add("agy-file-link");
      } else if (href.startsWith("conversation://")) {
        a.classList.add("agy-conv-link");
      }
    });
  }

  function enhanceAll() {
    const root = document.body;
    if (!root) return;
    transformAlerts(root);
    transformTables(root);
    transformCodeBlocks(root);
    bindInteractiveCarousels(root);
    decorateLinks(root);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", enhanceAll);
  } else {
    enhanceAll();
  }

  window.addEventListener("vscode.markdown.updateContent", () => {
    setTimeout(enhanceAll, 10);
  });

  let debounceTimer = null;
  const observer = new MutationObserver(() => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(enhanceAll, 60);
  });
  if (document.documentElement) {
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }
})();
