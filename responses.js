const body = document.querySelector("#records-body");
const countLabel = document.querySelector("#record-count");
const statusLabel = document.querySelector("#records-status");
const exportButton = document.querySelector("#export-button");
const clearButton = document.querySelector("#clear-button");
let records = [];

async function loadRecords() {
  try {
    body.replaceChildren();
    const response = await fetch("/api/guru/submissions", { cache: "no-store" });
    if (!(response.headers.get("content-type") || "").includes("application/json")) throw new Error("The server returned a non-JSON response. Restart the latest server.py.");
    const result = await response.json(); records = result.records || [];
    countLabel.textContent = `${records.length} submissions`; exportButton.disabled = records.length === 0; clearButton.disabled = records.length === 0;
    if (!records.length) { const row = body.insertRow(); const cell = row.insertCell(); cell.colSpan = 6; cell.textContent = "No student submissions yet."; return; }
    for (const record of records) {
      const row = body.insertRow();
      for (const value of [record.nama, record.id, record.group, `${record.score}/${record.total}`, record.submitted_at]) row.insertCell().textContent = value;
      const action = row.insertCell(); const details = document.createElement("details");
      const summary = document.createElement("summary"); summary.textContent = "View answers";
      const answers = document.createElement("p");
      answers.textContent = Array.from({length: 10}, (_, i) => `Q${i + 1}: ${record.answers[String(i + 1)] || "—"}`).join(" · ");
      details.append(summary, answers); action.append(details);
    }
  } catch (error) { countLabel.textContent = "Could not load records"; statusLabel.textContent = error.message || "Make sure server.py is running."; }
}

clearButton.addEventListener("click", async () => {
  if (!records.length || !window.confirm(`Permanently delete all ${records.length} student submissions? Students will be able to submit again afterward.`)) return;
  clearButton.disabled = true; statusLabel.textContent = "Clearing records…";
  try {
    const response = await fetch("/api/guru/submissions", { method: "DELETE" });
    if (!(response.headers.get("content-type") || "").includes("application/json")) throw new Error("The server response was not valid. Restart the latest server.py.");
    const result = await response.json();
    if (!response.ok) throw new Error(result.mesej || "Could not clear the records.");
    statusLabel.textContent = result.mesej; statusLabel.classList.add("success");
    await loadRecords();
  } catch (error) {
    statusLabel.textContent = error.message || "Could not connect to the server.";
    clearButton.disabled = false;
  }
});

function csvCell(value) {
  let text = String(value ?? ""); if (/^[=+@\-]/.test(text)) text = "'" + text;
  return `"${text.replaceAll('"', '""')}"`;
}

exportButton.addEventListener("click", () => {
  const headings = ["Name", "Student ID", "Group", "Score", "Total questions", "Submitted UTC", ...Array.from({length: 10}, (_, i) => `Question ${i + 1}`)];
  const lines = [headings, ...records.map(r => [r.nama, r.id, r.group, r.score, r.total, r.submitted_at, ...Array.from({length: 10}, (_, i) => r.answers[String(i + 1)] || "")])].map(row => row.map(csvCell).join(","));
  const blob = new Blob(["\ufeff" + lines.join("\r\n")], {type: "text/csv;charset=utf-8"});
  const url = URL.createObjectURL(blob); const link = document.createElement("a");
  link.href = url; link.download = "student_records.csv"; link.click(); URL.revokeObjectURL(url);
});
loadRecords();
