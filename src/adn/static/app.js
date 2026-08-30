/**
 * ADN Studio: Interactive frontend controller
 */

let currentEpisode = null;
let currentBgImage = new Image();
let currentBgPath = "";

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
  lucide.createIcons();
  loadEpisodesList();
  checkYouTubeAuth();
});

// Tab Switcher
function switchTab(tabId) {
  document.querySelectorAll(".tab-content").forEach(el => el.classList.add("hidden"));
  document.querySelectorAll(".tab-btn").forEach(el => {
    el.classList.remove("active", "text-amber-400", "bg-amber-500/10", "border", "border-amber-500/20");
    el.classList.add("text-zinc-400");
  });

  const targetTab = document.getElementById(`tab-${tabId}`);
  const targetBtn = document.getElementById(`tab-btn-${tabId}`);
  if (targetTab) targetTab.classList.remove("hidden");
  if (targetBtn) {
    targetBtn.classList.add("active", "text-amber-400", "bg-amber-500/10", "border", "border-amber-500/20");
    targetBtn.classList.remove("text-zinc-400");
  }

  if (tabId === "thumbnails") {
    updateLiveCanvas();
  }
}

// Toast Helper
function showToast(msg) {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toastMsg");
  toastMsg.textContent = msg;
  toast.classList.remove("translate-y-20", "opacity-0");
  setTimeout(() => {
    toast.classList.add("translate-y-20", "opacity-0");
  }, 3500);
}

// Check YouTube OAuth
async function checkYouTubeAuth() {
  const badge = document.getElementById("ytStatusBadge");
  const text = document.getElementById("ytStatusText");
  try {
    const res = await fetch("/api/youtube/status");
    const data = await res.json();
    if (data.authenticated && data.channel) {
      badge.className = "flex items-center space-x-2 bg-emerald-500/10 border border-emerald-500/30 px-3 py-1 rounded-full text-xs text-emerald-400";
      text.textContent = `Canal: ${data.channel.title}`;
    } else {
      badge.className = "flex items-center space-x-2 bg-zinc-800 border border-zinc-700 px-3 py-1 rounded-full text-xs text-zinc-400";
      text.textContent = "YouTube: Sin conectar";
    }
  } catch (err) {
    text.textContent = "YouTube: Desconectado";
  }
}

// Load Episodes
async function loadEpisodesList() {
  const select = document.getElementById("episodeSelect");
  try {
    const res = await fetch("/api/episodes");
    const episodes = await res.json();
    select.innerHTML = "";

    if (episodes.length === 0) {
      select.innerHTML = '<option value="">No hay episodios procesados</option>';
      return;
    }

    episodes.forEach(ep => {
      const opt = document.createElement("option");
      opt.value = ep.id;
      opt.dataset.path = ep.directory;
      opt.textContent = `🎙️ ${ep.name} (${ep.shorts_count} shorts)`;
      select.appendChild(opt);
    });

    select.addEventListener("change", (e) => {
      const opt = select.selectedOptions[0];
      loadEpisodeDetails(opt.value, opt.dataset.path);
    });

    // Auto load first episode
    loadEpisodeDetails(episodes[0].id, episodes[0].directory);
  } catch (err) {
    console.error("Failed to load episodes:", err);
    select.innerHTML = '<option value="">Error cargando episodios</option>';
  }
}

