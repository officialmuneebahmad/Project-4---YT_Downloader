document.addEventListener("DOMContentLoaded", () => {
  const urlInput = document.getElementById("url");
  const formatSelect = document.getElementById("format");
  const qualitySelect = document.getElementById("formatSelect");
  const downloadBtn = document.getElementById("downloadBtn");
  const statusEl = document.getElementById("status");

  // 🌓 Theme toggle
  const toggleBtn = document.getElementById("toggle-btn");
  toggleBtn.addEventListener("click", () => {
    document.body.classList.toggle("dark");
    if (document.body.classList.contains("dark")) {
      toggleBtn.innerHTML = "☀️ Day";
    } else {
      toggleBtn.innerHTML = "🌙 Night";
    }
  });

  // 🎞 Fetch available qualities when URL changes
  urlInput.addEventListener("change", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    statusEl.textContent = "Fetching available formats...";
    qualitySelect.innerHTML = '<option disabled selected>Loading...</option>';

    try {
      const res = await fetch("/formats", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });
      const data = await res.json();

      if (data.error) {
        statusEl.textContent = data.error;
        return;
      }

      // Reset select
      qualitySelect.innerHTML = "";

      // Choose list based on format (video or audio)
      const list =
        formatSelect.value === "mp3"
          ? data.audio_formats
          : data.video_formats;

      if (!list.length) {
        qualitySelect.innerHTML =
          '<option disabled>No formats found</option>';
        statusEl.textContent = "No available formats.";
        return;
      }

      list.forEach((f) => {
        const opt = document.createElement("option");
        if (formatSelect.value === "mp3") {
          opt.value = f.format_id;
          opt.textContent = `${f.abr || "?"} kbps (${f.ext})`;
        } else {
          opt.value = f.format_id;
          opt.textContent = `${f.resolution || "?"} (${f.ext})`;
        }
        qualitySelect.appendChild(opt);
      });

      statusEl.textContent = `Found ${list.length} formats for ${data.title}`;
    } catch (err) {
      console.error(err);
      statusEl.textContent = "Error fetching formats.";
    }
  });

  // 🎬 Download video
  downloadBtn.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    const fmt = formatSelect.value;
    const format_id = qualitySelect.value;

    if (!url) {
      alert("Please enter a YouTube URL.");
      return;
    }
    if (!format_id) {
      alert("Please choose a quality.");
      return;
    }

    downloadBtn.disabled = true;
    downloadBtn.textContent = "Downloading...";
    statusEl.textContent = "Download started...";

    try {
      const res = await fetch("/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format: fmt, format_id }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.error || "Download failed");
      }

      // Download blob
      const blob = await res.blob();
      const urlBlob = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = urlBlob;
      a.download = "download." + (fmt === "mp3" ? "mp3" : "mp4");
      a.click();
      window.URL.revokeObjectURL(urlBlob);

      statusEl.textContent = "✅ Download complete!";
      downloadBtn.textContent = "Download";
    } catch (err) {
      console.error(err);
      statusEl.textContent = "❌ " + err.message;
      downloadBtn.textContent = "Retry";
    } finally {
      downloadBtn.disabled = false;
    }
  });
});










// // main.js - handles theme toggle + download flow

// // download logic
// const downloadBtn = document.getElementById('downloadBtn');
// const statusEl = document.getElementById('status');


// function setStatus(msg, isError=false){
// statusEl.textContent = msg;
// statusEl.style.color = isError ? 'salmon' : '';
// }


// async function download() {
// const url = document.getElementById('url').value.trim();
// const format = document.getElementById('format').value;
// if (!url) { setStatus('Enter a YouTube URL.', true); return; }


// setStatus('Preparing download...');
// downloadBtn.disabled = true;


// try {
// const resp = await fetch('/download', {
// method: 'POST',
// headers: { 'Content-Type': 'application/json' },
// body: JSON.stringify({ url, format })
// });


// if (!resp.ok) {
// const err = await resp.json().catch(()=>({error:'Unknown error'}));
// setStatus(err.error || 'Server returned an error.', true);
// return;
// }


// // response is a binary file
// const blob = await resp.blob();
// const disposition = resp.headers.get('content-disposition') || '';
// let filename = 'download';
// const m = /filename\*=UTF-8''([^;]+)/.exec(disposition) || /filename="?([^";]+)"?/.exec(disposition);
// if (m && m[1]) filename = decodeURIComponent(m[1]);


// const urlObj = URL.createObjectURL(blob);
// const a = document.createElement('a');
// a.href = urlObj;
// a.download = filename;
// document.body.appendChild(a);
// a.click();
// a.remove();
// URL.revokeObjectURL(urlObj);


// setStatus('Download finished. Check your browser downloads.');
// } catch (e) {
// setStatus('Download failed: ' + e.message, true);
// } finally {
// downloadBtn.disabled = false;
// }
// }


// downloadBtn.addEventListener('click', download);


// // allow enter key
// document.getElementById('url').addEventListener('keydown', (e)=>{ if(e.key==='Enter') download(); });