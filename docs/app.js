// Mars Scout map. Reads the JSON files in data/, all written ahead of time by scout/ and model/.
const STATUS_COLOR = { clear: "#3ecf6e", caution: "#f2b632", blocked: "#e5484d" };
const STATUS_WORD = { clear: "Go", caution: "Go with care", blocked: "No go" };
const LEG_COLOR = { ok: "#3ecf6e", caution: "#f2b632", avoid: "#e5484d" };
const LEG_TEXT = { ok: "Gentle", caution: "Caution, steep in places", avoid: "Avoid the straight line" };
const LEG_SHORT = { ok: "Gentle", caution: "Steep in places", avoid: "Go around" };
const $ = (id) => document.getElementById(id);
const pct = (v) => Math.round(v * 100) + "%";
const params = new URLSearchParams(location.search);

// Mars Trek tiles are plain lat/lon (equirectangular): 2x1 tiles at zoom 0.
const map = L.map("map", { crs: L.CRS.EPSG4326, minZoom: 8, maxZoom: 21, zoomSnap: 0.25 });
// wider, coarser context under the HiRISE mosaic, for zooming out to the whole crater
L.tileLayer(
  "https://trek.nasa.gov/tiles/Mars/EQ/Gale_CTX_BlockAdj_dd/1.0.0/default/default028mm/{z}/{y}/{x}.png",
  { maxNativeZoom: 12, maxZoom: 21, attribution: "MRO CTX: NASA/JPL-Caltech/MSSS" }
).addTo(map);
L.tileLayer(
  "https://trek.nasa.gov/tiles/Mars/EQ/curiosity_hirise_mosaic/1.0.0/default/default028mm/{z}/{y}/{x}.png",
  { maxNativeZoom: 16, maxZoom: 21, attribution: "NASA/JPL-Caltech/University of Arizona · Mars Trek" }
).addTo(map);

// Leaflet's built-in scale bar assumes Earth's radius, so draw one for Mars instead.
const MARS_RADIUS_M = 3396190;
const scaleBar = L.control({ position: "bottomleft" });
scaleBar.onAdd = () => L.DomUtil.create("div", "mars-scale");
scaleBar.addTo(map);
function updateScale() {
  const y = map.getSize().y - 20;
  const span = Math.abs(map.containerPointToLatLng([100, y]).lng - map.containerPointToLatLng([0, y]).lng);
  const mPerPx = (span * Math.PI / 180) * MARS_RADIUS_M * Math.cos(map.getCenter().lat * Math.PI / 180) / 100;
  const nice = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000].filter((m) => m / mPerPx <= 140).pop() || 1;
  const el = scaleBar.getContainer();
  el.style.width = nice / mPerPx + "px";
  el.textContent = nice >= 1000 ? nice / 1000 + " km" : nice + " m";
}
map.on("zoomend moveend", updateScale);

const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
  const el = L.DomUtil.create("div", "map-legend");
  el.innerHTML =
    `<div><i class="dot clear"></i>Clear <i class="dot caution"></i>Caution <i class="dot blocked"></i>Blocked</div>` +
    `<div><i class="star"></i>Science stop <i class="walker-key"></i>Astronaut</div>` +
    `<div><i class="line scouted"></i>Scout-checked route</div>` +
    `<div><i class="line orbital"></i>Plan from orbit</div>` +
    `<div><i class="swatch" style="background:#f2b632"></i>Steep <i class="swatch" style="background:#e5484d"></i>Very steep or drop-off</div>`;
  return el;
};
legend.addTo(map);

let ctx = null;          // loaded data
let index = 0;           // the selected stop
let currentView = null;  // the direction being shown at that stop
let view = "paths";      // which image is shown
let routeBounds = null;
let walker = null, walked = null;
const markers = [];