// Load Single Episode Data
async function loadEpisodeDetails(episodeId, dirPath) {
  try {
    const res = await fetch(`/api/episodes/${episodeId}?path=${encodeURIComponent(dirPath)}`);
    const data = await res.json();
    currentEpisode = data;

    // Header & Summary
    const activeTitle = data.analysis.title_options?.[0]?.title || data.id.replace(/_/g, " ").toUpperCase();
    document.getElementById("epHeaderTitle").textContent = activeTitle;
    document.getElementById("epHeaderSummary").textContent = data.analysis.episode_summary || "";
    document.getElementById("pubTitle").value = activeTitle;

    // Themes
    const themesEl = document.getElementById("epThemes");
    themesEl.innerHTML = "";
    (data.analysis.core_themes || []).forEach(theme => {
      const tag = document.createElement("span");
      tag.className = "text-xs bg-zinc-800 text-amber-400 border border-brand-border px-2.5 py-1 rounded-md font-medium";
      tag.textContent = `#${theme}`;
      themesEl.appendChild(tag);
    });

    // Video Player
    const player = document.getElementById("mainVideoPlayer");
    const pathLabel = document.getElementById("videoPathLabel");
    if (data.video_url) {
      player.src = data.video_url;
      pathLabel.textContent = `📁 ${data.video_path}`;
    } else {
      pathLabel.textContent = "⚠️ Video principal no encontrado en directorio";
    }

    // Chapters
    renderChapters(data.analysis.chapters || []);

    // Description Editor
    document.getElementById("descEditor").value = data.analysis.youtube_description || "";

    // 10 Titles
    renderTitles(data.analysis.title_options || []);

    // 16:9 Clips
    renderClips(data.clips || [], data.analysis.clips || []);

    // 9:16 Shorts
    renderShorts(data.shorts || [], data.analysis.shorts || []);

    // Thumbnails
    initThumbnailStudio(data);

    // Badges
    document.getElementById("clipsBadge").textContent = (data.clips || []).length;
    document.getElementById("shortsBadge").textContent = (data.shorts || []).length;

    lucide.createIcons();
  } catch (err) {
    console.error("Error loading episode:", err);
    showToast("Error al cargar datos del episodio");
  }
}

// Render Chapters
function renderChapters(chapters) {
  const list = document.getElementById("chaptersList");
  const count = document.getElementById("chaptersCount");
  list.innerHTML = "";
  count.textContent = `${chapters.length} capítulos`;

  chapters.forEach((ch, idx) => {
    const item = document.createElement("div");
    item.className = "flex items-center justify-between p-2.5 hover:bg-white/5 rounded-lg cursor-pointer transition group";
    item.onclick = () => {
      const player = document.getElementById("mainVideoPlayer");
      player.currentTime = ch.start_seconds;
      player.play();
    };

    item.innerHTML = `
      <div class="flex items-center space-x-3 truncate">
        <span class="font-mono text-xs px-2 py-0.5 rounded bg-zinc-800 text-amber-400 group-hover:bg-amber-500 group-hover:text-black font-semibold transition">
          ${ch.timestamp}
        </span>
        <span class="text-xs text-zinc-300 group-hover:text-white truncate font-medium">
          ${ch.title}
        </span>
      </div>
      <i data-lucide="play" class="w-3.5 h-3.5 text-zinc-600 group-hover:text-amber-400 flex-shrink-0 transition"></i>
    `;
    list.appendChild(item);
  });
}

// Render 10 Titles
function renderTitles(titles) {
  const grid = document.getElementById("titlesGrid");
  grid.innerHTML = "";

  titles.forEach((t, i) => {
    const card = document.createElement("div");
    const styleColors = {
      question: "bg-blue-500/10 text-blue-400 border-blue-500/20",
      curiosity: "bg-purple-500/10 text-purple-400 border-purple-500/20",
      debate: "bg-red-500/10 text-red-400 border-red-500/20",
      contrarian: "bg-amber-500/10 text-amber-400 border-amber-500/20",
      story: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
    };
    const badgeStyle = styleColors[t.style.toLowerCase()] || "bg-zinc-800 text-zinc-400 border-zinc-700";

    card.className = "bg-brand-card border border-brand-border hover:border-amber-500/50 rounded-xl p-5 cursor-pointer transition relative group flex flex-col justify-between";
    card.onclick = () => selectActiveTitle(t.title);

    card.innerHTML = `
      <div>
        <div class="flex items-center justify-between mb-2">
          <span class="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${badgeStyle}">
            ${t.style}
          </span>
          <span class="text-xs text-zinc-500 font-mono">#${i + 1}</span>
        </div>
        <h3 class="text-base font-bold text-zinc-100 group-hover:text-amber-400 transition leading-snug">
          ${t.title}
        </h3>
        <p class="text-xs text-zinc-400 mt-2 line-clamp-2">
          ${t.rationale}
        </p>
      </div>
      <div class="mt-4 pt-3 border-t border-brand-border/60 flex items-center justify-between text-xs text-zinc-500 group-hover:text-amber-400">
        <span>Click para seleccionar</span>
        <i data-lucide="check" class="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition"></i>
      </div>
    `;
    grid.appendChild(card);
  });
}

