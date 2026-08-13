"use strict";

function setV2View(path, push = false) {
  const target = path.startsWith("/control") ? "/control" : "/";
  const dashboardView = document.getElementById("dashboardView");
  const controlView = document.getElementById("controlView");
  if (!dashboardView || !controlView) return;

  const controlActive = target === "/control";
  dashboardView.hidden = controlActive;
  controlView.hidden = !controlActive;

  document.querySelectorAll(".v2-nav[data-route]").forEach((item) => {
    const active = item.dataset.route === target;
    item.classList.toggle("active", active);
    if (active) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  });

  if (push && window.location.pathname !== target) history.pushState({ v2Route: target }, "", target);
  window.scrollTo(0, 0);
}

function loadV2Script(src) {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[data-v2-loaded="${src}"]`)) { resolve(); return; }
    const script = document.createElement("script");
    script.src = src;
    script.dataset.v2Loaded = src;
    script.onload = resolve;
    script.onerror = () => reject(new Error(`Nie udało się załadować ${src}`));
    document.head.appendChild(script);
  });
}

async function hydrateControlView() {
  const host = document.getElementById("controlView");
  if (!host) return;
  try {
    const response = await fetch("/control.html", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const source = parsed.querySelector(".app-shell");
    if (!source) throw new Error("Brak źródła widoku STREFY");

    const legacyTopbar = source.querySelector(":scope > .topbar");
    if (legacyTopbar) {
      const status = legacyTopbar.querySelector(".topbar-status");
      if (status) status.remove();
      const eyebrow = legacyTopbar.querySelector(".eyebrow");
      if (eyebrow) eyebrow.textContent = "STREFY";
      legacyTopbar.className = "v2-page-heading";
    }

    host.innerHTML = source.outerHTML;
    await loadV2Script("/app.js");
    await loadV2Script("/tacho.js");
  } catch (error) {
    host.innerHTML = `<section class="v2-page-heading"><h1>STREFY</h1><p>Nie udało się załadować widoku sterowania: ${String(error.message || error)}</p></section>`;
  }
}

function wireV2Navigation() {
  const nav = [...document.querySelectorAll(".v2-nav")];
  const zones = nav.find((el) => el.textContent.trim() === "STREFY");
  const service = nav.find((el) => el.textContent.trim() === "SERWIS");
  const dashboard = nav.find((el) => el.textContent.trim() === "PULPIT");
  if (zones) { zones.classList.remove("disabled"); zones.removeAttribute("aria-disabled"); zones.href = "/control"; zones.dataset.route = "/control"; }
  if (dashboard) dashboard.dataset.route = "/";
  if (service) { service.classList.add("disabled"); service.setAttribute("aria-disabled", "true"); service.href = "#"; }

  document.addEventListener("click", (event) => {
    const link = event.target.closest('a[href="/"],a[href="/control"]');
    if (!link) return;
    event.preventDefault();
    setV2View(link.getAttribute("href") || "/", true);
  });
  window.addEventListener("popstate", () => setV2View(window.location.pathname));
  setV2View(window.location.pathname);
}

wireV2Navigation();
hydrateControlView();

const card=document.querySelector('.v2-unit-card');if(card){card.className='v2-weather-card';card.innerHTML='<span class="v2-weather-kicker">POGODA</span><h2>Na zewnątrz</h2><div class="v2-weather-main"><span id="weatherIcon" class="v2-weather-icon">◌</span><strong id="weatherTemp">—</strong></div><p id="weatherCondition" class="v2-weather-condition">Brak danych pogodowych</p><p id="weatherLocation" class="v2-weather-location">Warsztat</p><div class="v2-weather-metrics"><div><span>Opady</span><strong id="weatherRain">—</strong></div><div><span>Wiatr</span><strong id="weatherWind">—</strong></div></div><div class="v2-weather-source">Źródło: MET Norway</div>'}
const $=id=>document.getElementById(id),u={clock:$('clock'),date:$('date'),systemDot:$('systemDot'),systemText:$('systemText'),z1n:$('zone1Name'),z2n:$('zone2Name'),z1d:$('zone1Dot'),z2d:$('zone2Dot'),z1s:$('zone1AirStatus'),z2s:$('zone2AirStatus'),z1v:$('zone1Voc'),z2v:$('zone2Voc'),z1p:$('zone1Pm25'),z2p:$('zone2Pm25'),vp:$('zone1VentilationPercent'),sp:$('zone1SupplyPercent'),ep:$('zone1ExtractPercent'),mode:$('zone1Mode'),b1:$('zone1Bar'),am:$('zone2AeroMode'),ae:$('zone2AeroExtra'),as:$('zone2AeroSupply'),ax:$('zone2AeroExtract'),b2:$('zone2Bar'),wi:$('weatherIcon'),wt:$('weatherTemp'),wc:$('weatherCondition'),wl:$('weatherLocation'),wr:$('weatherRain'),ww:$('weatherWind')};
let cfg={zone1:{name:'Mycie / Wygrzewanie',sensor_address:1},zone2:{name:'Lutowanie',sensor_address:2}};
const num=(v,d=0)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('pl-PL',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
function pct(v){const n=Number(v||0);return Math.max(0,Math.min(100,Math.round(n*10)))}
const node=(b,a)=>b&&Array.isArray(b.nodes)?b.nodes.find(n=>n.slave_address===a)||null:null,ok=n=>!!(n&&n.online===true&&n.usable===true&&n.measurement_valid===true&&n.measurement_stale!==true),aok=a=>!!(a&&a.ready===true&&a.worker_alive===true&&a.online===true&&a.usable===true),tok=t=>!!(t&&t.ready===true&&t.worker_alive===true&&!t.last_error);
function clock(){const d=new Date();if(u.clock)u.clock.textContent=new Intl.DateTimeFormat('pl-PL',{hour:'2-digit',minute:'2-digit'}).format(d);if(u.date)u.date.textContent=new Intl.DateTimeFormat('pl-PL',{day:'2-digit',month:'2-digit',year:'numeric'}).format(d)}
function air(st,k,n,s,v,p,d){const r=n&&n.reading?n.reading:{},z=st.air_quality&&st.air_quality[k],q=z&&typeof z.status==='string'?z.status.trim().toUpperCase():'';s.textContent=ok(n)?(q||'MONITORING'):(n&&n.online?'BRAK DANYCH':'OFFLINE');v.textContent=num(r.voc_index);p.textContent=num(r.pm2_5_ug_m3);d.classList.toggle('bad',!ok(n))}
function weather(w){if(!w||w.available!==true){u.wi.textContent='◌';u.wt.textContent='—';u.wc.textContent='Brak danych pogodowych';u.wl.textContent='Warsztat';u.wr.textContent='—';u.ww.textContent='—';return}u.wi.textContent=w.icon||'◌';u.wt.textContent=`${num(w.temperature_celsius,1)}°C`;u.wc.textContent=w.condition||'—';u.wl.textContent=w.location||'Warsztat';u.wr.textContent=typeof w.precipitation_amount_mm==='number'?`${num(w.precipitation_amount_mm,1)} mm`:'—';u.ww.textContent=typeof w.wind_speed_kmh==='number'?`${num(w.wind_speed_kmh)} km/h`:'—'}
function render(st){const z1=node(st.sensor_bus,cfg.zone1.sensor_address),z2=node(st.sensor_bus,cfg.zone2.sensor_address),s=pct(st.setpoints&&st.setpoints.supply_voltage),e=pct(st.setpoints&&st.setpoints.extract_voltage),avg=Math.round((s+e)/2),a=st.aero_bus,t=a&&a.telemetry?a.telemetry:{},f1=typeof t.fan_1_percent==='number'?t.fan_1_percent:null,f2=typeof t.fan_2_percent==='number'?t.fan_2_percent:null,ah=aok(a),alarms=Array.isArray(st.active_alarms)?st.active_alarms:[];u.z1n.textContent=cfg.zone1.name;u.z2n.textContent=cfg.zone2.name;air(st,'zone1',z1,u.z1s,u.z1v,u.z1p,u.z1d);air(st,'zone2',z2,u.z2s,u.z2v,u.z2p,u.z2d);u.sp.textContent=`${s}%`;u.ep.textContent=`${e}%`;u.vp.textContent=`${avg}%`;u.mode.textContent=st.mode==='MANUAL'?'Ręcznie · MANUAL':(st.mode||'—');u.b1.style.width=`${avg}%`;u.am.textContent=ah?'ONLINE':'NIEDOSTĘPNY';u.ae.textContent=ah?'AERO ONLINE':'Brak komunikacji AERO';u.as.textContent=f1===null?'—':`${f1}%`;u.ax.textContent=f2===null?'—':`${f2}%`;u.b2.style.width=`${Math.round(((f1||0)+(f2||0))/2)}%`;const core=st.hardware_ready===true&&st.output_state_known===true&&alarms.length===0,sens=ok(z1)&&ok(z2),tach=tok(st.tacho),allOk=core&&sens&&tach&&ah;if(u.systemDot)u.systemDot.className=`v2-dot ${allOk?'good':'warn'}`;if(u.systemText)u.systemText.textContent=allOk?'System OK':'System UWAGA'}
async function req(p){const r=await fetch(p,{cache:'no-store'}),j=await r.json();if(!r.ok||j.ok!==true)throw Error();return j}async function state(){try{render((await req('/api/v1/state')).state)}catch(e){if(u.systemDot)u.systemDot.className='v2-dot bad';if(u.systemText)u.systemText.textContent='Brak danych z CM5'}}async function meteo(){try{weather((await req('/api/v1/weather')).weather)}catch(e){weather(null)}}async function config(){try{const r=await req('/api/v1/config');if(r.config)cfg=r.config}catch(e){}}
clock();setInterval(clock,1000);config().finally(state);meteo();setInterval(state,2000);setInterval(meteo,900000);