Promise.all(["pins", "route", "terrain", "model"].map((n) => fetch(`data/${n}.json`).then((r) => r.json())))
  .then(([scout, route, terrain, model]) => {
    const pins = scout.pins;
    ctx = {
      scout, route, terrain, pins,
      stops: Object.fromEntries(route.stops.map((s) => [s.id, s])),
      orbital: Object.fromEntries(terrain.stops.map((s) => [s.id, s])),
      legs: Object.fromEntries(terrain.segments.map((s) => [s.from, s])),
    };

    // header
    $("sol-range").textContent = `sols ${pins[0].sol}–${pins[pins.length - 1].sol}`;
    $("stat-distance").textContent = (route.total_distance_m / 1000).toFixed(2) + " km";
    $("stat-time").textContent = Math.round(route.total_walk_min) + " min";
    $("stat-pins").textContent = pins.length;
    $("stat-photos").textContent = route.photos_analysed;
    $("stat-acc").textContent = (model.test_min1.pixel_accuracy * 100).toFixed(1) + "%";
    $("intro-km").textContent = (route.total_distance_m / 1000).toFixed(1) + " km";

    // map layers, bottom to top
    const slopeLayer = L.imageOverlay("data/slope.png", terrain.bounds, { opacity: 0.85, interactive: false }).addTo(map);
    L.control.layers(null, { "Steep ground and drop-offs (from orbit)": slopeLayer }, { collapsed: false, position: "bottomright" }).addTo(map);
    L.polyline(route.traverse, { color: "#fff", weight: 1.5, opacity: 0.5, interactive: false }).addTo(map);
    const plan = L.polyline(route.orbital_plan, { color: "#9ecbff", weight: 2, dashArray: "6 6" });
    plan.addTo(map).bindTooltip("Plan from orbit: straight lines between science stops");
    const scouted = L.polyline(route.scouted_route, { color: "#3ecf6e", weight: 4, opacity: 0.55 }).addTo(map);
    walked = L.polyline([], { color: "#fff", weight: 2.5, opacity: 0.95, interactive: false }).addTo(map);
    routeBounds = scouted.getBounds();
    const bend = L.circleMarker(route.reroute.detour_point, { radius: 4, color: "#fff", fillColor: "#f2b632", fillOpacity: 1, weight: 1 })
      .addTo(map)
      .bindTooltip(`Re-route: straight ahead was ${pct(route.reroute.straight_hazard)} sand and rock. Bend is illustrative.`);

    pins.forEach((pin, i) => {
      const stop = ctx.stops[pin.id];
      const m = L.circleMarker([pin.lat, pin.lon], {
        radius: stop.science ? 9 : 6, color: "#fff", weight: 2,
        fillColor: STATUS_COLOR[pin.status], fillOpacity: 1,
      }).addTo(map);
      m.bindTooltip(`${stop.science ? stop.science.name : "Scout stop " + (i + 1)} · ${STATUS_WORD[pin.status].toLowerCase()}`);
      if (stop.science) {
        L.marker([pin.lat, pin.lon], {
          interactive: false,
          icon: L.divIcon({ className: "stop-label" + (stop.science.name.startsWith("Stop C") ? " left" : ""), html: "★ " + stop.science.name.split(":")[0], iconSize: [70, 16],
                            // two science stops are close together: put one label on the left of its marker
                            iconAnchor: stop.science.name.startsWith("Stop C") ? [82, 8] : [-12, 8] }),
        }).addTo(map);
      }
      m.on("click", () => { stopPlay(); show(i, "ahead"); });
      markers.push(m);
    });
    walker = L.marker([pins[0].lat, pins[0].lon], {
      interactive: false, zIndexOffset: 1000,
      icon: L.divIcon({ className: "walker", html: "<i></i>", iconSize: [26, 26], iconAnchor: [13, 13] }),
    }).addTo(map);

    buildTimeline();
    drawTerrain(terrain);
    drawEnvironment(route);
    drawModel(model);
    $("traverse-note").textContent =
      `The thin white line on the map is Curiosity's whole traverse since landing: ${route.traverse_km} km over ${route.traverse_last_sol} sols.`;
    $("assumptions").innerHTML = route.assumptions.map((a) => `<li>${a}</li>`).join("");

    const reroute = pins.findIndex((p) => p.id === route.reroute.pin_id);
    const name = pins[reroute].views.find((v) => v.direction === "ahead").name;
    ["photo", "paths", "edge"].forEach((v, k) => { $("intro-img" + (k + 1)).src = `data/pins/${name}_${v}.jpg`; });

    map.fitBounds(routeBounds.pad(0.12), { animate: false });
    show(reroute, "ahead", { pan: false });  // open on the re-route stop: it is the point of the demo
    buildTour(reroute);

    // clean map-only views, used to make the slide images: ?shot=overview|zoom|orbit&stop=N&z=18
    if (params.has("shot")) {
      const mode = params.get("shot"), at = pins[params.has("stop") ? +params.get("stop") : reroute];
      document.body.classList.add("shot");
      if (mode === "orbit") document.body.classList.add("bare");
      map.invalidateSize({ animate: false });
      if (mode === "overview") map.fitBounds(routeBounds.pad(+params.get("pad") || 0.1), { animate: false });
      if (params.has("tidy")) {  // small dots and a bold route line, for a clean overview picture
        plan.remove(); bend.remove(); walker.remove();
        scouted.setStyle({ weight: 3, opacity: 1, color: "#ffffff" });
        markers.forEach((m, k) => { m.setRadius(ctx.stops[pins[k].id].science ? 5 : 3); m.setStyle({ weight: 1, color: "#14110f" }); });
        document.body.classList.add("tidy");
        return;
      }
      else map.setView([at.lat, at.lon], +params.get("z") || 18.5, { animate: false });
      show(pins.indexOf(at), "ahead", { pan: false });
      return;
    }
    if (params.has("tab")) setTab(params.get("tab"));
    if (params.has("step")) tourGo(+params.get("step"), { auto: false, animate: false });
    else if (params.has("tour")) tourGo(0);
    else if (params.has("play")) { show(0, "ahead"); play(); }
    else if (params.get("intro") !== "0") $("intro").hidden = false;
  })
  .catch((err) => {
    $("pin-title").textContent = "Could not load the scout data";
    $("pin-verdict").textContent = String(err);
  });

