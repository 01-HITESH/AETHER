/*
 * AETHER — 360° Panorama Viewer (Google Street-View style)
 * ---------------------------------------------------------
 * Renders an equirectangular panorama on the inside of a sphere using the
 * Three.js r125 build already loaded by the walkthrough pages, and provides:
 *   • drag-to-look (yaw + pitch) with inertia, mouse + touch
 *   • zoom (wheel + toolbar button) by animating the camera FOV
 *   • a draggable joystick nav bar for continuous pan/rotate
 *   • toolbar wiring: 360 auto-rotate, pan, zoom, reset, snapshot, info readout
 *
 * It reads ?tour=<id> from the URL, fetches the tour via the AETHER API and
 * loads its panorama. With no tour it falls back to a generated demo gradient
 * so the page is never blank.
 */
(function () {
  "use strict";

  if (false && typeof THREE === "undefined") {
    console.error("[AETHER] Three.js not found — viewer cannot start.");
    return;
  }

  // --- Locate the stage container the page already provides -----------------
  var container =
    document.querySelector('[id^="threejs-container-"]') ||
    document.querySelector("#threejs-viewport") ||
    document.querySelector(".aether-pano-stage");
  if (!container) {
    console.warn("[AETHER] No panorama container found on this page.");
    return;
  }
  // Remove any placeholder canvas/content the mockup shipped with.
  container.innerHTML = "";
  container.style.cursor = "grab";
  if (getComputedStyle(container).position === "static") {
    container.style.position = "relative";
  }

  var API_BASE =
    (window.AetherAPI && window.AetherAPI.base) || "/api";
  var token =
    (window.AetherAPI && window.AetherAPI.getToken && window.AetherAPI.getToken()) ||
    localStorage.getItem("aether_token") ||
    "";

  if (typeof THREE === "undefined") {
    startCanvasFallback(container, API_BASE, token);
    return;
  }

  // --- Scene setup ----------------------------------------------------------
  var width = container.clientWidth || window.innerWidth;
  var height = container.clientHeight || window.innerHeight;

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(72, width / height, 0.1, 1100);
  camera.position.set(0, 0, 0.01);

  var renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(width, height);
  container.appendChild(renderer.domElement);

  // Inverted sphere — we view it from the inside.
  var geometry = new THREE.SphereGeometry(500, 64, 48);
  geometry.scale(-1, 1, 1);
  var material = new THREE.MeshBasicMaterial({ color: 0x1b1b1d });
  var sphere = new THREE.Mesh(geometry, material);
  scene.add(sphere);

  // --- View state -----------------------------------------------------------
  var state = {
    lon: 0, lat: 0,          // current heading (degrees)
    targetLon: 0, targetLat: 0,
    fov: 72, targetFov: 72,
    autoRotate: false,
    isUserDragging: false,
  };
  var MIN_FOV = 30, MAX_FOV = 100;
  var MIN_LAT = -85, MAX_LAT = 85;

  // --- Texture loading ------------------------------------------------------
  function applyTexture(url) {
    var loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    loader.load(
      url,
      function (texture) {
        texture.minFilter = THREE.LinearFilter;
        texture.magFilter = THREE.LinearFilter;
        sphere.material = new THREE.MeshBasicMaterial({ map: texture });
        sphere.material.needsUpdate = true;
        hideLoading();
      },
      undefined,
      function () {
        showError("Could not load the panorama image.");
      }
    );
  }

  function makeDemoTexture() {
    // Procedural fallback so the viewer is never empty.
    var c = document.createElement("canvas");
    c.width = 1024; c.height = 512;
    var ctx = c.getContext("2d");
    var g = ctx.createLinearGradient(0, 0, 0, 512);
    g.addColorStop(0, "#2a2a2c");
    g.addColorStop(0.5, "#1f1f21");
    g.addColorStop(1, "#0e0e10");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 1024, 512);
    ctx.fillStyle = "rgba(212,197,169,0.85)";
    ctx.font = "28px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("Upload a room photo to generate your 360° tour", 512, 256);
    var tex = new THREE.CanvasTexture(c);
    sphere.material = new THREE.MeshBasicMaterial({ map: tex });
    hideLoading();
  }

  // --- Loading + error overlays --------------------------------------------
  var overlay = document.createElement("div");
  overlay.style.cssText =
    "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;" +
    "background:rgba(14,14,16,0.6);backdrop-filter:blur(6px);color:#d4c5a9;" +
    "font:500 14px Inter,sans-serif;letter-spacing:0.08em;z-index:5;text-transform:uppercase;";
  overlay.textContent = "Loading 360° view…";
  container.appendChild(overlay);
  function hideLoading() { overlay.style.display = "none"; }
  function showError(msg) { overlay.style.display = "flex"; overlay.textContent = msg; }

  // --- Fetch the tour -------------------------------------------------------
  function getQueryParam(name) {
    return new URLSearchParams(window.location.search).get(name);
  }
  var tourId = getQueryParam("tour") || getQueryParam("tourId");

  if (tourId) {
    fetch(API_BASE + "/tours/" + encodeURIComponent(tourId), {
      headers: token ? { Authorization: "Bearer " + token } : {},
    })
      .then(function (r) {
        if (!r.ok) throw new Error("tour fetch failed");
        return r.json();
      })
      .then(function (data) {
        var tour = data.tour || data;
        if (tour && tour.pano_url) {
          applyTexture(tour.pano_url);
          populatePanels(tour);
        } else {
          makeDemoTexture();
        }
      })
      .catch(function () {
        makeDemoTexture();
      });
  } else {
    makeDemoTexture();
  }

  // Fill in the page's project-identity panel if present (non-destructive).
  function populatePanels(tour) {
    try {
      var idEl = document.querySelector("[data-aether-tour-title]");
      if (idEl) idEl.textContent = tour.title || idEl.textContent;
      var subEl = document.querySelector("[data-aether-tour-sub]");
      if (subEl) subEl.textContent =
        (tour.room_label || "") + " • " + (tour.style || "");
    } catch (e) { /* panels are optional */ }
  }

  function populatePanels(tour) {
    try {
      var title = tour.title || "Generated Room";
      var sub = (tour.room_label || "") + " / " + (tour.style_label || tour.style || "");
      var idEl = document.querySelector("[data-aether-tour-title]");
      if (idEl) idEl.textContent = title;
      var subEl = document.querySelector("[data-aether-tour-sub]");
      if (subEl) subEl.textContent = sub;
      Array.prototype.slice.call(document.querySelectorAll("h3,h4,p,span,button")).forEach(function (el) {
        var txt = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (/the obsidian lounge|modern living room/i.test(txt)) el.textContent = title;
        else if (/living room .* modern|main living area/i.test(txt)) el.textContent = sub;
      });
    } catch (e) { /* panels are optional */ }
  }

  // --- Pointer drag-to-look -------------------------------------------------
  var pointer = { down: false, x: 0, y: 0, lon: 0, lat: 0, vx: 0, vy: 0, t: 0 };

  function onDown(clientX, clientY) {
    pointer.down = true;
    state.isUserDragging = true;
    pointer.x = clientX; pointer.y = clientY;
    pointer.lon = state.targetLon; pointer.lat = state.targetLat;
    pointer.vx = 0; pointer.vy = 0;
    container.style.cursor = "grabbing";
  }
  function onMove(clientX, clientY) {
    if (!pointer.down) return;
    var k = state.fov / 72 * 0.12;     // slower when zoomed in
    var dLon = (pointer.x - clientX) * k;
    var dLat = (clientY - pointer.y) * k;
    state.targetLon = pointer.lon + dLon;
    state.targetLat = clamp(pointer.lat + dLat, MIN_LAT, MAX_LAT);
    pointer.vx = dLon; pointer.vy = dLat;
  }
  function onUp() {
    pointer.down = false;
    state.isUserDragging = false;
    container.style.cursor = "grab";
  }

  renderer.domElement.addEventListener("mousedown", function (e) {
    e.preventDefault(); onDown(e.clientX, e.clientY);
  });
  window.addEventListener("mousemove", function (e) { onMove(e.clientX, e.clientY); });
  window.addEventListener("mouseup", onUp);

  renderer.domElement.addEventListener("touchstart", function (e) {
    if (e.touches.length === 1) onDown(e.touches[0].clientX, e.touches[0].clientY);
  }, { passive: true });
  renderer.domElement.addEventListener("touchmove", function (e) {
    if (e.touches.length === 1) {
      onMove(e.touches[0].clientX, e.touches[0].clientY);
      e.preventDefault();
    }
  }, { passive: false });
  renderer.domElement.addEventListener("touchend", onUp);

  // --- Wheel zoom -----------------------------------------------------------
  renderer.domElement.addEventListener("wheel", function (e) {
    e.preventDefault();
    state.targetFov = clamp(state.targetFov + e.deltaY * 0.05, MIN_FOV, MAX_FOV);
  }, { passive: false });

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

  // --- Public control API (used by toolbar + joystick) ----------------------
  var Viewer = {
    zoomIn: function () { state.targetFov = clamp(state.targetFov - 12, MIN_FOV, MAX_FOV); },
    zoomOut: function () { state.targetFov = clamp(state.targetFov + 12, MIN_FOV, MAX_FOV); },
    toggleAutoRotate: function () { state.autoRotate = !state.autoRotate; return state.autoRotate; },
    setAutoRotate: function (v) { state.autoRotate = !!v; },
    reset: function () {
      state.targetLon = 0; state.targetLat = 0; state.targetFov = 72;
      state.autoRotate = false;
    },
    nudge: function (dLon, dLat) {
      state.targetLon += dLon;
      state.targetLat = clamp(state.targetLat + dLat, MIN_LAT, MAX_LAT);
    },
    snapshot: function () {
      try {
        renderer.render(scene, camera);
        var url = renderer.domElement.toDataURL("image/png");
        var a = document.createElement("a");
        a.href = url;
        a.download = "aether-360-snapshot.png";
        document.body.appendChild(a); a.click(); a.remove();
      } catch (e) {
        alert("Snapshot failed: " + e.message);
      }
    },
    getHeading: function () {
      return { lon: Math.round(state.lon), lat: Math.round(state.lat), fov: Math.round(state.fov) };
    },
  };
  window.AetherViewer = Viewer;

  // --- Wire the existing floating toolbar by its button titles --------------
  // The toolbar lives in the page (sibling of the WebGL container), so search
  // the whole document and match only the known viewer-control titles/icons.
  function wireToolbar() {
    var buttons = Array.prototype.slice.call(
      document.querySelectorAll("button[title], button[data-action]")
    );
    buttons.forEach(function (btn) {
      var title = (btn.getAttribute("title") || btn.getAttribute("data-action") || "").toLowerCase();
      var icon = (btn.querySelector(".material-symbols-outlined") || {}).textContent || "";
      icon = (icon || "").trim().toLowerCase();
      var action = null;
      if (title.indexOf("rotate") >= 0 || icon === "360") action = "autorotate";
      else if (title.indexOf("pan") >= 0 || icon === "pan_tool") action = "pan";
      else if (title.indexOf("zoom") >= 0 || icon.indexOf("zoom_in") >= 0) action = "zoom";
      else if (title.indexOf("reset") >= 0 || icon === "restart_alt") action = "reset";
      else if (title.indexOf("snapshot") >= 0 || icon === "camera") action = "snapshot";
      else if (title.indexOf("measure") >= 0 || icon === "square_foot") action = "info";
      if (!action) return;

      btn.addEventListener("click", function (e) {
        e.preventDefault();
        if (action === "autorotate") {
          var on = Viewer.toggleAutoRotate();
          btn.classList.toggle("text-secondary", on);
        } else if (action === "pan") {
          container.style.cursor = "grab";
        } else if (action === "zoom") {
          if (e.shiftKey || e.altKey) Viewer.zoomOut();
          else Viewer.zoomIn();
        } else if (action === "reset") {
          Viewer.reset();
        } else if (action === "snapshot") {
          Viewer.snapshot();
        } else if (action === "info") {
          toggleReadout();
        }
      });
    });
  }

  // --- Heading / FOV readout (toggled by the "measure" button) --------------
  var readout = document.createElement("div");
  readout.style.cssText =
    "position:absolute;top:16px;right:16px;z-index:6;display:none;" +
    "padding:8px 14px;border-radius:9999px;font:600 11px Inter,sans-serif;" +
    "letter-spacing:0.12em;text-transform:uppercase;color:#e4e2e4;" +
    "background:rgba(255,255,255,0.06);backdrop-filter:blur(18px);" +
    "border:1px solid rgba(255,255,255,0.12);";
  container.appendChild(readout);
  var readoutVisible = false;
  function toggleReadout() { readoutVisible = !readoutVisible; readout.style.display = readoutVisible ? "block" : "none"; }

  // --- Joystick-style draggable navigation bar ------------------------------
  function buildJoystick() {
    var base = document.createElement("div");
    base.setAttribute("aria-label", "Navigation joystick");
    base.style.cssText =
      "position:absolute;left:50%;bottom:96px;transform:translateX(-50%);z-index:7;" +
      "width:104px;height:104px;border-radius:9999px;touch-action:none;" +
      "background:rgba(255,255,255,0.05);backdrop-filter:blur(24px);" +
      "border:1px solid rgba(255,255,255,0.12);box-shadow:0 0 30px rgba(0,0,0,0.35);" +
      "display:flex;align-items:center;justify-content:center;cursor:grab;";
    var ring = document.createElement("div");
    ring.style.cssText =
      "position:absolute;inset:10px;border-radius:9999px;border:1px dashed rgba(212,197,169,0.25);";
    var knob = document.createElement("div");
    knob.style.cssText =
      "width:40px;height:40px;border-radius:9999px;background:#d4c5a9;" +
      "box-shadow:0 0 18px rgba(212,197,169,0.45);transition:box-shadow .2s;will-change:transform;";
    base.appendChild(ring);
    base.appendChild(knob);
    container.appendChild(base);

    var dragging = false, cx = 0, cy = 0, vec = { x: 0, y: 0 };
    var R = 32; // max knob travel (px)

    function setKnob(dx, dy) {
      var d = Math.hypot(dx, dy);
      if (d > R) { dx = dx / d * R; dy = dy / d * R; }
      knob.style.transform = "translate(" + dx + "px," + dy + "px)";
      vec.x = dx / R; vec.y = dy / R;   // normalised -1..1
    }
    function startDrag(clientX, clientY) {
      dragging = true;
      var rect = base.getBoundingClientRect();
      cx = rect.left + rect.width / 2;
      cy = rect.top + rect.height / 2;
      base.style.cursor = "grabbing";
      setKnob(clientX - cx, clientY - cy);
    }
    function moveDrag(clientX, clientY) {
      if (!dragging) return;
      setKnob(clientX - cx, clientY - cy);
    }
    function endDrag() {
      dragging = false; vec.x = 0; vec.y = 0;
      knob.style.transform = "translate(0,0)";
      base.style.cursor = "grab";
    }

    base.addEventListener("mousedown", function (e) { e.preventDefault(); startDrag(e.clientX, e.clientY); });
    window.addEventListener("mousemove", function (e) { moveDrag(e.clientX, e.clientY); });
    window.addEventListener("mouseup", endDrag);
    base.addEventListener("touchstart", function (e) {
      startDrag(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault();
    }, { passive: false });
    base.addEventListener("touchmove", function (e) {
      moveDrag(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault();
    }, { passive: false });
    base.addEventListener("touchend", endDrag);

    // Continuous nudge while the knob is displaced.
    return function tickJoystick() {
      if (vec.x !== 0 || vec.y !== 0) {
        var speed = 1.6 * (state.fov / 72);
        Viewer.nudge(vec.x * speed, -vec.y * speed);
      }
    };
  }

  var tickJoystick = buildJoystick();
  wireToolbar();
  wireSceneButtons();

  // --- Animation loop -------------------------------------------------------
  function animate() {
    requestAnimationFrame(animate);

    if (state.autoRotate && !pointer.down) state.targetLon += 0.06;

    // Inertia after a flick.
    if (!pointer.down && (Math.abs(pointer.vx) > 0.01 || Math.abs(pointer.vy) > 0.01)) {
      state.targetLon += pointer.vx;
      state.targetLat = clamp(state.targetLat + pointer.vy, MIN_LAT, MAX_LAT);
      pointer.vx *= 0.92; pointer.vy *= 0.92;
    }

    tickJoystick();

    // Ease current -> target.
    state.lon += (state.targetLon - state.lon) * 0.12;
    state.lat += (state.targetLat - state.lat) * 0.12;
    state.fov += (state.targetFov - state.fov) * 0.12;

    camera.fov = state.fov;
    camera.updateProjectionMatrix();

    var phi = THREE.MathUtils.degToRad(90 - state.lat);
    var theta = THREE.MathUtils.degToRad(state.lon);
    var tx = 500 * Math.sin(phi) * Math.cos(theta);
    var ty = 500 * Math.cos(phi);
    var tz = 500 * Math.sin(phi) * Math.sin(theta);
    camera.lookAt(tx, ty, tz);

    if (readoutVisible) {
      var h = Viewer.getHeading();
      readout.textContent = "Heading " + h.lon + "°  •  Pitch " + h.lat + "°  •  FOV " + h.fov + "°";
    }

    renderer.render(scene, camera);
  }
  animate();

  // --- Resize ---------------------------------------------------------------
  function onResize() {
    var w = container.clientWidth || window.innerWidth;
    var h = container.clientHeight || window.innerHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  window.addEventListener("resize", onResize);

  function wireSceneButtons() {
    Array.prototype.slice.call(document.querySelectorAll("button")).forEach(function (btn) {
      var txt = (btn.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      if (!/main living area|dining nook|entryway/.test(txt)) return;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        Viewer.setAutoRotate(false);
        if (txt.indexOf("dining") >= 0) {
          state.targetLon = 70; state.targetLat = -4; state.targetFov = 62;
        } else if (txt.indexOf("entry") >= 0) {
          state.targetLon = -75; state.targetLat = -2; state.targetFov = 66;
        } else {
          state.targetLon = 0; state.targetLat = 0; state.targetFov = 72;
        }
        Array.prototype.slice.call((btn.parentElement || document).querySelectorAll("button")).forEach(function (b) {
          b.classList.remove("text-secondary", "border-secondary/30", "bg-white/5");
          b.classList.add("text-on-surface-variant");
        });
        btn.classList.add("text-secondary", "border-secondary/30", "bg-white/5");
      });
    });
  }

  function startCanvasFallback(container, apiBase, token) {
    container.innerHTML = "";
    if (getComputedStyle(container).position === "static") container.style.position = "relative";
    container.style.cursor = "grab";
    var canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:100%;display:block;background:#131315;";
    container.appendChild(canvas);
    var ctx = canvas.getContext("2d");
    var img = new Image();
    img.crossOrigin = "anonymous";
    var state = { lon: 0, lat: 0, fov: 1, dragging: false, x: 0, y: 0, baseLon: 0, baseLat: 0, auto: false };
    var overlay = document.createElement("div");
    overlay.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#d4c5a9;background:rgba(14,14,16,.5);font:600 12px Inter,sans-serif;letter-spacing:.12em;text-transform:uppercase;z-index:3;";
    overlay.textContent = "Loading 360 view";
    container.appendChild(overlay);

    function q(name) { return new URLSearchParams(location.search).get(name); }
    var tourId = q("tour") || q("tourId");
    if (tourId) {
      fetch(apiBase + "/tours/" + encodeURIComponent(tourId), { headers: token ? { Authorization: "Bearer " + token } : {} })
        .then(function (r) { if (!r.ok) throw new Error("tour"); return r.json(); })
        .then(function (data) { loadImage((data.tour || data).pano_url); })
        .catch(makeDemo);
    } else {
      makeDemo();
    }

    function loadImage(url) {
      img.onload = function () { overlay.style.display = "none"; resize(); draw(); };
      img.onerror = makeDemo;
      img.src = url;
    }
    function makeDemo() {
      var c = document.createElement("canvas");
      c.width = 1024; c.height = 512;
      var gctx = c.getContext("2d");
      var g = gctx.createLinearGradient(0, 0, 0, 512);
      g.addColorStop(0, "#39393b"); g.addColorStop(.55, "#1f1f21"); g.addColorStop(1, "#0e0e10");
      gctx.fillStyle = g; gctx.fillRect(0, 0, c.width, c.height);
      gctx.fillStyle = "#d4c5a9"; gctx.font = "28px Inter, sans-serif"; gctx.textAlign = "center";
      gctx.fillText("Upload a room photo to generate your 360 view", 512, 256);
      loadImage(c.toDataURL("image/png"));
    }
    function resize() {
      var rect = container.getBoundingClientRect();
      var dpr = Math.min(devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    function draw() {
      var w = canvas.clientWidth || container.clientWidth;
      var h = canvas.clientHeight || container.clientHeight;
      if (!w || !h || !img.width) return;
      ctx.clearRect(0, 0, w, h);
      var viewW = Math.max(240, img.width / state.fov);
      var viewH = Math.max(120, Math.min(img.height, viewW * h / w));
      var sx = ((state.lon % img.width) + img.width) % img.width;
      var sy = Math.max(0, Math.min(img.height - viewH, img.height / 2 - viewH / 2 - state.lat));
      function drawSlice(x, sw, dx, dw) {
        ctx.drawImage(img, x, sy, sw, viewH, dx, 0, dw, h);
      }
      if (sx + viewW <= img.width) {
        drawSlice(sx, viewW, 0, w);
      } else {
        var first = img.width - sx;
        drawSlice(sx, first, 0, w * first / viewW);
        drawSlice(0, viewW - first, w * first / viewW, w * (viewW - first) / viewW);
      }
    }
    function tick() {
      if (state.auto) state.lon += 0.45;
      draw();
      requestAnimationFrame(tick);
    }
    canvas.addEventListener("mousedown", function (e) {
      state.dragging = true; state.x = e.clientX; state.y = e.clientY; state.baseLon = state.lon; state.baseLat = state.lat; container.style.cursor = "grabbing";
    });
    window.addEventListener("mousemove", function (e) {
      if (!state.dragging) return;
      state.lon = state.baseLon - (e.clientX - state.x) * state.fov * 2.2;
      state.lat = state.baseLat + (e.clientY - state.y) * state.fov * 1.3;
    });
    window.addEventListener("mouseup", function () { state.dragging = false; container.style.cursor = "grab"; });
    canvas.addEventListener("wheel", function (e) {
      e.preventDefault();
      state.fov = Math.max(.6, Math.min(3.2, state.fov + e.deltaY * .0015));
    }, { passive: false });
    window.addEventListener("resize", function () { resize(); draw(); });
    window.AetherViewer = {
      zoomIn: function () { state.fov = Math.max(.6, state.fov - .25); },
      zoomOut: function () { state.fov = Math.min(3.2, state.fov + .25); },
      toggleAutoRotate: function () { state.auto = !state.auto; return state.auto; },
      setAutoRotate: function (v) { state.auto = !!v; },
      reset: function () { state.lon = 0; state.lat = 0; state.fov = 1; state.auto = false; },
      nudge: function (dx, dy) { state.lon += dx * 18; state.lat += dy * 10; },
      snapshot: function () {
        var a = document.createElement("a");
        a.href = canvas.toDataURL("image/png");
        a.download = "aether-360-snapshot.png";
        document.body.appendChild(a); a.click(); a.remove();
      },
      getHeading: function () { return { lon: Math.round(state.lon), lat: Math.round(state.lat), fov: Math.round(state.fov * 72) }; },
    };
    wireFallbackToolbar();
    tick();
    function wireFallbackToolbar() {
      Array.prototype.slice.call(document.querySelectorAll("button[title]")).forEach(function (btn) {
        var title = (btn.getAttribute("title") || "").toLowerCase();
        btn.addEventListener("click", function (e) {
          e.preventDefault();
          if (title.indexOf("rotate") >= 0) window.AetherViewer.toggleAutoRotate();
          else if (title.indexOf("zoom") >= 0) e.shiftKey ? window.AetherViewer.zoomOut() : window.AetherViewer.zoomIn();
          else if (title.indexOf("reset") >= 0) window.AetherViewer.reset();
          else if (title.indexOf("snapshot") >= 0 || title.indexOf("take snapshot") >= 0) window.AetherViewer.snapshot();
        });
      });
    }
  }
})();