function selectActiveTitle(title) {
  document.getElementById("epHeaderTitle").textContent = title;
  document.getElementById("pubTitle").value = title;
  document.getElementById("thumbHeadlineInput").value = title;
  updateLiveCanvas();
  showToast(`Título seleccionado: "${title}"`);
}

// Render 16:9 Clips
function renderClips(clipsFiles, clipsMeta) {
  const grid = document.getElementById("clipsGrid");
  grid.innerHTML = "";

  if (clipsFiles.length === 0) {
    grid.innerHTML = `
      <div class="col-span-2 text-center py-12 border border-dashed border-brand-border rounded-xl">
        <i data-lucide="scissors" class="w-8 h-8 text-zinc-600 mx-auto mb-2"></i>
        <p class="text-sm text-zinc-400">No se encontraron clips 16:9 cortados aún.</p>
      </div>
    `;
    return;
  }

  clipsFiles.forEach((clip, i) => {
    const meta = clipsMeta[i] || {};
    const card = document.createElement("div");
    card.className = "bg-brand-card border border-brand-border rounded-xl overflow-hidden flex flex-col";
    card.innerHTML = `
      <div class="bg-black aspect-video relative">
        <video controls src="${clip.url}" class="w-full h-full object-contain"></video>
      </div>
      <div class="p-5 flex-1 flex flex-col justify-between space-y-3">
        <div>
          <div class="flex items-center justify-between text-xs text-zinc-500 mb-1">
            <span class="font-mono text-cyan-400 font-semibold">Clip #${i + 1}</span>
            <span>${clip.filename}</span>
          </div>
          <h4 class="font-bold text-sm text-white">${meta.title || clip.filename}</h4>
          <p class="text-xs text-zinc-400 mt-1.5">${meta.hook || meta.summary || ""}</p>
        </div>
      </div>
    `;
    grid.appendChild(card);
  });
}

// Render 9:16 Shorts
function renderShorts(shortsFiles, shortsMeta) {
  const grid = document.getElementById("shortsGrid");
  grid.innerHTML = "";

  if (shortsFiles.length === 0) {
    grid.innerHTML = `
      <div class="col-span-3 text-center py-12 border border-dashed border-brand-border rounded-xl">
        <i data-lucide="smartphone" class="w-8 h-8 text-zinc-600 mx-auto mb-2"></i>
        <p class="text-sm text-zinc-400">No se encontraron shorts 9:16 generados aún.</p>
      </div>
    `;
    return;
  }

  shortsFiles.forEach((short, i) => {
    const meta = shortsMeta[i] || {};
    const card = document.createElement("div");
    card.className = "bg-brand-card border border-brand-border rounded-xl overflow-hidden flex flex-col items-center p-4 space-y-3";
    card.innerHTML = `
      <!-- 9:16 Phone Frame -->
      <div class="w-full max-w-[220px] aspect-[9/16] bg-black rounded-xl overflow-hidden border-2 border-zinc-800 shadow-2xl relative">
        <video controls src="${short.url}" class="w-full h-full object-cover"></video>
      </div>
      <div class="w-full text-center space-y-1">
        <span class="text-[10px] font-mono text-pink-400 font-bold uppercase tracking-wider">Short #${i + 1}</span>
        <h4 class="font-bold text-xs text-white truncate">${meta.title || short.filename}</h4>
        <p class="text-[11px] text-zinc-400 italic line-clamp-2">"${meta.hook_quote || ""}"</p>
      </div>
    `;
    grid.appendChild(card);
  });
}

