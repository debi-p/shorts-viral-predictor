const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('status');
const resultsBox = document.getElementById('results-box');
const scoreVal = document.getElementById('score-val');
const suggestionsList = document.getElementById('suggestions-list');
const progressWrap = document.getElementById('progress-wrap');
const youtubeUrlInput = document.getElementById('youtube-url');
const analyzeUrlButton = document.getElementById('analyze-url');

dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('hover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('hover'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('hover');
  if (e.dataTransfer.files.length > 0) handleVideoFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', (e) => {
  if (e.target.files.length > 0) handleVideoFile(e.target.files[0]);
});
analyzeUrlButton.addEventListener('click', analyzeYouTubeUrl);

function handleVideoFile(file) {
  statusDiv.innerText = "Checking video duration...";
  statusDiv.style.color = "#333";
  resultsBox.style.display = "none";
  progressWrap.style.display = "none";

  const video = document.createElement('video');
  video.preload = 'metadata';
  video.onloadedmetadata = function() {
    window.URL.revokeObjectURL(video.src);
    if (video.duration > 60) {
      statusDiv.innerText = `Rejected: Video is ${Math.round(video.duration)}s. Shorts must be under 60s!`;
      statusDiv.style.color = "red";
      return;
    }
    uploadVideoForAnalysis(file);
  };
  video.src = URL.createObjectURL(file);
}

function uploadVideoForAnalysis(file) {
  const cleanTitle = file.name.replace(/\.[^/.]+$/, "").replace(/[_-]/g, " ");
  const url = `http://localhost:8765/analyze-video?title=${encodeURIComponent(cleanTitle)}`;
  setLoading(true, "Uploading video and transcribing with local Whisper...");
  console.log("[Backend Upload] title:", cleanTitle);
  console.log("[Backend Upload] file:", file.name, "size=", file.size, "type=", file.type);

  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    body: file
  })
    .then(res => {
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      return res.json();
    })
    .then(renderResults)
    .catch(() => {
      setLoading(false);
      statusDiv.innerText = "Analysis failed or timed out. Check backend logs.";
      statusDiv.style.color = "red";
    });
}

function analyzeYouTubeUrl() {
  const youtubeUrl = youtubeUrlInput.value.trim();
  if (!youtubeUrl) {
    statusDiv.innerText = "Paste a YouTube Shorts URL first.";
    statusDiv.style.color = "red";
    return;
  }

  resultsBox.style.display = "none";
  setLoading(true, "Fetching YouTube title and description...");
  console.log("[YouTube URL Payload] url:", youtubeUrl);

  fetch('http://localhost:8765/analyze-youtube-url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: youtubeUrl })
  })
    .then(res => {
      if (!res.ok) throw new Error(`Backend returned ${res.status}`);
      return res.json();
    })
    .then(renderResults)
    .catch((error) => {
      console.error("[YouTube URL] error:", error);
      setLoading(false);
      statusDiv.innerText = "Could not analyze YouTube URL. Check backend and URL.";
      statusDiv.style.color = "red";
    });
}

function renderResults(data) {
  setLoading(false);
  statusDiv.innerText = "Evaluation Complete!";
  statusDiv.style.color = "green";
  resultsBox.style.display = "block";
  scoreVal.innerText = `${data.score}%`;
  scoreVal.style.color = data.score >= 80 ? "green" : data.score >= 50 ? "orange" : "red";
  suggestionsList.innerHTML = "";
  data.suggestions.forEach((item, index) => {
    const div = document.createElement('div');
    div.className = "suggestion-item";
    const label = document.createElement('span');
    label.className = "suggestion-label";
    label.innerText = `Step ${index + 1}`;
    const text = document.createElement('span');
    text.innerText = item;
    div.appendChild(label);
    div.appendChild(text);
    suggestionsList.appendChild(div);
  });
}

function setLoading(isLoading, message = "") {
  progressWrap.style.display = isLoading ? "block" : "none";
  dropZone.style.pointerEvents = isLoading ? "none" : "auto";
  dropZone.style.opacity = isLoading ? "0.65" : "1";
  analyzeUrlButton.disabled = isLoading;
  analyzeUrlButton.style.opacity = isLoading ? "0.65" : "1";
  if (message) {
    statusDiv.innerText = message;
    statusDiv.style.color = "#333";
  }
}
