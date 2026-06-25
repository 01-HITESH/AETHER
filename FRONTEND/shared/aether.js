/*
 * AETHER — shared frontend runtime
 * --------------------------------
 * One script, loaded on every page (added just before </body>). It provides:
 *   • AetherAPI    — thin fetch wrapper around the /api backend with bearer auth
 *   • session guard — redirect to auth when logged out / into app when logged in
 *   • label nav     — every button/link navigates according to its visible text
 *   • toasts        — lightweight feedback for success/error
 *   • page modules  — per-page wiring keyed off the folder name in the URL
 *
 * The page markup is never restructured; behaviour is attached on top of it.
 */
(function () {
  "use strict";

  // ===========================================================================
  // Config & helpers
  // ===========================================================================
  var APP_BASE = "/app";            // FRONTEND is mounted here by the backend
  var API_BASE = "/api";
  var PAGE = "aether_authentication/code.html"; // overwritten below

  function page(folder) { return APP_BASE + "/" + folder + "/code.html"; }

  // Resolve which design folder we are on from the path.
  (function detectPage() {
    var m = location.pathname.match(/\/([a-z0-9_]+)\/code\.html/i);
    PAGE = m ? m[1] : "";
  })();

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function textOf(el) { return (el.textContent || "").replace(/\s+/g, " ").trim(); }
  function actionText(el) {
    var parts = [
      textOf(el),
      el.getAttribute && el.getAttribute("title"),
      el.getAttribute && el.getAttribute("aria-label"),
      el.getAttribute && el.getAttribute("data-action"),
    ];
    var icon = el.querySelector && el.querySelector(".material-symbols-outlined");
    if (icon) parts.push(textOf(icon));
    return parts.filter(Boolean).join(" ").replace(/\s+/g, " ").trim();
  }

  // ===========================================================================
  // API client
  // ===========================================================================
  // The original mockups ship inline parse-time guards that check
  // sessionStorage['aetherSession']. We keep that key in sync with our own
  // token so those guards pass and never fight our unified auth (no redirect
  // loop). aether.js is the single source of truth.
  var SESSION_KEY = "aetherSession";
  function syncSession(user) {
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify({
        email: (user && user.email) || "",
        name: (user && user.name) || "Designer",
        signedInAt: new Date().toISOString(),
      }));
    } catch (e) { /* sessionStorage may be unavailable */ }
  }
  function clearSession() { try { sessionStorage.removeItem(SESSION_KEY); } catch (e) {} }

  var AetherAPI = {
    base: API_BASE,
    getToken: function () { return localStorage.getItem("aether_token") || ""; },
    setToken: function (t) { t ? localStorage.setItem("aether_token", t) : localStorage.removeItem("aether_token"); },
    setUser: function (u) { localStorage.setItem("aether_user", JSON.stringify(u || {})); if (u) syncSession(u); },
    getUser: function () { try { return JSON.parse(localStorage.getItem("aether_user") || "{}"); } catch (e) { return {}; } },
    isAuthed: function () { return !!this.getToken(); },

    request: function (path, opts) {
      opts = opts || {};
      var headers = opts.headers || {};
      var token = this.getToken();
      if (token) headers["Authorization"] = "Bearer " + token;
      if (opts.json !== undefined) {
        headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(opts.json);
      }
      return fetch(API_BASE + path, {
        method: opts.method || "GET",
        headers: headers,
        body: opts.body,
      }).then(function (r) {
        return r.text().then(function (txt) {
          var data = {};
          try { data = txt ? JSON.parse(txt) : {}; } catch (e) { data = { detail: txt }; }
          if (!r.ok) {
            var err = new Error((data && data.detail) || ("Request failed (" + r.status + ")"));
            err.status = r.status; err.data = data;
            throw err;
          }
          return data;
        });
      });
    },

    register: function (name, email, password) {
      return this.request("/auth/register", { method: "POST", json: { name: name, email: email, password: password } });
    },
    login: function (email, password) {
      return this.request("/auth/login", { method: "POST", json: { email: email, password: password } });
    },
    logout: function () {
      var self = this;
      return this.request("/auth/logout", { method: "POST" }).catch(function () {}).then(function () {
        self.setToken(""); localStorage.removeItem("aether_user"); clearSession();
      });
    },
    me: function () { return this.request("/me"); },
    patchMe: function (patch) { return this.request("/me", { method: "PATCH", json: patch }); },
    patchPassword: function (currentPassword, newPassword) {
      return this.request("/me/password", {
        method: "PATCH",
        json: { currentPassword: currentPassword, newPassword: newPassword },
      });
    },

    upload: function (file) {
      var fd = new FormData();
      fd.append("file", file);
      return this.request("/upload", { method: "POST", body: fd });
    },
    createTour: function (payload) { return this.request("/tours", { method: "POST", json: payload }); },
    listTours: function () { return this.request("/tours"); },
    getTour: function (id) { return this.request("/tours/" + encodeURIComponent(id)); },
    saveTour: function (id) { return this.request("/tours/" + encodeURIComponent(id) + "/save", { method: "POST" }); },
    favoriteTour: function (id) { return this.request("/tours/" + encodeURIComponent(id) + "/favorite", { method: "POST" }); },
    deleteTour: function (id) { return this.request("/tours/" + encodeURIComponent(id), { method: "DELETE" }); },
    exportUrl: function (id, kind) {
      var token = this.getToken();
      var url = API_BASE + "/tours/" + encodeURIComponent(id) + "/export/" + encodeURIComponent(kind);
      return token ? url + "?token=" + encodeURIComponent(token) : url;
    },
  };
  window.AetherAPI = AetherAPI;

  // Session draft (selections carried across the wizard) -----------------------
  var Draft = {
    get: function () { try { return JSON.parse(sessionStorage.getItem("aether_draft") || "{}"); } catch (e) { return {}; } },
    set: function (patch) {
      var d = this.get(); Object.assign(d, patch);
      sessionStorage.setItem("aether_draft", JSON.stringify(d));
      return d;
    },
    clear: function () { sessionStorage.removeItem("aether_draft"); },
  };
  window.AetherDraft = Draft;

  // ===========================================================================
  // Toasts
  // ===========================================================================
  function toast(message, kind) {
    var host = $("#aether-toast-host");
    if (!host) {
      host = document.createElement("div");
      host.id = "aether-toast-host";
      host.style.cssText = "position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:10px;";
      document.body.appendChild(host);
    }
    var el = document.createElement("div");
    var border = kind === "error" ? "rgba(255,180,171,0.5)" : "rgba(212,197,169,0.5)";
    var color = kind === "error" ? "#ffb4ab" : "#d4c5a9";
    el.style.cssText =
      "min-width:220px;max-width:340px;padding:12px 16px;border-radius:10px;" +
      "background:rgba(19,19,21,0.92);backdrop-filter:blur(18px);border:1px solid " + border + ";" +
      "color:" + color + ";font:500 14px Inter,sans-serif;box-shadow:0 8px 30px rgba(0,0,0,0.4);" +
      "opacity:0;transform:translateY(-8px);transition:all .25s ease;";
    el.textContent = message;
    host.appendChild(el);
    requestAnimationFrame(function () { el.style.opacity = "1"; el.style.transform = "translateY(0)"; });
    setTimeout(function () {
      el.style.opacity = "0"; el.style.transform = "translateY(-8px)";
      setTimeout(function () { el.remove(); }, 250);
    }, kind === "error" ? 4200 : 2600);
  }
  window.aetherToast = toast;

  // ===========================================================================
  // Session guard
  // ===========================================================================
  var PUBLIC_PAGES = {
    "aether_authentication": true,
    "aether_ai_interior_design_hero_1": true,
    "aether_ai_interior_design_hero_2": true,
  };
  function guard() {
    var authed = AetherAPI.isAuthed();
    if (PAGE === "aether_authentication") {
      if (authed) location.replace(page("aether_dashboard"));
      return;
    }
    if (!PUBLIC_PAGES[PAGE] && !authed) {
      location.replace(page("aether_authentication"));
    }
  }

  // ===========================================================================
  // Label-based navigation
  // ===========================================================================
  // Visible text (lowercased, exact-or-includes) -> destination folder.
  var NAV_MAP = [
    // sidebar / global
    ["dashboard", "aether_dashboard"],
    ["new design", "aether_upload_room"],
    ["create new design", "aether_upload_room"],
    ["my projects", "aether_project_details"],
    ["saved designs", "aether_saved_designs"],
    ["browse styles", "aether_style_selection"],
    ["view saved designs", "aether_saved_designs"],
    ["continue last project", "aether_project_details"],
    ["profile", "aether_profile_settings"],
    ["settings", "aether_profile_settings"],
    ["account", "aether_profile_settings"],
    ["upload room", "aether_upload_room"],
    ["generate space", "aether_upload_room"],
    ["studio", "aether_dashboard"],
    ["resources", "aether_project_details"],
    // hero / marketing
    ["start designing", "aether_upload_room"],
    ["view demo", "aether_interactive_3d_walkthrough"],
    ["get started", "aether_upload_room"],
    // wizard
    ["continue to style selection", "aether_style_selection"],
    ["continue to requirements", "aether_describe_requirements"],
    ["select style", "aether_style_selection"],
    ["generate design", "aether_generating_design"],
    ["view results", "aether_explore_results"],
    ["explore results", "aether_explore_results"],
    // results / viewer
    ["open 3d walkthrough", "aether_interactive_3d_walkthrough"],
    ["3d walkthrough", "aether_interactive_3d_walkthrough"],
    ["immersive view", "aether_immersive_3d_walkthrough_pro"],
    ["project details", "aether_project_details"],
    ["view details", "aether_project_details"],
    // gallery
    ["gallery", "aether_saved_designs"],
  ];

  // Buttons whose behaviour is owned by a page module — never auto-navigate these.
  var RESERVED_TEXT = [
    "browse files", "sign in", "sign up", "log in", "login", "create account",
    "continue with google", "save design", "save", "share", "export 3d",
    "export model", "export report", "export pdf", "download", "download hd",
    "cancel generation", "delete", "refresh", "back", "logout", "log out",
    "upgrade to pro", "rotate", "pan", "zoom", "measure", "snapshot",
    "reset view", "detailed style report", "edit", "save changes",
  ];

  function reserved(t) {
    for (var i = 0; i < RESERVED_TEXT.length; i++) if (t === RESERVED_TEXT[i]) return true;
    return false;
  }
  function resolveTarget(t) {
    for (var i = 0; i < NAV_MAP.length; i++) {
      if (t === NAV_MAP[i][0]) return NAV_MAP[i][1];
    }
    for (var j = 0; j < NAV_MAP.length; j++) {
      if (t.indexOf(NAV_MAP[j][0]) >= 0) return NAV_MAP[j][1];
    }
    return null;
  }

  function wireGlobalNav() {
    document.addEventListener("click", function (e) {
      var el = e.target.closest("a, button");
      if (!el || el.dataset.aetherHandled) return;
      var t = actionText(el).toLowerCase();
      if (!t) return;
      if (t.indexOf("logout") >= 0 || t.indexOf("log out") >= 0) {
        e.preventDefault();
        AetherAPI.logout().then(function () { location.href = page("aether_authentication"); });
        return;
      }
      // Honour real hrefs that already point somewhere meaningful.
      var href = el.getAttribute && el.getAttribute("href");
      if (href && href !== "#" && href.charAt(0) !== "#" && !/^javascript:/i.test(href)) return;

      if (reserved(t)) return; // page module handles it
      var target = resolveTarget(t);
      if (target && target !== PAGE) {
        e.preventDefault();
        location.href = page(target);
      } else if (href === "#" && /privacy|terms|legal|contact|press|sustainability|notifications|filter|sort|resources/.test(t)) {
        e.preventDefault();
        toast("This local demo action is available without leaving AETHER.");
      }
    }, true);
  }

  // Carry an active tour id through links that lead to viewer/results pages.
  function withTour(folder) {
    var id = Draft.get().tourId || new URLSearchParams(location.search).get("tour");
    return id ? page(folder) + "?tour=" + encodeURIComponent(id) : page(folder);
  }

  // ===========================================================================
  // Page modules
  // ===========================================================================
  var Pages = {};

  // ---- Authentication -------------------------------------------------------
  Pages.aether_authentication = function () {
    function val(id) { var el = document.getElementById(id); return el ? el.value.trim() : ""; }

    var done = function (res) {
      AetherAPI.setToken(res.token); AetherAPI.setUser(res.user);
      toast("Welcome to AETHER, " + (res.user.name || "Designer") + ".");
      setTimeout(function () { location.href = page("aether_dashboard"); }, 500);
    };
    var fail = function (err) { toast(err.message || "Authentication failed.", "error"); };

    function doSignIn(e) {
      if (e) e.preventDefault();
      var email = val("email"), password = val("password");
      if (!email || !password) { toast("Please enter your email and password.", "error"); return; }
      AetherAPI.login(email, password).then(done).catch(function (err) {
        // First-time email: auto-provision so the demo flows smoothly.
        if (err.status === 401) AetherAPI.register("Designer", email, password).then(done).catch(fail);
        else fail(err);
      });
    }

    function doSignUp(e) {
      if (e) e.preventDefault();
      var name = val("name"), email = val("email-up"), password = val("password-up"), confirm = val("password-confirm");
      if (!email || !password) { toast("Please complete the sign-up form.", "error"); return; }
      if (confirm && password !== confirm) { toast("Passwords do not match.", "error"); return; }
      AetherAPI.register(name, email, password).then(done).catch(function (err) {
        if (err.status === 409) AetherAPI.login(email, password).then(done).catch(fail); // already exists → log in
        else fail(err);
      });
    }

    // Wire the two real forms / submit buttons by their IDs.
    var signInForm = document.getElementById("signInFormElement");
    var signUpForm = document.getElementById("signUpFormElement");
    if (signInForm) signInForm.addEventListener("submit", doSignIn);
    if (signUpForm) signUpForm.addEventListener("submit", doSignUp);
    var siBtn = document.getElementById("signInSubmit");
    var suBtn = document.getElementById("signUpSubmit");
    if (siBtn) { siBtn.addEventListener("click", doSignIn); siBtn.dataset.aetherHandled = "1"; }
    if (suBtn) { suBtn.addEventListener("click", doSignUp); suBtn.dataset.aetherHandled = "1"; }

    // Neutralise the mockup's "Continue with Google" → dashboard bypass.
    $all("button").forEach(function (b) {
      if (textOf(b).toLowerCase().indexOf("google") >= 0) {
        b.removeAttribute("onclick");
        b.dataset.aetherHandled = "1";
        b.addEventListener("click", function (e) {
          e.preventDefault();
          toast("Social sign-in is disabled offline — use email & password.", "error");
        });
      }
    });
  };

  // ---- Dashboard ------------------------------------------------------------
  Pages.aether_dashboard = function () {
    var u = AetherAPI.getUser();
    $all("[data-aether-username]").forEach(function (el) { el.textContent = u.name || "Designer"; });
    AetherAPI.me().then(function (res) {
      syncDashboardStats(res.stats || {});
      if (res.user) {
        AetherAPI.setUser(res.user);
        $all("[data-aether-username]").forEach(function (el) { el.textContent = res.user.name || "Designer"; });
      }
    }).catch(function () {});
    AetherAPI.listTours().then(function (res) {
      var tours = res.tours || [];
      syncDashboardStats({
        projects: tours.length,
        saved: tours.filter(function (t) { return t.saved; }).length,
        favorites: tours.filter(function (t) { return t.favorite; }).length,
      });
      renderTourCards(tours);
    }).catch(function () {});
  };

  // ---- Upload room ----------------------------------------------------------
  Pages.aether_upload_room = function () {
    // Create the real (hidden) file input.
    var fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = "image/png,image/jpeg,image/jpg";
    fileInput.style.display = "none";
    document.body.appendChild(fileInput);

    var dropzone = $(".dropzone-border") || $(".glass-card");
    var continueBtn = findButtonByText(/continue to style/i) || findButtonByText(/continue/i);
    if (continueBtn) { continueBtn.classList.add("opacity-50", "cursor-not-allowed"); }

    var roomType = "living_room";
    var ROOM_KEYS = {
      "living room": "living_room", "bedroom": "bedroom", "kitchen": "kitchen",
      "bathroom": "bathroom", "office": "office", "hall": "hall",
    };
    // Track room-type radio selection by its label text.
    $all('input[name="room_type"]').forEach(function (radio) {
      var label = radio.closest("label");
      var name = label ? textOf(label).toLowerCase() : "";
      Object.keys(ROOM_KEYS).forEach(function (k) { if (name.indexOf(k) >= 0) radio._roomKey = ROOM_KEYS[k]; });
      radio.addEventListener("change", function () { if (radio._roomKey) { roomType = radio._roomKey; Draft.set({ roomType: roomType }); } });
      if (radio.checked && radio._roomKey) roomType = radio._roomKey;
    });

    var existingDraft = Draft.get();
    var uploaded = !!existingDraft.uploadId;
    if (uploaded && continueBtn) continueBtn.classList.remove("opacity-50", "cursor-not-allowed");
    if (uploaded && existingDraft.sourceUrl) showPreview(existingDraft.sourceUrl);
    function handleFile(file) {
      if (!file) return;
      if (!/image\/(png|jpe?g)/i.test(file.type)) { toast("Please choose a JPG or PNG image.", "error"); return; }
      if (file.size > 20 * 1024 * 1024) { toast("Image exceeds the 20MB limit.", "error"); return; }

      // Live preview inside the dropzone.
      var reader = new FileReader();
      reader.onload = function (ev) { showPreview(ev.target.result); };
      reader.readAsDataURL(file);

      toast("Uploading photo…");
      AetherAPI.upload(file).then(function (res) {
        uploaded = true;
        Draft.set({ uploadId: res.uploadId, roomType: roomType, sourceUrl: res.url });
        if (continueBtn) { continueBtn.classList.remove("opacity-50", "cursor-not-allowed"); }
        toast("Photo uploaded. Continue to choose a style.");
      }).catch(function (err) { toast(err.message || "Upload failed.", "error"); });
    }

    function showPreview(src) {
      if (!dropzone) return;
      var img = dropzone.querySelector(".aether-preview");
      if (!img) {
        img = document.createElement("img");
        img.className = "aether-preview";
        img.style.cssText = "position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:inherit;z-index:1;";
        dropzone.style.position = "relative";
        dropzone.appendChild(img);
      }
      img.src = src;
    }

    if (dropzone) {
      dropzone.addEventListener("click", function () { fileInput.click(); });
      ["dragover", "dragenter"].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) { e.preventDefault(); dropzone.classList.add("dropzone-hover"); });
      });
      ["dragleave", "drop"].forEach(function (ev) {
        dropzone.addEventListener(ev, function (e) { e.preventDefault(); });
      });
      dropzone.addEventListener("drop", function (e) {
        e.preventDefault();
        if (e.dataTransfer.files && e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
      });
    }
    var browseBtn = findButtonByText(/browse files/i);
    if (browseBtn) {
      browseBtn.dataset.aetherHandled = "1";
      browseBtn.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); fileInput.click(); });
    }
    fileInput.addEventListener("change", function () { if (fileInput.files[0]) handleFile(fileInput.files[0]); });

    if (continueBtn) {
      continueBtn.dataset.aetherHandled = "1";
      continueBtn.addEventListener("click", function (e) {
        e.preventDefault();
        if (!uploaded) { toast("Please upload a room photo first.", "error"); return; }
        location.href = page("aether_style_selection");
      });
    }
    wireBack();
  };

  // ---- Style selection ------------------------------------------------------
  Pages.aether_style_selection = function () {
    var selected = Draft.get().style || "modern";
    // Style cards: capture the chosen style by its heading text.
    var cards = $all(".glass-card, [data-style]").filter(function (card) {
      var h = card.querySelector("h3, h4");
      return h && matchStyle(textOf(h).toLowerCase());
    });
    cards.forEach(function (card) {
      var key = matchStyle(textOf(card.querySelector("h3, h4")).toLowerCase());
      card.addEventListener("click", function () {
        selected = key; Draft.set({ style: key });
        // Move the existing "selected" highlight to the clicked card.
        cards.forEach(function (c) { c.classList.remove("style-selected"); });
        card.classList.add("style-selected");
        toast(prettyStyle(key) + " style selected.");
      });
    });
    var cont = findButtonByText(/continue to requirements/i) || findButtonByText(/continue/i);
    if (cont) {
      cont.dataset.aetherHandled = "1";
      cont.addEventListener("click", function (e) { e.preventDefault(); Draft.set({ style: selected }); location.href = page("aether_describe_requirements"); });
    }
    wireBack();
  };

  // ---- Describe requirements ------------------------------------------------
  Pages.aether_describe_requirements = function () {
    var selectedPalette = [];
    $all("button.font-label-sm").forEach(function (chip) {
      var label = textOf(chip);
      if (!label || /add custom|generate|back/i.test(label)) return;
      chip.dataset.aetherHandled = "1";
      if (/border-secondary|bg-secondary/.test(chip.className)) selectedPalette.push(label);
      chip.addEventListener("click", function (e) {
        e.preventDefault();
        var active = chip.dataset.aetherSelected !== "1";
        chip.dataset.aetherSelected = active ? "1" : "0";
        chip.classList.toggle("border-secondary", active);
        chip.classList.toggle("text-secondary", active);
        chip.classList.toggle("bg-secondary/10", active);
        selectedPalette = $all("button.font-label-sm")
          .filter(function (b) { return b.dataset.aetherSelected === "1" || /border-secondary|bg-secondary/.test(b.className); })
          .map(function (b) { return textOf(b); })
          .filter(Boolean);
      });
    });
    var gen = findButtonByText(/generate design/i);
    if (gen) {
      gen.dataset.aetherHandled = "1";
      gen.addEventListener("click", function (e) {
      e.preventDefault();
      var textareas = $all("textarea");
      var notes = textareas.map(function (t) { return t.value.trim(); }).filter(Boolean).join(" | ");
      var budget = $("input[type='range']");
      Draft.set({ requirements: {
        notes: notes,
        palette: selectedPalette,
        budget_level: budget ? Number(budget.value) : null,
      } });
      location.href = page("aether_generating_design");
      });
    }
    wireBack();
  };

  // ---- Generating design (+ animated variant) -------------------------------
  function generatingModule() {
    var d = Draft.get();
    var viewBtn = findButtonByText(/view results/i);

    // Width bars to animate (the design uses h-full bg-secondary w-[72%] etc.).
    var bars = $all(".h-full.bg-secondary, [class*='bg-secondary'][class*='w-']");
    // Percentage label: the span that currently reads like "72%".
    var pctLabel = null;
    $all("span").forEach(function (s) { if (!pctLabel && /^\d{1,3}%$/.test(textOf(s))) pctLabel = s; });

    if (!d.uploadId) {
      toast("No uploaded photo found — returning to upload.", "error");
      setTimeout(function () { location.href = page("aether_upload_room"); }, 1500);
      return;
    }

    toast("Generating your 360° tour…");
    var pct = 0;
    var fakeTimer = setInterval(function () {
      pct = Math.min(92, pct + Math.random() * 9);
      setProgress(pct);
    }, 320);

    AetherAPI.createTour({
      uploadId: d.uploadId,
      roomType: d.roomType || "living_room",
      style: d.style || "modern",
      requirements: d.requirements || {},
    }).then(function (res) {
      clearInterval(fakeTimer);
      setProgress(100);
      Draft.set({ tourId: res.tourId });
      toast("Tour ready. Opening results…");
      if (viewBtn) {
        viewBtn.classList.remove("opacity-50", "cursor-not-allowed", "bg-white/5");
        viewBtn.classList.add("bg-secondary", "text-on-secondary");
        viewBtn.removeAttribute("disabled");
        viewBtn.addEventListener("click", function (e) { e.preventDefault(); location.href = page("aether_explore_results") + "?tour=" + res.tourId; });
      }
      setTimeout(function () { location.href = page("aether_explore_results") + "?tour=" + res.tourId; }, 1200);
    }).catch(function (err) {
      clearInterval(fakeTimer);
      toast(err.message || "Generation failed.", "error");
    });

    function setProgress(p) {
      var v = Math.round(p);
      if (pctLabel) pctLabel.textContent = v + "%";
      $all("[data-aether-progress]").forEach(function (el) { el.textContent = v + "%"; });
      bars.forEach(function (b) { b.style.width = v + "%"; });
    }

    var cancel = findButtonByText(/cancel generation/i);
    if (cancel) {
      cancel.dataset.aetherHandled = "1";
      cancel.addEventListener("click", function (e) { e.preventDefault(); clearInterval(fakeTimer); location.href = page("aether_upload_room"); });
    }
  }
  Pages.aether_generating_design = generatingModule;
  Pages.aether_generating_design_animated = generatingModule;

  // ---- Explore results (+ interactive variant) ------------------------------
  function resultsModule() {
    var id = new URLSearchParams(location.search).get("tour") || Draft.get().tourId;
    var open = findButtonByText(/open 3d walkthrough/i) || findButtonByText(/3d walkthrough/i);
    if (open) open.addEventListener("click", function (e) {
      e.preventDefault();
      location.href = page("aether_interactive_3d_walkthrough") + (id ? "?tour=" + id : "");
    });
    var save = findButtonByText(/^save design$/i) || findButtonByText(/save design/i);
    if (save && id) save.addEventListener("click", function (e) {
      e.preventDefault();
      AetherAPI.saveTour(id).then(function () { toast("Design saved to your library."); }).catch(function (err) { toast(err.message, "error"); });
    });
    wireExportButtons(id);
    wireIconButtons(id);
    if (!id) return;
    AetherAPI.getTour(id).then(function (res) {
      var tour = res.tour;
      Draft.set({ tourId: tour.id });
      populateTourText(tour);
      bindTourImages(tour);
    }).catch(function () {});
  }
  Pages.aether_explore_results = resultsModule;
  Pages.aether_explore_results_interactive = resultsModule;

  // ---- Project details ------------------------------------------------------
  Pages.aether_project_details = function () {
    var open = findButtonByText(/open 3d walkthrough/i) || findButtonByText(/3d walkthrough/i);
    AetherAPI.listTours().then(function (res) {
      var tours = res.tours || [];
      var id = new URLSearchParams(location.search).get("tour") || (tours[0] && tours[0].id);
      if (open) {
        open.dataset.aetherHandled = "1";
        open.addEventListener("click", function (e) { e.preventDefault(); location.href = page("aether_interactive_3d_walkthrough") + (id ? "?tour=" + id : ""); });
      }
      wireExportButtons(id);
      wireIconButtons(id);
      if (tours[0]) {
        var t = tours.filter(function (tour) { return tour.id === id; })[0] || tours[0];
        populateTourText(t);
        bindTourImages(t);
      }
    }).catch(function () {
      if (open) open.addEventListener("click", function (e) { e.preventDefault(); location.href = page("aether_interactive_3d_walkthrough"); });
    });
  };

  // ---- Saved designs --------------------------------------------------------
  Pages.aether_saved_designs = function () {
    AetherAPI.listTours().then(function (res) {
      renderTourCards(res.tours || [], { allowDelete: true });
      wireSavedFilters(res.tours || []);
    }).catch(function () {});
  };

  // ---- Profile settings -----------------------------------------------------
  Pages.aether_profile_settings = function () {
    var currentUser = null;
    AetherAPI.me().then(function (res) {
      var u = res.user, s = res.stats;
      currentUser = u;
      AetherAPI.setUser(u);
      syncProfileIdentity(u);
      syncDashboardStats(s || {});
      $all("[data-aether-username]").forEach(function (el) { el.textContent = u.name; });
      $all("[data-aether-email]").forEach(function (el) { el.textContent = u.email; });
      $all("[data-aether-stat-projects]").forEach(function (el) { el.textContent = s.projects; });
      $all("[data-aether-stat-saved]").forEach(function (el) { el.textContent = s.saved; });
      applyProfileSettings(u.settings || {});
    }).catch(function () {});
    var save = findButtonByText(/save changes/i);
    if (save) {
      save.dataset.aetherHandled = "1";
      save.addEventListener("click", function (e) {
        e.preventDefault();
        var settings = {};
        $all("input[type='checkbox']").forEach(function (input, i) { settings["toggle_" + (i + 1)] = input.checked; });
        var range = $("input[type='range']");
        if (range) settings.design_intensity = Number(range.value);
        var patch = { settings: settings };
        if (currentUser && currentUser.name) patch.name = currentUser.name;
        AetherAPI.patchMe(patch).then(function (res) {
          currentUser = res.user;
          AetherAPI.setUser(res.user);
          syncProfileIdentity(res.user);
          toast("Profile settings saved.");
        }).catch(function (err) { toast(err.message || "Could not save settings.", "error"); });
      });
    }
    var cancel = findButtonByText(/^cancel$/i);
    if (cancel) {
      cancel.dataset.aetherHandled = "1";
      cancel.addEventListener("click", function (e) { e.preventDefault(); location.href = page("aether_dashboard"); });
    }
    wireProfileAccountActions(function () { return currentUser; }, function (u) { currentUser = u; });
  };

  // The 3D viewer pages are handled by pano-viewer.js; nothing extra needed here,
  // but we still wire global nav + back on them.
  Pages.aether_interactive_3d_walkthrough = function () { wireViewerActions(); };
  Pages.aether_immersive_3d_walkthrough_pro = function () { wireViewerActions(); };
  Pages.aether_pro_3d_walkthrough_viewer = function () { wireViewerActions(); };
  Pages.aether_refined_3d_walkthrough = function () {};

  function wireViewerActions() {
    var id = new URLSearchParams(location.search).get("tour") || Draft.get().tourId;
    var save = findButtonByText(/save design/i);
    if (save && id) save.addEventListener("click", function (e) {
      e.preventDefault();
      AetherAPI.saveTour(id).then(function () { toast("Design saved."); }).catch(function (err) { toast(err.message, "error"); });
    });
    wireExportButtons(id);
    wireIconButtons(id);
    if (id) AetherAPI.getTour(id).then(function (res) { populateTourText(res.tour); }).catch(function () {});
  }

  // ===========================================================================
  // Shared helpers
  // ===========================================================================
  function findButtonByText(re) {
    var els = $all("button, a");
    for (var i = 0; i < els.length; i++) if (re.test(textOf(els[i]))) return els[i];
    return null;
  }
  function wireBack() {
    var back = findButtonByText(/^back$/i);
    if (back) {
      back.dataset.aetherHandled = "1";
      back.addEventListener("click", function (e) { e.preventDefault(); history.length > 1 ? history.back() : (location.href = page("aether_dashboard")); });
    }
  }

  function applyProfileSettings(settings) {
    $all("input[type='checkbox']").forEach(function (input, i) {
      var key = "toggle_" + (i + 1);
      if (Object.prototype.hasOwnProperty.call(settings, key)) input.checked = !!settings[key];
    });
    var range = $("input[type='range']");
    if (range && settings.design_intensity !== undefined) range.value = settings.design_intensity;
  }

  function wireProfileAccountActions(getUser, setUser) {
    $all("button").forEach(function (btn) {
      var t = actionText(btn).toLowerCase();
      if (t.indexOf("edit profile information") >= 0) {
        btn.dataset.aetherHandled = "1";
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          var user = getUser() || AetherAPI.getUser();
          var name = prompt("Profile name", user.name || "Designer");
          if (name === null) return;
          name = name.trim();
          if (!name) { toast("Profile name cannot be empty.", "error"); return; }
          AetherAPI.patchMe({ name: name }).then(function (res) {
            setUser(res.user);
            AetherAPI.setUser(res.user);
            syncProfileIdentity(res.user);
            toast("Profile updated.");
          }).catch(function (err) { toast(err.message || "Could not update profile.", "error"); });
        });
      } else if (t.indexOf("change password") >= 0) {
        btn.dataset.aetherHandled = "1";
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          var currentPassword = prompt("Current password");
          if (currentPassword === null) return;
          var newPassword = prompt("New password");
          if (newPassword === null) return;
          if (newPassword.length < 4) { toast("New password must be at least 4 characters.", "error"); return; }
          AetherAPI.patchPassword(currentPassword, newPassword).then(function () {
            toast("Password updated.");
          }).catch(function (err) { toast(err.message || "Could not update password.", "error"); });
        });
      } else if (t.indexOf("two-factor") >= 0 || t.indexOf("active sessions") >= 0) {
        btn.dataset.aetherHandled = "1";
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          toast("This account setting is tracked locally in this build.");
        });
      }
    });
  }

  function populateTourText(tour) {
    if (!tour) return;
    $all("h1,h2,h3,h4,p,span").forEach(function (el) {
      var t = textOf(el);
      if (/obsidian lounge|main living area|living room .* modern|modern .* living room/i.test(t)) {
        if (/obsidian lounge|modern .* living room/i.test(t)) el.textContent = tour.title || t;
        else if (/living room .* modern/i.test(t)) el.textContent = (tour.room_label || "") + " / " + (tour.style_label || "");
      }
    });
    applyRequirementText(tour);
  }

  function asset(tour, kind) {
    if (!tour) return "";
    if (kind === "source") return tour.source_url || "";
    if (kind === "redesign") return tour.redesign_url || tour.thumb_url || tour.pano_url || "";
    if (kind === "pano") return tour.pano_url || tour.redesign_url || tour.thumb_url || "";
    return tour.thumb_url || tour.redesign_url || tour.pano_url || tour.source_url || "";
  }

  function bindTourImages(tour) {
    if (!tour) return;
    var source = asset(tour, "source");
    var redesign = asset(tour, "redesign");
    var thumb = asset(tour, "thumb");
    var pano = asset(tour, "pano");

    $all("img").forEach(function (img) {
      var context = (
        (img.getAttribute("alt") || "") + " " +
        (img.getAttribute("data-alt") || "") + " " +
        contextText(img)
      ).toLowerCase();
      if (/account|profile|architect profile|avatar/.test(context)) return;
      if (/before|original|empty room|existing/.test(context)) setImage(img, source);
      else if (/after|generated|redesign|visualization|concept|render|interior design/.test(context)) setImage(img, redesign || thumb);
      else if (/panorama|360|walkthrough/.test(context)) setImage(img, pano);
      else if (img.closest("#comparison-slider,#slider-container,.comparison-after,#after-image,#slider-after")) setImage(img, redesign || thumb);
    });

    var comparison = $("#comparison-slider") || $("#slider-container");
    if (comparison) {
      var imgs = $all("img", comparison).filter(function (img) {
        return !/account|profile|avatar/i.test((img.getAttribute("alt") || "") + " " + (img.getAttribute("data-alt") || ""));
      });
      if (imgs[0]) setImage(imgs[0], source);
      if (imgs[1]) setImage(imgs[1], redesign || thumb);
    }
    var interactive = $("#slider-after");
    if (interactive) {
      var afterImg = $("img", interactive);
      if (afterImg) setImage(afterImg, redesign || thumb);
      var beforeImg = interactive.parentElement && $("img", interactive.parentElement);
      if (beforeImg) setImage(beforeImg, source);
    }

    $all("[style*='background-image']").forEach(function (el) {
      var label = contextText(el).toLowerCase();
      if (/before|upload|source|original/.test(label)) setBackground(el, source);
      else setBackground(el, thumb || redesign || pano);
    });

    updateComparisonSizing();
  }

  function contextText(el) {
    var bits = [];
    var node = el;
    for (var i = 0; node && i < 3; i++, node = node.parentElement) {
      bits.push(node.id || "");
      bits.push(node.className || "");
      bits.push(node.getAttribute && (node.getAttribute("aria-label") || ""));
    }
    return bits.join(" ");
  }

  function setImage(img, url) {
    if (!img || !url) return;
    img.src = url;
    img.removeAttribute("srcset");
    img.removeAttribute("data-alt");
    img.loading = "eager";
    img.decoding = "async";
  }

  function setBackground(el, url) {
    if (!el || !url) return;
    el.style.backgroundImage = "url('" + url + "')";
  }

  function updateComparisonSizing() {
    var afterContainer = $("#after-image-container");
    var comparison = $("#comparison-slider");
    if (afterContainer && comparison) {
      var afterImg = $("img", afterContainer);
      if (afterImg) {
        var rect = comparison.getBoundingClientRect();
        afterImg.style.width = Math.max(1, rect.width) + "px";
        afterImg.style.height = Math.max(1, rect.height) + "px";
        afterImg.style.maxWidth = "none";
      }
    }
  }

  function applyRequirementText(tour) {
    var req = tour.requirements || {};
    var notes = (req.notes || "").toString();
    if (!notes) return;
    $all("p").forEach(function (el) {
      var t = textOf(el);
      if (/maximize natural light|specific brands|constraints|atmosphere|functionality|design goals/i.test(t)) {
        el.textContent = notes.length > 180 ? notes.slice(0, 177) + "..." : notes;
      }
    });
  }

  function syncDashboardStats(stats) {
    var projects = Number(stats.projects || 0);
    var saved = Number(stats.saved || 0);
    var favorites = Number(stats.favorites || 0);
    setMetric("designs generated", projects);
    setMetric("3d models created", projects);
    setMetric("360", projects);
    setMetric("saved designs", saved);
    setMetric("favorites", favorites);
    $all("[data-aether-stat-projects]").forEach(function (el) { el.textContent = projects; });
    $all("[data-aether-stat-saved]").forEach(function (el) { el.textContent = saved; });
    $all("[data-aether-stat-favorites]").forEach(function (el) { el.textContent = favorites; });
  }

  function syncProfileIdentity(user) {
    if (!user) return;
    $all("h1,h2,h3,h4,p,span").forEach(function (el) {
      var t = textOf(el);
      if (/alexander thorne|alex thorne|designer$/i.test(t) && user.name) {
        el.textContent = user.name;
      } else if (/alex\.thorne@studio\.aether|@/.test(t) && t.indexOf("mailto:") < 0 && user.email) {
        if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t)) el.textContent = user.email;
      } else if (/member since/i.test(t) && user.created_at) {
        el.textContent = "Member since " + formatDate(user.created_at);
      }
    });
  }

  function formatDate(value) {
    var d = new Date(value);
    if (isNaN(d.getTime())) return value;
    return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  }

  function setMetric(label, value) {
    $all("p,span").forEach(function (el) {
      var t = textOf(el).toLowerCase();
      if (t.indexOf(label) < 0) return;
      var box = el.parentElement;
      if (!box) return;
      var values = $all("p,span", box).filter(function (v) { return v !== el && /^\d+$/.test(textOf(v)); });
      if (values[0]) values[0].textContent = String(value);
    });
  }

  function wireExportButtons(id) {
    $all("button, a").forEach(function (el) {
      var t = actionText(el).toLowerCase();
      if (!t) return;
      var kind = null;
      if (t.indexOf("download hd") >= 0 || t === "download" || t.indexOf(" download") >= 0) kind = "hd";
      else if (t.indexOf("export pdf") >= 0 || t.indexOf("report") >= 0) kind = "report";
      else if (t.indexOf("export 3d") >= 0 || t.indexOf("export model") >= 0 || t.indexOf("view_in_ar") >= 0) kind = "model";
      else if (t.indexOf("share") >= 0 || t.indexOf("ios_share") >= 0) kind = "share";
      else if (t.indexOf("generate more") >= 0) kind = "generate";
      else if (t.indexOf("upgrade to pro") >= 0) kind = "pro";
      if (!kind) return;
      el.dataset.aetherHandled = "1";
      el.addEventListener("click", function (e) {
        e.preventDefault();
        if (kind === "generate") { location.href = page("aether_upload_room"); return; }
        if (kind === "pro") { toast("Pro controls are enabled in this local build."); return; }
        if (!id) { toast("Generate a tour first.", "error"); return; }
        if (kind === "share") {
          var url = location.origin + page("aether_interactive_3d_walkthrough") + "?tour=" + encodeURIComponent(id);
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(url).then(function () { toast("Viewer link copied."); }).catch(function () { toast(url); });
          } else {
            toast(url);
          }
          return;
        }
        window.open(AetherAPI.exportUrl(id, kind), "_blank");
      });
    });
  }

  function wireIconButtons(id) {
    $all("button").forEach(function (btn) {
      var t = actionText(btn).toLowerCase();
      if (t.indexOf("bookmark") >= 0 || t.indexOf("favorite") >= 0) {
        btn.dataset.aetherHandled = "1";
        btn.addEventListener("click", function (e) {
          e.preventDefault(); e.stopPropagation();
          if (!id) { toast("Generate a tour first.", "error"); return; }
          AetherAPI.favoriteTour(id).then(function () { toast("Favorite updated."); }).catch(function (err) { toast(err.message, "error"); });
        });
      } else if (t.indexOf("delete") >= 0) {
        btn.dataset.aetherHandled = "1";
        btn.setAttribute("data-aether-delete", "1");
        btn.addEventListener("click", function (e) {
          e.preventDefault(); e.stopPropagation();
          if (!id) { toast("No generated design selected.", "error"); return; }
          AetherAPI.deleteTour(id).then(function () { toast("Design deleted."); location.href = page("aether_saved_designs"); }).catch(function (err) { toast(err.message, "error"); });
        });
      } else if (t.indexOf("download") >= 0) {
        btn.dataset.aetherHandled = "1";
      }
    });
  }

  function wireSavedFilters(tours) {
    var buttons = $all("button");
    buttons.forEach(function (btn) {
      var label = textOf(btn).toLowerCase();
      if (!/all projects|living room|bedroom|kitchen|office|luxury|modern/.test(label)) return;
      btn.dataset.aetherHandled = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        buttons.forEach(function (b) { b.classList.remove("border-secondary", "text-secondary", "bg-secondary/10"); });
        btn.classList.add("border-secondary", "text-secondary", "bg-secondary/10");
        var filtered = label === "all projects" ? tours : tours.filter(function (t) {
          return (t.room_label || "").toLowerCase().indexOf(label) >= 0 || (t.style_label || "").toLowerCase().indexOf(label) >= 0;
        });
        renderTourCards(filtered, { allowDelete: true });
      });
    });
  }

  var STYLE_KEYS = ["modern", "minimalist", "luxury", "scandinavian", "japanese zen", "industrial", "contemporary", "traditional", "bohemian", "classical"];
  function matchStyle(name) {
    for (var i = 0; i < STYLE_KEYS.length; i++) {
      if (name.indexOf(STYLE_KEYS[i]) >= 0) return STYLE_KEYS[i].replace(" ", "_");
    }
    return null;
  }
  function prettyStyle(k) { return k.replace("_", " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); }); }

  // Render real tour cards by cloning the first existing card in a grid so the
  // styling exactly matches the mockup. Falls back to a styled card if none.
  function renderTourCards(tours, opts) {
    opts = opts || {};
    // Find the grid whose first child looks like a content card (has an image).
    var grids = $all(".grid");
    var grid = null, template = null;
    for (var i = 0; i < grids.length; i++) {
      var first = grids[i].children[0];
      if (first && (first.querySelector("img") || first.querySelector("[style*='background-image']"))) {
        grid = grids[i]; template = first; break;
      }
    }
    if (!grid || !template) return;
    if (!tours.length) {
      while (grid.firstChild) grid.removeChild(grid.firstChild);
      var empty = document.createElement("div");
      empty.className = "glass-panel rounded-xl p-6 text-on-surface-variant";
      empty.textContent = "No generated designs yet. Create a new design to populate this space.";
      grid.appendChild(empty);
      return;
    }

    // Build real cards from the template so styling matches the mockup exactly.
    var fragment = document.createDocumentFragment();
    tours.forEach(function (t) {
      var card = template.cloneNode(true);
      card.dataset.aetherTourId = t.id;
      card.style.display = "";
      var preview = asset(t, "thumb");
      var img = card.querySelector("img");
      if (img && preview) { img.src = preview; img.removeAttribute("data-alt"); img.removeAttribute("srcset"); }
      card.querySelectorAll("[style*='background-image']").forEach(function (el) {
        if (preview) el.style.backgroundImage = "url('" + preview + "')";
      });
      var h = card.querySelector("h1,h2,h3,h4,h5");
      if (h) h.textContent = t.title;
      var detail = card.querySelector("p");
      if (detail) detail.textContent = (t.room_label || "") + " / " + (t.style_label || "");
      card.querySelectorAll("button").forEach(function (btn) {
        var txt = actionText(btn).toLowerCase();
        if (txt.indexOf("delete") >= 0) {
          btn.dataset.aetherHandled = "1";
          btn.setAttribute("data-aether-delete", "1");
          btn.addEventListener("click", function (e) {
            e.preventDefault(); e.stopPropagation();
            AetherAPI.deleteTour(t.id).then(function () { toast("Design deleted."); card.remove(); }).catch(function (err) { toast(err.message, "error"); });
          });
        } else if (txt.indexOf("favorite") >= 0 || txt.indexOf("bookmark") >= 0) {
          btn.dataset.aetherHandled = "1";
          btn.addEventListener("click", function (e) {
            e.preventDefault(); e.stopPropagation();
            AetherAPI.favoriteTour(t.id).then(function () { toast("Favorite updated."); }).catch(function (err) { toast(err.message, "error"); });
          });
        } else if (txt.indexOf("download") >= 0) {
          btn.dataset.aetherHandled = "1";
          btn.addEventListener("click", function (e) {
            e.preventDefault(); e.stopPropagation();
            window.open(AetherAPI.exportUrl(t.id, "hd"), "_blank");
          });
        }
      });
      card.style.cursor = "pointer";
      card.addEventListener("click", function (ev) {
        var del = ev.target.closest && ev.target.closest("[data-aether-delete]");
        if (del) return;
        location.href = page("aether_interactive_3d_walkthrough") + "?tour=" + t.id;
      });
      fragment.appendChild(card);
    });

    // Replace the static placeholder cards with the real ones.
    while (grid.firstChild) grid.removeChild(grid.firstChild);
    grid.appendChild(fragment);
  }

  // ===========================================================================
  // Boot
  // ===========================================================================
  function boot() {
    guard();
    // Restore aetherSession on every page load so inline mockup guards pass
    // even in new tabs where only the localStorage token survived.
    if (AetherAPI.isAuthed()) syncSession(AetherAPI.getUser());
    wireGlobalNav();
    var mod = Pages[PAGE];
    if (mod) { try { mod(); } catch (e) { console.error("[AETHER] page module error:", e); } }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
