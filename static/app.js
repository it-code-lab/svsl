let rowCounter = 0;

const rowFieldMap = [
  ["title_", 0],
  ["description_", 1],
  ["tags_", 2],
  ["video_file_name_", 3],
  ["thumbnail_file_name_", 4],
  ["scheduled_at_", 5],
  ["pinterest_link_url_", 6],
];

document.addEventListener("DOMContentLoaded", () => {
  initPersistentControls();
  initYouTubeControls();
  initSpreadsheetPaste();
  initScheduleHelper();
});

function addRow(values = {}) {
  rowCounter += 1;
  const rowId = String(Date.now()) + "_" + String(rowCounter);
  const template = document.getElementById("rowTemplate").innerHTML
    .replaceAll("__ROW_ID__", rowId)
    .replaceAll("__ROW_NUM__", rowCounter);

  const wrapper = document.createElement("div");
  wrapper.innerHTML = template;
  const row = wrapper.firstElementChild;
  document.getElementById("rows").appendChild(row);
  fillRow(row, values);
}

function removeRow(button) {
  const row = button.closest(".video-row");
  if (row) row.remove();
}

function initPersistentControls() {
  document.querySelectorAll("[data-persist]").forEach((control) => {
    const storageKey = storageKeyFor(control);
    const storedValue = localStorage.getItem(storageKey);
    if (storedValue !== null) {
      control.value = storedValue;
    }

    control.addEventListener("change", () => {
      localStorage.setItem(storageKey, control.value);
    });
  });

  document.querySelectorAll('input[name="platforms"]').forEach((checkbox) => {
    const storageKey = `scheduler.platform.${checkbox.value}`;
    checkbox.checked = localStorage.getItem(storageKey) === "true";
    checkbox.addEventListener("change", () => {
      localStorage.setItem(storageKey, checkbox.checked ? "true" : "false");
    });
  });
}

function initYouTubeControls() {
  const channelSelect = document.getElementById("youtubeChannel");
  const playlistSelect = document.getElementById("youtubePlaylist");
  const refreshButton = document.getElementById("refreshYouTubePlaylists");
  if (!channelSelect || !playlistSelect) return;

  channelSelect.addEventListener("change", () => {
    localStorage.removeItem(storageKeyFor(playlistSelect));
    loadYouTubePlaylists(false);
  });

  if (refreshButton) {
    refreshButton.addEventListener("click", () => loadYouTubePlaylists(true));
  }

  loadYouTubePlaylists(false);
}

async function loadYouTubePlaylists(force = false) {
  const channelSelect = document.getElementById("youtubeChannel");
  const playlistSelect = document.getElementById("youtubePlaylist");
  const channelId = channelSelect.value;
  const storedPlaylist = localStorage.getItem(storageKeyFor(playlistSelect)) || "";

  resetSelect(playlistSelect, channelId ? "Loading playlists..." : "Choose a YouTube channel first");
  if (!channelId) return;

  try {
    const forceParam = force ? "?force=true" : "";
    const response = await fetch(
      `/api/youtube/channels/${encodeURIComponent(channelId)}/playlists${forceParam}`,
    );
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Could not load playlists.");
    }

    playlistSelect.innerHTML = '<option value="">No playlist</option>';
    data.items.forEach((playlist) => {
      const option = document.createElement("option");
      option.value = playlist.id;
      option.textContent = `${playlist.name} - ${playlist.id}`;
      playlistSelect.appendChild(option);
    });
    playlistSelect.disabled = false;
    playlistSelect.value = storedPlaylist;
  } catch (error) {
    resetSelect(playlistSelect, error.message || "Could not load playlists");
  }
}

function initSpreadsheetPaste() {
  const replaceButton = document.getElementById("replaceRowsFromPaste");
  const appendButton = document.getElementById("appendRowsFromPaste");

  if (replaceButton) {
    replaceButton.addEventListener("click", () => createRowsFromPaste(true));
  }
  if (appendButton) {
    appendButton.addEventListener("click", () => createRowsFromPaste(false));
  }
}

function createRowsFromPaste(replaceExisting) {
  const text = document.getElementById("pasteTable").value.trim();
  if (!text) return;

  if (replaceExisting) {
    document.getElementById("rows").innerHTML = "";
  }

  parsePastedRows(text).forEach((values) => addRow(values));
}

function parsePastedRows(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.split("\t").map((cell) => cell.trim()))
    .filter((cells) => cells.some(Boolean))
    .map((cells) => ({
      title: cells[0] || "",
      description: cells[1] || "",
      tags: cells[2] || "",
      video_file_name: cells[3] || "",
      thumbnail_file_name: cells[4] || "",
      scheduled_at: normalizeDateTimeLocal(cells[5] || ""),
      pinterest_link_url: cells[6] || "",
    }));
}

function fillRow(row, values) {
  rowFieldMap.forEach(([prefix, index]) => {
    const key = prefix.replace(/_$/, "");
    const field = row.querySelector(`[name^="${prefix}"]`);
    if (field && values[key]) {
      field.value = values[key];
    }
  });
}

function initScheduleHelper() {
  const button = document.getElementById("fillScheduleTimes");
  if (!button) return;

  button.addEventListener("click", () => {
    const startValue = document.getElementById("scheduleStart").value;
    const gapMinutes = Number(document.getElementById("scheduleGapMinutes").value || "0");
    if (!startValue) return;

    const startDate = new Date(startValue);
    document.querySelectorAll('.video-row input[name^="scheduled_at_"]').forEach((input, index) => {
      const nextDate = new Date(startDate.getTime() + index * gapMinutes * 60 * 1000);
      input.value = toDateTimeLocalValue(nextDate);
    });
  });
}

function normalizeDateTimeLocal(value) {
  if (!value) return "";
  const normalized = value.replace(" ", "T");
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return value;
  return toDateTimeLocalValue(parsed);
}

function toDateTimeLocalValue(date) {
  const pad = (value) => String(value).padStart(2, "0");
  return [
    date.getFullYear(),
    "-",
    pad(date.getMonth() + 1),
    "-",
    pad(date.getDate()),
    "T",
    pad(date.getHours()),
    ":",
    pad(date.getMinutes()),
  ].join("");
}

function resetSelect(select, message) {
  select.innerHTML = "";
  const option = document.createElement("option");
  option.value = "";
  option.textContent = message;
  select.appendChild(option);
  select.disabled = true;
}

function storageKeyFor(control) {
  return `scheduler.${control.dataset.persist}`;
}
