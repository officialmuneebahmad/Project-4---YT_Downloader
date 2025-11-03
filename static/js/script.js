// script.js — handles theme toggle + YouTube download logic safely

document.addEventListener("DOMContentLoaded", () => {
  // === Element references ===
  const toggleBtn = document.getElementById("toggle-btn");
  const sectionColor = document.getElementById("sectionColor");
  const downloadBtn = document.getElementById("downloadBtn");
  const statusEl = document.getElementById("status");
  const htmlEl = document.documentElement;
  const formatSelect = document.getElementById("formatSelect");
  const formatType = document.getElementById("format");

  // === Theme handling ===
  function applyTheme(theme) {
    if (theme === "dark") {
      htmlEl.classList.add("dark");
      toggleBtn.innerHTML = `<span>☀️</span><span class="max-sm:hidden inline"> Day</span>`;
      sectionColor.classList.replace("bg-[#f0f0f0]", "bg-gray-800");
      sectionColor.classList.replace("text-black", "text-white");
      document.body.style.backgroundColor = "#0a0a0a";
      document.body.style.color = "#f0f0f0";
      toggleBtn.style.border = "1px solid white";
    } else {
      htmlEl.classList.remove("dark");
      toggleBtn.innerHTML = `<span>🌙</span><span class="max-sm:hidden inline"> Night</span>`;
      sectionColor.classList.replace("bg-gray-800", "bg-[#f0f0f0]");
      sectionColor.classList.replace("text-white", "text-black");
      document.body.style.backgroundColor = "#ffffff";
      document.body.style.color = "#0a0a0a";
      
    }
  }

  const savedTheme = localStorage.getItem("theme");
  if (savedTheme) applyTheme(savedTheme);
  else if (window.matchMedia("(prefers-color-scheme: dark)").matches) applyTheme("dark");
  else applyTheme("light");

  toggleBtn.addEventListener("click", () => {
    const isDark = htmlEl.classList.toggle("dark");
    const newTheme = isDark ? "dark" : "light";
    applyTheme(newTheme);
    localStorage.setItem("theme", newTheme);
  });

  // === Utility: unique task ID generator ===
  function generateTaskId() {
    return "task_" + Math.random().toString(36).substring(2, 10);
  }

  // === Download logic ===
  async function downloadVideo() {
    const url = document.getElementById("url").value.trim();
    const format = document.getElementById("format").value;
    const quality = document.getElementById("formatSelect")?.value;

    if (!url) {
      statusEl.textContent = "Enter a YouTube URL.";
      statusEl.style.color = "salmon";
      return;
    }

    const taskId = generateTaskId();
    downloadBtn.disabled = true;
    downloadBtn.textContent = "Preparing...";
    statusEl.textContent = "";

    // Progress bar setup
    const progressBar = document.createElement("div");
    progressBar.className = "w-full bg-gray-300 rounded-full h-2 mt-4 overflow-hidden";
    const progressInner = document.createElement("div");
    progressInner.className = "bg-green-500 h-2 rounded-full transition-all duration-300 ease-out";
    progressBar.appendChild(progressInner);
    sectionColor.appendChild(progressBar);

    try {
      // Start the actual download
      const resp = await fetch("/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, format, quality, task_id: taskId }),
      });

      const data = await resp.json();
      if (data.error) {
        statusEl.textContent = "❌ " + data.error;
        progressBar.remove();
        downloadBtn.disabled = false;
        downloadBtn.textContent = "Download";
        return;
      }

      // Wait 1 second before starting progress stream
      setTimeout(() => {
        monitorProgress(taskId);
      }, 1000);

      // Start listening for progress updates
      const eventSrc = new EventSource(`/progress/${taskId}`);
      eventSrc.onmessage = (e) => {
        if (!e.data) return;
        const info = JSON.parse(e.data);

        if (info.status === "downloading") {
          progressInner.style.width = `${info.progress}%`;
          downloadBtn.textContent = `Downloading... ${info.progress}%`;
        } else if (info.status === "finished") {
          progressInner.style.width = "100%";
          downloadBtn.textContent = "Finishing...";
          eventSrc.close();

          setTimeout(async () => {
            const fileResp = await fetch(`/fetch/${taskId}`);
            const blob = await fileResp.blob();
            const a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "download";
            a.click();
            URL.revokeObjectURL(a.href);
            progressBar.remove();
            downloadBtn.disabled = false;
            downloadBtn.textContent = "Download";
            statusEl.textContent = "✅ Download complete!";
          }, 800);
        } else if (info.status === "error") {
          eventSrc.close();
          progressBar.remove();
          downloadBtn.disabled = false;
          downloadBtn.textContent = "Download";
          statusEl.textContent = "❌ " + info.message;
        }
      };
    } catch (err) {
      statusEl.textContent = "❌ Download failed: " + err.message;
      progressBar.remove();
      downloadBtn.disabled = false;
      downloadBtn.textContent = "Download";
    }
  }

  // === Event bindings ===
  downloadBtn.addEventListener("click", downloadVideo);
  document.getElementById("url").addEventListener("keydown", (e) => {
    if (e.key === "Enter") downloadVideo();
  });

  // === Quality options handling === 
  function populateQualities() {
    formatSelect.innerHTML = "";
    if (formatType.value === "mp4") {
      ["720p", "480p"].forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q;
        opt.textContent = q;
        formatSelect.appendChild(opt);
      });
    } else {
      ["320kbps", "128kbps"].forEach((q) => {
        const opt = document.createElement("option");
        opt.value = q;
        opt.textContent = q;
        formatSelect.appendChild(opt);
      });
    }
  }

  formatType.addEventListener("change", populateQualities);
  populateQualities(); // initialize on load
});