// Thumbnail Studio Initialization
function initThumbnailStudio(data) {
  const activeTitle = data.analysis.title_options?.[0]?.title || "LA TRAMPA DEL TRIBALISMO";
  document.getElementById("thumbHeadlineInput").value = activeTitle;
  document.getElementById("thumbSubtextInput").value = "Conversación franca y sin rodeos";

  const list = document.getElementById("thumbBackgroundsList");
  list.innerHTML = "";

  const backgrounds = (data.thumbnails || []).filter(t => !t.filename.includes("composite") && !t.filename.includes("final"));
  
  if (backgrounds.length === 0 && data.thumbnails?.length > 0) {
    backgrounds.push(data.thumbnails[0]);
  }

  if (backgrounds.length > 0) {
    backgrounds.forEach((bg, idx) => {
      const item = document.createElement("div");
      item.className = "flex-shrink-0 w-28 aspect-video rounded-lg overflow-hidden border-2 border-transparent hover:border-amber-400 cursor-pointer transition relative";
      item.onclick = () => selectThumbnailBackground(bg.url, bg.path);
      item.innerHTML = `
        <img src="${bg.url}" class="w-full h-full object-cover">
        <span class="absolute bottom-1 right-1 text-[9px] bg-black/80 px-1 rounded text-white font-mono">#${idx + 1}</span>
      `;
      list.appendChild(item);
    });
    selectThumbnailBackground(backgrounds[0].url, backgrounds[0].path);
  } else {
    // Generate default gradient
    currentBgImage = null;
    updateLiveCanvas();
  }

  // Pre-fill FLUX prompt with Concept 1 prompt if available
  const concepts = data.analysis?.thumbnail_concepts || [];
  if (concepts.length > 0) {
    document.getElementById("fluxPromptInput").value = concepts[0].gemini_prompt || "";
  }
}

function selectThumbnailBackground(url, path) {
  currentBgPath = path;
  currentBgImage = new Image();
  currentBgImage.crossOrigin = "anonymous";
  currentBgImage.src = url;
  currentBgImage.onload = () => updateLiveCanvas();
}

