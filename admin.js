const form = document.querySelector("#teacher-form");
const status = document.querySelector("#teacher-status");
const answerPattern = /(?:^|[,\n;\s])(?:Q)?(\d+)\s*[:=.]\s*([A-D])\b/gi;

async function readApiJson(response) {
  if (!(response.headers.get("content-type") || "").includes("application/json")) {
    throw new Error("The server is outdated or this page was opened directly from the file. Stop it with Ctrl+C, restart using `python server.py`, then open http://127.0.0.1:8765/guru.");
  }
  return response.json();
}

function parseLatex(source, keyText) {
  const headings = [...source.matchAll(/\\textbf\s*\{\s*Question\s*(\d+)\s*\}/gi)];
  if (headings.length !== 10) throw new Error(`Found ${headings.length} question headings; exactly 10 are required, formatted like \\textbf{Question 1}.`);
  const answerKey = new Map();
  for (const match of keyText.matchAll(answerPattern)) answerKey.set(Number(match[1]), match[2].toUpperCase());
  const questions = [];
  for (let i = 0; i < headings.length; i++) {
    const start = headings[i].index + headings[i][0].length;
    const end = i + 1 < headings.length ? headings[i + 1].index : source.length;
    const block = source.slice(start, end);
    const begin = /\\begin\s*\{\s*enumerate\s*\}(?:\s*\[[^\]]*\])?/i.exec(block);
    if (!begin) throw new Error(`Question ${i + 1}: missing \\begin{enumerate}.`);
    const afterBegin = begin.index + begin[0].length;
    const endMatch = /\\end\s*\{\s*enumerate\s*\}/i.exec(block.slice(afterBegin));
    if (!endMatch) throw new Error(`Question ${i + 1}: missing \\end{enumerate}.`);
    const questionText = block.slice(0, begin.index).trim();
    const optionSource = block.slice(afterBegin, afterBegin + endMatch.index);
    const items = [...optionSource.matchAll(/\\item\b/g)];
    if (items.length !== 4) throw new Error(`Question ${i + 1}: exactly four \\item commands are required for choices A–D.`);
    const options = {};
    for (let j = 0; j < 4; j++) {
      const itemStart = items[j].index + items[j][0].length;
      const itemEnd = j + 1 < 4 ? items[j + 1].index : optionSource.length;
      options[String.fromCharCode(65 + j)] = optionSource.slice(itemStart, itemEnd).trim();
    }
    const number = Number(headings[i][1]);
    if (number !== i + 1) throw new Error("Question headings must be numbered consecutively from Question 1 to Question 10.");
    if (!questionText) throw new Error(`Question ${number} is empty.`);
    if (!answerKey.has(number)) throw new Error(`Answer key for question ${number} is missing.`);
    questions.push({ number, question_text: questionText, options, correct_answer: answerKey.get(number) });
  }
  if (answerKey.size !== 10) throw new Error("The answer key must contain 10 entries, for example 1:B, 2:A, ... 10:D.");
  return questions;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault(); status.textContent = ""; status.classList.remove("success");
  const button = document.querySelector("#save-button"); button.disabled = true;
  try {
    const questions = parseLatex(form.elements.latex_source.value, form.elements.answer_key.value);
    const response = await fetch("/api/guru/questions", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({
        valid_from: form.elements.valid_from.value,
        valid_until: form.elements.valid_until.value,
        title: form.elements.quiz_title.value.trim(), questions,
      }),
    });
    const result = await readApiJson(response);
    if (!response.ok) throw new Error(result.mesej || "Could not save the questions.");
    form.elements.quiz_title.value = result.title || form.elements.quiz_title.value.trim();
    status.textContent = "Validity dates, quiz title, and all 10 questions were saved."; status.classList.add("success");
  } catch (error) { status.textContent = error.message || "Could not connect to the server."; }
  finally { button.disabled = false; }
});

async function loadSaved() {
  try {
    const response = await fetch("/api/guru/questions", { cache: "no-store" });
    const result = await readApiJson(response);
    if (!result.available) return;
    form.elements.valid_from.value = result.valid_from || "";
    form.elements.valid_until.value = result.valid_until || "";
    form.elements.quiz_title.value = result.title || "Student quiz";
    const source = result.questions.map(q => `\\textbf{Question ${q.number}}\n\n${q.question_text}\n\n\\begin{enumerate}[label=\\Alph*.]\n${["A", "B", "C", "D"].map(letter => `  \\item ${q.options[letter]}`).join("\n")}\n\\end{enumerate}`).join("\n\n");
    form.elements.latex_source.value = source;
    form.elements.answer_key.value = result.questions.map(q => `${q.number}:${q.correct_answer}`).join(", ");
  } catch { /* No saved quiz yet. */ }
}
loadSaved();