// ---------- one stop ----------

function show(i, direction, opts = {}) {
  const { scout, route, stops, pins, orbital, legs } = ctx;
  const stopPin = pins[i], stop = stops[stopPin.id];
  // "pin" below is the view being shown: one direction at this stop
  const pin = stopPin.views.find((v) => v.direction === direction) || stopPin.views[0];
  markers[index].setStyle({ weight: 2, color: "#fff" });
  index = i;
  currentView = pin;
  markers[i].setStyle({ weight: 4, color: "#e8793a" });

  // astronaut marker, walked part of the route, timeline
  const here = [stopPin.lat, stopPin.lon];
  walker.setLatLng(here);
  walked.setLatLngs(pins.slice(0, i + 1).map((p) => [p.lat, p.lon]));
  if (opts.pan !== false && !map.getBounds().pad(-0.15).contains(here)) map.panTo(here, { animate: opts.animate !== false });
  document.querySelectorAll("#tl-scout button").forEach((b, k) => {
    b.classList.toggle("on", k === i);
    b.classList.toggle("done", k < i);
  });
  $("tl-label").innerHTML =
    `<b>Stop ${i + 1} of ${pins.length}</b> · sol ${stopPin.sol} · ${Math.round(stop.distance_from_start_m)} m from the start · ` +
    `${stop.walk_back_min} min walked` + (stop.science ? ` · <span class="sci">★ ${stop.science.name}</span>` : "");
  if (opts.tab !== false) setTab("scout");

  const dirs = $("dirs");
  dirs.innerHTML = "";
  for (const v of stopPin.views) {
    const b = document.createElement("button");
    b.className = v === pin ? "on" : "";
    const dot = document.createElement("i");
    dot.className = "dot " + v.status;
    b.append(dot, v.direction[0].toUpperCase() + v.direction.slice(1));
    b.title = `${v.direction}: ${v.status}`;
    b.addEventListener("click", () => { stopPlay(); show(i, v.direction); });
    dirs.appendChild(b);
  }
  $("dir-note").textContent = stopPin.views.length > 1
    ? `Looking ${pin.direction}${pin.direction === "ahead" ? " (toward the next stop)" : ""}, compass bearing ${Math.round(pin.photo_azimuth_deg)}°. ` +
      `Lowest-hazard direction at this stop: ${stopPin.safest_direction}.`
    : "Only one usable photo at this stop.";

  $("pin-title").textContent = `Stop ${i + 1} · sol ${stopPin.sol}`;
  const badge = $("pin-status");
  badge.textContent = pin.status;
  badge.style.background = STATUS_COLOR[pin.status];

  const sci = $("pin-science");
  sci.hidden = !stop.science;
  if (stop.science) sci.innerHTML = `<strong>${stop.science.name}.</strong> ${stop.science.why}`;

  const side = pin.chosen_path < pin.straight_path ? "left" : "right";
  $("verdict").style.borderColor = STATUS_COLOR[pin.status];
  $("verdict-word").textContent = STATUS_WORD[pin.status];
  $("verdict-word").style.color = STATUS_COLOR[pin.status];
  $("pin-verdict").textContent =
    pin.status === "clear"
      ? `Straight on is ${pct(pin.straight_hazard)} sand and rock, and both checks agree.`
      : pin.status === "caution"
        ? (pin.chosen_path === pin.straight_path
            ? `Straight on is ${pct(pin.straight_hazard)} sand and rock, the best path available.`
            : `Straight on is ${pct(pin.straight_hazard)} sand and rock. The scout picked a path to the ${side} at ${pct(pin.chosen_hazard)}.`) +
          (pin.edge_check.agreement === "disagree" ? " The two checks disagree here." : "")
        : `Every path crosses at least ${pct(pin.chosen_hazard)} sand and rock. Do not continue this way.`;

  setImage();

  const e = pin.edge_check;
  $("chk-model").textContent = pct(pin.ground.sand + pin.ground["big rock"]);
  $("chk-edge").textContent = e.rocks_found;
  const agree = $("chk-agree");
  agree.className = "agree " + e.agreement;
  agree.textContent = e.agreement === "agree"
    ? "✓ The two checks agree on the chosen path."
    : "⚠ The two checks disagree, so this view cannot be marked clear:";
  $("edge-notes").innerHTML = "";
  for (const note of e.notes) {
    const li = document.createElement("li");
    li.textContent = note;
    $("edge-notes").appendChild(li);
  }

  $("ground-bar").innerHTML = Object.entries(pin.ground)
    .map(([name, v]) => `<span title="${name} ${pct(v)}" style="width:${v * 100}%;background:rgb(${scout.classes[name]})"></span>`).join("");
  $("ground-text").textContent = Object.entries(pin.ground).map(([n, v]) => `${n} ${pct(v)}`).join(" · ");

  const w = stop.weather, leg = legs[stopPin.id];
  const dose = route.radiation.dose_msv_per_day * 1000 * stop.walk_back_min / 1440;  // microsieverts
  const tiles = [
    [`${stop.walk_back_min} min`, `to walk back to the start (${Math.round(stop.distance_from_start_m)} m, est.)`],
    [`${dose.toFixed(1)} µSv`, "radiation dose so far (long-term average rate)"],
    [w ? `${w.air_temp_min_c} to ${w.air_temp_max_c} °C` : "no reading", `air temperature, sol ${stopPin.sol}`],
    [leg ? LEG_SHORT[leg.level] : "End of route", leg ? `next leg from orbit: up to ${leg.max_slope_deg}°${leg.crosses_drop_off ? ", crosses a drop-off" : ""}` : "no further leg"],
  ];
  $("safety-tiles").innerHTML = tiles.map(([v, l]) => `<div><span>${v}</span><label>${l}</label></div>`).join("");
  if (leg) $("safety-tiles").lastElementChild.firstElementChild.style.color = LEG_COLOR[leg.level];

  const rows = [
    ["Slope here", `${orbital[stopPin.id].dem_slope_deg}° from orbit, ${stopPin.rover_tilt_deg}° rover tilt on the ground`],
    ["Next leg", leg
      ? `${LEG_TEXT[leg.level]}: up to ${leg.max_slope_deg}° over ${Math.round(leg.length_m)} m` +
        (leg.crosses_drop_off ? ", crosses a drop-off" : "") + " (straight line, from orbit)"
      : "End of route"],
    ["Elevation", `${Math.round(stopPin.elevation_m)} m`],
  ];
  if (w) {
    rows.push(
      ["Ground temperature", `${w.ground_temp_min_c} to ${w.ground_temp_max_c} °C`],
      ["Pressure", `${w.pressure_pa} Pa`],
      ["Sky / UV", `${w.sky} / ${w.uv}`],
      ["Daylight", `${w.sunrise} to ${w.sunset} local`],
      ["Weather date", `sol ${stopPin.sol} (${w.earth_date}), Curiosity REMS`],
    );
  }
  $("safety").innerHTML = rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("");

  $("pin-source").href = pin.photo_url;
  $("pin-conf").textContent = `model confidence ${pct(pin.model_confidence)}`;
}