// Live Canvas Text Rendering Engine
function updateLiveCanvas() {
  const canvas = document.getElementById("thumbCanvas");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;

  // Clear
  ctx.clearRect(0, 0, width, height);

  // 1. Draw Background Image or Fallback Gradient
  if (currentBgImage && currentBgImage.complete && currentBgImage.naturalWidth > 0) {
    ctx.drawImage(currentBgImage, 0, 0, width, height);
  } else {
    const grad = ctx.createLinearGradient(0, 0, width, height);
    grad.addColorStop(0, "#1c1917");
    grad.addColorStop(1, "#0c0a09");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, width, height);
  }

  // 2. Dark Scrim Overlays
  // Top brand scrim
  ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  ctx.fillRect(0, 0, width, 90);

  // Bottom text scrim
  ctx.fillStyle = "rgba(0, 0, 0, 0.70)";
  ctx.fillRect(0, 480, width, 240);

  // 3. Top-Left Badge: ADN DIVERGENTE
  ctx.fillStyle = "rgba(0, 0, 0, 0.85)";
  ctx.strokeStyle = "#F59E0B";
  ctx.lineWidth = 2;
  ctx.fillRect(30, 22, 210, 40);
  ctx.strokeRect(30, 22, 210, 40);

  ctx.font = "bold 20px 'Oswald', Impact, sans-serif";
  ctx.fillStyle = "#F59E0B";
  ctx.textAlign = "center";
  ctx.fillText("ADN DIVERGENTE", 135, 49);

  // 4. Bottom-Left Badge: EPISODIO COMPLETO
  const badgeText = document.getElementById("thumbBadgeInput").value || "EPISODIO COMPLETO";
  ctx.fillStyle = "rgba(220, 38, 38, 0.9)";
  ctx.fillRect(35, 665, 175, 30);
  ctx.font = "bold 14px 'Inter', sans-serif";
  ctx.fillStyle = "#FFFFFF";
  ctx.textAlign = "center";
  ctx.fillText(badgeText.toUpperCase(), 122, 685);

  // 5. Headline Text Wrapping & Dynamic Sizing
  const headline = (document.getElementById("thumbHeadlineInput").value || "").trim().toUpperCase();
  const subtext = (document.getElementById("thumbSubtextInput").value || "").trim();

  const maxTextWidth = 1120;
  let fontSize = 54;
  ctx.font = `bold ${fontSize}px 'Oswald', Impact, 'Arial Black', sans-serif`;

  let words = headline.split(" ");
  let lines = [];
  let currentLine = "";

  words.forEach(w => {
    let testLine = currentLine ? `${currentLine} ${w}` : w;
    if (ctx.measureText(testLine).width > maxTextWidth && currentLine) {
      lines.push(currentLine);
      currentLine = w;
    } else {
      currentLine = testLine;
    }
  });
  if (currentLine) lines.push(currentLine);

  // Scale down if more than 2 lines
  if (lines.length > 2) {
    fontSize = 42;
    ctx.font = `bold ${fontSize}px 'Oswald', Impact, sans-serif`;
  }

  // Draw Headline
  ctx.textAlign = "center";
  ctx.lineJoin = "round";
  ctx.lineWidth = 9;
  ctx.strokeStyle = "#000000";

  let startY = 560 - (lines.length - 1) * (fontSize * 0.6);

  lines.forEach((line, idx) => {
    const y = startY + idx * (fontSize + 6);
    ctx.strokeText(line, width / 2, y);
    ctx.fillStyle = (idx % 2 === 0) ? "#FFFFFF" : "#FBBF24";
    ctx.fillText(line, width / 2, y);
  });

  // 6. Draw Subtext
  if (subtext) {
    ctx.font = "bold 24px 'Inter', sans-serif";
    ctx.lineWidth = 5;
    ctx.strokeStyle = "#000000";
    ctx.fillStyle = "#FDE68A";
    const subY = startY + lines.length * (fontSize + 4) + 12;
    ctx.strokeText(subtext, width / 2, subY);
    ctx.fillText(subtext, width / 2, subY);
  }
}

// Download Canvas Thumbnail
function downloadThumbnail() {
  const canvas = document.getElementById("thumbCanvas");
  const link = document.createElement("a");
  link.download = `${currentEpisode?.id || 'adn'}_thumbnail.jpg`;
  link.href = canvas.toDataURL("image/jpeg", 0.95);
  link.click();
  showToast("Miniatura descargada con éxito!");
}

