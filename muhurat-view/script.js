async function generateMuhurat() {
  const startDate = document.getElementById("startDate").value;
  const endDate = document.getElementById("endDate").value;
  const requestType = document.getElementById("requestType").value;

  const loading = document.getElementById("loading");
  const result = document.getElementById("result");

  if (!startDate || !endDate) {
    showMessage("Please select a valid date range", "warning");
    return;
  }

  loading.classList.remove("hidden");
  result.innerHTML = "";

  try {
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      user_request: requestType
    });

    const response = await fetch(
      `http://127.0.0.1:8000/ai-muhurat-range?${params}`
    );

    const data = await response.json();
    loading.classList.add("hidden");

    if (data.status !== "success") {
      throw new Error("Muhurat calculation failed");
    }

    renderResult(data);

  } catch (error) {
    loading.classList.add("hidden");
    console.error(error);
    showMessage(
      "AI could not compute muhurat at this moment. Please try again.",
      "error"
    );
  }
}

/* ------------------------
   Render Result (Branded)
-------------------------*/
function renderResult(data) {
  const result = document.getElementById("result");

  let html = `
    <div class="mb-6">
      <h2 class="text-2xl font-bold bg-gradient-to-r from-amber-400 to-orange-500 bg-clip-text text-transparent">
        Recommended Muhurats
      </h2>
      <p class="text-sm text-gray-400 mt-1 capitalize">
        Event Type: ${data.request_type.replace("_", " ")}
      </p>
    </div>
  `;

  data.recommended_muhurats.forEach(m => {
    html += `
      <div class="relative mb-4 p-5 rounded-xl border border-white/10 bg-black/30 backdrop-blur-md hover:border-amber-400/40 transition">

        <span class="absolute -top-3 right-4 px-3 py-1 text-xs rounded-full bg-amber-400 text-black font-semibold">
          ${m.nakshatra}
        </span>

        <p class="text-sm text-gray-300 mt-2">
          🕒 ${m.start} – ${m.end}
        </p>

        ${
          m.explanation
            ? `<p class="text-xs text-gray-400 mt-3 leading-relaxed">
                 ${m.explanation}
               </p>`
            : ""
        }
      </div>
    `;
  });

  html += `
    <div class="mt-6 text-center">
      <a
        href="${data.pdf_url}"
        target="_blank"
        class="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-gradient-to-r from-green-400 to-emerald-600 text-black font-semibold hover:scale-105 transition"
      >
        📄 Download Detailed PDF
      </a>
    </div>
  `;

  result.innerHTML = html;
}

/* ------------------------
   UI Message Helper
-------------------------*/
function showMessage(message, type = "info") {
  const result = document.getElementById("result");

  const colors = {
    info: "text-blue-400",
    warning: "text-amber-400",
    error: "text-red-400"
  };

  result.innerHTML = `
    <div class="mt-6 text-center ${colors[type]}">
      ${message}
    </div>
  `;
}