function setImage() {
  const img = $("pin-image");
  img.src = `data/pins/${currentView.name}_${view}.jpg`;
  img.alt = { paths: "Photo with terrain colours and candidate paths; the chosen path is green",
              edge: "Photo with rock shadows outlined in magenta and smooth ground tinted cyan",
              photo: "Curiosity navigation camera photo" }[view];
  document.querySelectorAll("#views button").forEach((x) => x.classList.toggle("on", x.dataset.view === view));
  const sw = (c, t) => `<li><i class="swatch" style="background:${c}"></i>${t}</li>`;
  $("image-legend").innerHTML = view === "paths"
    ? Object.entries(ctx.scout.classes).map(([n, c]) => sw(`rgb(${c})`, n)).join("") +
      `<li><i class="line scouted"></i>chosen path</li><li><i class="line rejected"></i>rejected paths</li>` + sw("#ff3cc8", "edge-check rock")
    : view === "edge" ? sw("#ff3cc8", "rock shadows") + sw("#35d0e0", "smooth ground (possible sand)")
    : `<li>Curiosity left navigation camera, contrast stretched</li>`;
}

function setView(v) { view = v; setImage(); }
document.querySelectorAll("#views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

function setTab(name) {
  document.querySelectorAll(".ptabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => { t.hidden = t.id !== "tab-" + name; });
}
document.querySelectorAll(".ptabs button").forEach((b) => b.addEventListener("click", () => setTab(b.dataset.tab)));

// ---------- timeline and playing the walk ----------

function buildTimeline() {
  const { pins, stops, legs } = ctx;
  pins.forEach((pin, i) => {
    const b = document.createElement("button");
    b.style.background = STATUS_COLOR[pin.status];
    const sci = stops[pin.id].science;
    if (sci) { b.classList.add("sci"); b.dataset.star = "★ " + sci.name.split(":")[0].replace("Stop ", ""); }
    b.title = `Stop ${i + 1}, sol ${pin.sol}: ${STATUS_WORD[pin.status].toLowerCase()}` + (sci ? ` (${sci.name})` : "");
    b.setAttribute("aria-label", b.title);
    b.addEventListener("click", () => { stopPlay(); show(i, "ahead"); });
    $("tl-scout").appendChild(b);

    const leg = legs[pin.id], cell = document.createElement("i");
    if (leg) {
      cell.style.background = LEG_COLOR[leg.level];
      cell.title = `Leg ${i + 1} to ${i + 2} from orbit: ${LEG_TEXT[leg.level].toLowerCase()}, up to ${leg.max_slope_deg}°`;
    }
    $("tl-orbit").appendChild(cell);
  });
}

let playTimer = null;
function stopPlay() {
  clearInterval(playTimer);
  playTimer = null;
  $("tl-play").textContent = "▶";
  document.body.classList.remove("playing");
}
function play() {
  if (playTimer) return stopPlay();
  tourEnd();
  const n = ctx.pins.length;
  if (index >= n - 1) show(0, "ahead");
  $("tl-play").textContent = "❚❚";
  document.body.classList.add("playing");
  playTimer = setInterval(() => {
    if (index >= n - 1) return stopPlay();
    show(index + 1, "ahead");
  }, 1100);
}
const step = (d) => { stopPlay(); show(Math.min(Math.max(index + d, 0), ctx.pins.length - 1), "ahead"); };
$("tl-play").addEventListener("click", play);
$("tl-prev").addEventListener("click", () => step(-1));
$("tl-next").addEventListener("click", () => step(1));
document.addEventListener("keydown", (ev) => {
  if (!ctx) return;
  if (ev.key === "Escape") { $("intro").hidden = true; tourEnd(); }
  if (!$("intro").hidden || tourAt >= 0) return;
  if (ev.key === "ArrowRight") step(1);
  if (ev.key === "ArrowLeft") step(-1);
});

// ---------- guided tour ----------

let tour = [], tourAt = -1, tourTimer = null;
const TOUR_MS = 4200;

function buildTour(reroute) {
  const { pins, route, terrain, stops } = ctx;
  const r = route.reroute;
  const count = (s) => pins.filter((p) => p.status === s).length;
  const steep = pins.findIndex((p) => ctx.legs[p.id] && ctx.legs[p.id].level === "avoid");
  const last = pins.map((p) => !!stops[p.id].science).lastIndexOf(true);
  const km = (route.total_distance_m / 1000).toFixed(1);
  const overview = (o) => map.fitBounds(routeBounds.pad(0.12), o);
  // zoom to a stop and the leg after it
  const near = (i, zoomOut, o) => {
    const next = pins[Math.min(i + 1, pins.length - 1)];
    map.fitBounds(L.latLngBounds([pins[i].lat, pins[i].lon], [next.lat, next.lon]).pad(zoomOut), { ...o, maxZoom: 19.5 });
  };
  tour = [
    { text: `An astronaut plans a ${km} km Marswalk across the boxwork ridges of Mount Sharp. A robotic scout goes first.`,
      run: (o) => { overview(o); show(0, "ahead", { pan: false }); } },
    { text: "At every stop the scout photographs the ground. These are real photos from NASA's Curiosity rover, replayed.",
      run: (o) => { near(reroute, 6, o); show(reroute, "ahead", { pan: false }); setView("photo"); scrollPanel("views"); } },
    { text: `An AI model trained on NASA's AI4Mars data colours the terrain. Straight ahead is ${pct(r.straight_hazard)} sand and rock, so the scout picks the green path at ${pct(r.chosen_hazard)}.`,
      run: (o) => { near(reroute, 6, o); show(reroute, "ahead", { pan: false }); setView("paths"); scrollPanel("views"); } },
    { text: "A second check with no AI outlines rock shadows. When the two disagree, a stop is never marked clear.",
      run: (o) => { near(reroute, 6, o); show(reroute, "ahead", { pan: false }); setView("edge"); scrollPanel("views"); } },
    { text: "From orbit, NASA's 1 m elevation model marks steep ground and drop-offs in red. Here the straight line ahead is rated: go around.",
      run: (o) => { near(steep, 2.5, o); show(steep, "ahead", { pan: false }); setView("paths"); scrollPanel("safety-head"); } },
    { text: "Every stop reports the time to walk back, the weather Curiosity measured there, and the radiation dose so far.",
      run: (o) => { near(last, 6, o); show(last, "ahead", { pan: false }); scrollPanel("safety-head"); } },
    { text: `${pins.length} stops and ${route.photos_analysed} NASA photos checked: ${count("clear")} clear, ${count("caution")} go with care, ${count("blocked")} blocked. Now explore the map.`,
      run: (o) => { overview(o); show(pins.length - 1, "ahead", { pan: false }); scrollPanel("pin"); } },
  ];
}

function scrollPanel(id) {
  const el = $(id), panel = document.querySelector("aside");
  if (getComputedStyle(panel).overflowY !== "visible") panel.scrollTop = el.offsetTop - 50;
}

function tourGo(n, opts = {}) {
  if (n < 0) n = 0;
  if (n >= tour.length) return tourEnd();
  stopPlay();
  clearTimeout(tourTimer);
  $("intro").hidden = true;
  tourAt = n;
  document.querySelector("aside").scrollTop = 0;
  tour[n].run({ animate: opts.animate !== false, duration: 0.8 });
  $("caption").hidden = false;
  $("caption-text").textContent = tour[n].text;
  $("caption-count").textContent = `${n + 1} / ${tour.length}`;
  $("tour-next").textContent = n === tour.length - 1 ? "Finish" : "Next";
  const bar = $("caption-progress").firstElementChild;
  bar.style.animation = "none";
  if (opts.auto !== false) {
    void bar.offsetWidth;  // restart the progress animation
    bar.style.animation = `fill ${TOUR_MS}ms linear forwards`;
    tourTimer = setTimeout(() => (n === tour.length - 1 ? tourEnd() : tourGo(n + 1)), TOUR_MS);
  }
}
function tourEnd() {
  clearTimeout(tourTimer);
  tourAt = -1;
  $("caption").hidden = true;
}
$("btn-tour").addEventListener("click", () => tourGo(0));
$("tour-next").addEventListener("click", () => tourGo(tourAt + 1));
$("tour-back").addEventListener("click", () => tourGo(tourAt - 1));
$("tour-end").addEventListener("click", tourEnd);
$("intro-tour").addEventListener("click", () => tourGo(0));
$("intro-explore").addEventListener("click", () => { $("intro").hidden = true; });
$("intro").addEventListener("click", (ev) => { if (ev.target.id === "intro") $("intro").hidden = true; });
$("btn-intro").addEventListener("click", () => { $("intro").hidden = false; });

// ---------- environment, terrain and model panels ----------

function drawEnvironment(route) {
  const env = route.environment, rad = route.radiation, days = env.daily;
  $("env-air").textContent = `${env.air_min_c} to ${env.air_max_c} °C`;
  $("env-ground").textContent = `${env.ground_min_c} to ${env.ground_max_c} °C`;
  $("env-pressure").textContent = `${env.pressure_min_pa}–${env.pressure_max_pa} Pa`;
  $("env-daylight").textContent = `${env.daylight_hours_min}–${env.daylight_hours_max} h`;
  const list = (counts) => Object.entries(counts).map(([k, n]) => `${k.toLowerCase()} on ${n}`).join(", ");
  $("env-sky").textContent =
    `Curiosity REMS readings for ${env.sols_with_readings} sols of the drive. Pressure is about ` +
    `${(env.pressure_max_pa / env.earth_sea_level_pa * 100).toFixed(1)}% of Earth's at sea level. ` +
    `Sky: ${list(env.sky_sol_counts)} sols. UV: ${list(env.uv_sol_counts)} sols.`;

  lineChart($("chart-temp"), {
    label: "Daily high and low air temperature for each sol of the drive",
    x: days.map((d) => d.sol),
    series: [
      { name: "High", color: "#d95926", values: days.map((d) => d.air_max_c) },
      { name: "Low", color: "#3987e5", values: days.map((d) => d.air_min_c) },
    ],
    xTitle: "Sol", yUnit: "°",
    tooltip: (i) => ({
      title: `Sol ${days[i].sol} (${days[i].earth_date})`,
      rows: [["Air", `${days[i].air_min_c} to ${days[i].air_max_c} °C`],
             ["Ground", `${days[i].ground_min_c} to ${days[i].ground_max_c} °C`],
             ["Pressure", `${days[i].pressure_pa} Pa`]],
    }),
  });
  $("table-temp").innerHTML =
    "<tr><th>Sol</th><th>Earth date</th><th>Air low</th><th>Air high</th><th>Ground low</th><th>Ground high</th></tr>" +
    days.map((d) => `<tr><td>${d.sol}</td><td>${d.earth_date}</td><td>${d.air_min_c}</td><td>${d.air_max_c}</td><td>${d.ground_min_c}</td><td>${d.ground_max_c}</td></tr>`).join("");

  const prof = route.elevation_profile;
  lineChart($("chart-elev"), {
    label: "Elevation at each scout stop along the route",
    x: prof.map((p) => p.distance_m),
    series: [{ name: "Elevation", color: "#3987e5", values: prof.map((p) => p.elevation_m) }],
    xTitle: "Distance from start (m)", yUnit: " m", markers: true, leftMargin: 58,
    tooltip: (i) => ({
      title: `Stop ${i + 1} · sol ${prof[i].sol}`,
      rows: [["Elevation", `${prof[i].elevation_m} m`], ["Distance", `${prof[i].distance_m} m`], ["Rover tilt", `${prof[i].tilt_deg}°`]],
    }),
  });
  const tilts = prof.map((p) => p.tilt_deg);
  $("elev-text").textContent =
    `The route varies by ${route.climb_m} m in elevation. Rover tilt at the stops ranged from ` +
    `${Math.min(...tilts)}° to ${Math.max(...tilts)}°, a rough indicator of ground slope.`;

  $("rad-day").textContent = `${rad.dose_msv_per_day} mSv`;
  $("rad-eva").textContent = `${rad.dose_msv_8h_eva} mSv`;
  $("rad-walk").textContent = `${rad.dose_msv_this_walk} mSv`;
  $("rad-earth").textContent = `${rad.times_earth_background}× lower`;
  $("rad-text").textContent = `${rad.source}. ${rad.note} ${rad.earth_source}. ${rad.storm_note}`;
}

function drawTerrain(terrain) {
  const t = terrain.thresholds, a = terrain.area, v = terrain.validation;
  const count = (level) => terrain.segments.filter((s) => s.level === level).length;
  $("terr-caution").textContent = pct(a.share_caution);
  $("terr-avoid").textContent = pct(a.share_avoid);
  $("terr-legs").textContent = `${count("ok")} / ${count("caution")} / ${count("avoid")}`;
  $("terr-max").textContent = a.max_slope_deg + "°";
  $("terr-text").textContent =
    `From NASA's 1 m HiRISE elevation model, over a ${a.width_m} × ${a.height_m} m area around the walk. ` +
    `Yellow on the map is slope of ${t.caution_deg}° or more; red is ${t.avoid_deg}° or more, or a drop of more than ` +
    `${t.drop_m} m within 3 m (scarps, ledges, pit edges). Legs are rated along the straight line between stops, ` +
    `so an "avoid" leg means go around, as Curiosity did. These limits are our assumptions, not NASA limits.`;
  $("terr-valid").textContent =
    `Check against the ground: at ${v.stops} rover stops, elevation from orbit differs from Curiosity's own by ` +
    `${v.elevation_mean_difference_m} m on average (spread ${v.elevation_difference_spread_m} m). Slope from orbit and rover tilt ` +
    `differ by ${v.mean_abs_difference_deg}° on average (correlation ${v.tilt_vs_orbital_slope_r}), so treat slope as a guide to ` +
    `steep areas, not an exact value at a point.`;
}

function drawModel(model) {
  const m = model.test_min1, strict = model.test_min3;
  $("m-acc").textContent = (m.pixel_accuracy * 100).toFixed(1) + "%";
  $("m-miou").textContent = m.mean_iou.toFixed(2);
  $("m-bars").innerHTML = Object.entries(m.iou).map(([name, v]) =>
    `<div><label>${name}</label><div class="track"><i style="width:${v * 100}%;background:rgb(${ctx.scout.classes[name]})"></i></div><b>${v.toFixed(2)}</b></div>`).join("");
  const total = Object.values(m.labeled_pixels).reduce((a, b) => a + b, 0);
  $("m-note").textContent =
    `Big rock is the weak class: it is only ${(m.labeled_pixels["big rock"] / total * 100).toFixed(1)}% of the labeled test pixels and the model ` +
    `misses most of it. That is why the edge check runs alongside the model. On the strictest test subset ` +
    `(${(strict.pixel_accuracy * 100).toFixed(1)}% accuracy) big rock reaches ${strict.iou["big rock"].toFixed(2)}.`;
}