// Trigger Local FLUX Image Render
async function triggerFluxRender() {
  const prompt = document.getElementById("fluxPromptInput").value.trim();
  const btn = document.getElementById("fluxRenderBtn");
  if (!prompt) {
    alert("Por favor escribe un prompt en inglés para FLUX.");
    return;
  }

  btn.disabled = true;
  btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin mr-1.5"></i> Renderizando en Apple Silicon GPU...`;
  lucide.createIcons();

  try {
    const outPath = `${currentEpisode.directory}/thumbnails/flux_${Date.now()}.png`;
    const res = await fetch("/api/thumbnails/flux-generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: prompt,
        output_path: outPath,
        quantize: 4
      })
    });
    const job = await res.json();
    showToast("Renderizado FLUX iniciado en GPU...");

    // Poll job status
    const interval = setInterval(async () => {
      const sRes = await fetch(`/api/jobs/${job.job_id}`);
      const sData = await sRes.json();
      if (sData.status === "completed") {
        clearInterval(interval);
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="wand-2" class="w-3.5 h-3.5 mr-1.5"></i> Renderizar Fondo con FLUX`;
        lucide.createIcons();
        showToast("¡Imagen generada con FLUX.1 exitosamente!");
        selectThumbnailBackground(sData.url, sData.path);
      } else if (sData.status === "failed") {
        clearInterval(interval);
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="wand-2" class="w-3.5 h-3.5 mr-1.5"></i> Renderizar Fondo con FLUX`;
        lucide.createIcons();
        alert(`Error al generar con FLUX: ${sData.message}`);
      }
    }, 2000);
  } catch (err) {
    btn.disabled = false;
    btn.innerHTML = `<i data-lucide="wand-2" class="w-3.5 h-3.5 mr-1.5"></i> Renderizar Fondo con FLUX`;
    alert("Error al contactar al servidor FLUX");
  }
}

// Save All Changes to Server
async function saveAllChanges() {
  if (!currentEpisode) return;

  const payload = {
    title: document.getElementById("pubTitle").value,
    youtube_description: document.getElementById("descEditor").value,
  };

  try {
    const res = await fetch(`/api/episodes/${currentEpisode.id}/save?path=${encodeURIComponent(currentEpisode.directory)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      showToast("✓ Cambios guardados correctamente en JSON y disco");
    } else {
      showToast("Error al guardar cambios");
    }
  } catch (err) {
    showToast("Error al conectar con el servidor");
  }
}

// Copy Description
function copyDescription() {
  const desc = document.getElementById("descEditor").value;
  navigator.clipboard.writeText(desc);
  showToast("Descripción copiada al portapapeles");
}

// Publish to YouTube
async function publishEpisode() {
  if (!currentEpisode || !currentEpisode.video_path) {
    alert("No hay archivo de video cargado para publicar.");
    return;
  }

  const btn = document.getElementById("publishBtn");
  const statusBox = document.getElementById("uploadStatusBox");
  const privacy = document.getElementById("pubPrivacy").value;
  const title = document.getElementById("pubTitle").value;

  if (!confirm(`¿Deseas subir "${title}" a YouTube como ${privacy.toUpperCase()}?`)) {
    return;
  }

  btn.disabled = true;
  statusBox.classList.remove("hidden");
  statusBox.innerHTML = `⏳ <b>Iniciando subida a YouTube...</b> Por favor no cierres la ventana.`;

  try {
    const res = await fetch("/api/youtube/upload-episode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        video_path: currentEpisode.video_path,
        analysis_path: `${currentEpisode.directory}/${currentEpisode.id}_analysis.json`,
        title: title,
        privacy: privacy,
        description: document.getElementById("descEditor").value
      })
    });
    const job = await res.json();

    const interval = setInterval(async () => {
      const sRes = await fetch(`/api/jobs/${job.job_id}`);
      const sData = await sRes.json();
      if (sData.status === "completed") {
        clearInterval(interval);
        btn.disabled = false;
        statusBox.className = "p-4 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs";
        statusBox.innerHTML = `🎉 <b>¡Video subido exitosamente a YouTube!</b> <a href="${sData.url}" target="_blank" class="underline font-bold text-amber-400 ml-2">Ver Video (${sData.url})</a>`;
      } else if (sData.status === "failed") {
        clearInterval(interval);
        btn.disabled = false;
        statusBox.className = "p-4 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-xs";
        statusBox.innerHTML = `❌ <b>Error al subir video:</b> ${sData.message}`;
      }
    }, 3000);
  } catch (err) {
    btn.disabled = false;
    statusBox.textContent = `Error de conexión: ${err.message}`;
  }
}
