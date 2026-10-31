const form = document.querySelector("#student-form");
const status = document.querySelector("#status");
const button = document.querySelector("#submit-button");

async function readApiJson(response) {
  if (!(response.headers.get("content-type") || "").includes("application/json")) {
    throw new Error("The server may be outdated or this page was opened directly from a file. Restart it with `python server.py`, then open http://127.0.0.1:8765.");
  }
  return response.json();
}

async function renderMath(elements) {
  if (window.MathJax?.typesetPromise) {
    try { await window.MathJax.typesetPromise(elements); } catch (error) { console.warn("Could not render LaTeX:", error); }
  }
}

async function loadQuiz() {
  const unavailable = document.querySelector("#unavailable");
  try {
    const response = await fetch("/api/question", { cache: "no-store" });
    const result = await readApiJson(response);
    if (result.title) {
      document.querySelector("#quiz-title").textContent = result.title;
      document.title = `${result.title} | Student Quiz`;
    }
    const validity = document.querySelector("#quiz-validity");
    if (result.valid_from && result.valid_until) {
      validity.textContent = `Open from ${result.valid_from} through ${result.valid_until} (Malaysia time).`;
    }
    if (result.available && !result.is_open) {
      unavailable.querySelector("h2").textContent = result.valid_from && result.valid_until
        ? (result.today < result.valid_from ? "Quiz is not open yet" : "Quiz has closed")
        : "Quiz schedule not set";
      unavailable.querySelector("p").textContent = result.valid_from && result.valid_until
        ? `This quiz accepts responses from ${result.valid_from} through ${result.valid_until} (Malaysia time).`
        : "The lecturer has not set the form validity dates yet.";
      unavailable.classList.remove("hidden"); return;
    }
    if (!result.available || result.questions.length !== 10) { unavailable.classList.remove("hidden"); return; }
    const container = document.querySelector("#questions");
    for (const q of result.questions) {
      const fieldset = document.createElement("fieldset"); fieldset.className = "student-question";
      const legend = document.createElement("legend"); legend.textContent = `Question ${q.number} *`; fieldset.append(legend);
      const prompt = document.createElement("div"); prompt.className = "math-content student-prompt"; prompt.textContent = q.question_text; fieldset.append(prompt);
      const choices = document.createElement("div"); choices.className = "choices";
      for (const letter of ["A", "B", "C", "D"]) {
        const label = document.createElement("label"); label.className = "choice";
        const radio = document.createElement("input"); radio.type = "radio"; radio.name = `jawapan_${q.number}`; radio.value = letter; radio.required = letter === "A";
        const badge = document.createElement("span"); badge.className = "choice-letter"; badge.textContent = letter;
        const text = document.createElement("span"); text.className = "math-content"; text.textContent = q.options[letter];
        label.append(radio, badge, text); choices.append(label);
      }
      fieldset.append(choices); container.append(fieldset);
    }
    form.classList.remove("hidden"); await renderMath([container]);
  } catch {
    unavailable.classList.remove("hidden");
    unavailable.querySelector("p").textContent = "Could not load the quiz. Make sure server.py is running.";
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); status.textContent = ""; status.classList.remove("success"); button.disabled = true; button.textContent = "Menghantar…";
  const data = new FormData(form);
  const answers = {};
  for (let i = 1; i <= 10; i++) answers[String(i)] = String(data.get(`jawapan_${i}`) || "");
  try {
    const response = await fetch("/api/respons", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ nama: String(data.get("nama") || "").trim(), id: String(data.get("id") || "").trim(), group: String(data.get("group") || "").trim(), answers }),
    });
    const result = await readApiJson(response);
    if (!response.ok) throw new Error(result.mesej || "Could not submit your answers.");
    status.textContent = result.mesej; status.classList.add("success"); form.reset();
  } catch (error) { status.textContent = error.message || "Could not connect to the server."; }
  finally { button.disabled = false; button.innerHTML = 'Submit all answers <span aria-hidden="true">→</span>'; }
});
loadQuiz();


