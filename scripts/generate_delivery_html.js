const fs = require("fs");

const input = "docs/entrega/pre_projeto_tcc.md";
const output = "docs/entrega/pre_projeto_tcc.html";

const escapeHtml = (value) =>
  value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const markdown = fs.readFileSync(input, "utf8");
const lines = markdown.split(/\r?\n/);
const html = [];
let inCode = false;
let codeLines = [];
let tableLines = [];

function flushCode() {
  if (!codeLines.length) return;
  html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
  codeLines = [];
}

function flushTable() {
  if (!tableLines.length) return;

  const rows = tableLines
    .filter((row) => !/^\|\s*-/.test(row))
    .map((row) =>
      row
        .trim()
        .replace(/^\|/, "")
        .replace(/\|$/, "")
        .split("|")
        .map((cell) => cell.trim()),
    );

  html.push("<table>");
  rows.forEach((row, rowIndex) => {
    const tag = rowIndex === 0 ? "th" : "td";
    html.push(`<tr>${row.map((cell) => `<${tag}>${escapeHtml(cell)}</${tag}>`).join("")}</tr>`);
  });
  html.push("</table>");
  tableLines = [];
}

for (const line of lines) {
  if (line.startsWith("```")) {
    if (inCode) {
      inCode = false;
      flushCode();
    } else {
      flushTable();
      inCode = true;
    }
    continue;
  }

  if (inCode) {
    codeLines.push(line);
    continue;
  }

  if (/^\|.*\|\s*$/.test(line)) {
    tableLines.push(line);
    continue;
  }

  flushTable();

  if (!line.trim()) {
    html.push("");
    continue;
  }

  const image = line.match(/^!\[([^\]]*)\]\(([^)]*)\)/);
  if (image) {
    html.push(
      `<figure><img src="${escapeHtml(image[2])}" alt="${escapeHtml(image[1])}"><figcaption>${escapeHtml(
        image[1],
      )}</figcaption></figure>`,
    );
    continue;
  }

  const heading = line.match(/^(#{1,6})\s+(.*)$/);
  if (heading) {
    const level = heading[1].length;
    html.push(`<h${level}>${escapeHtml(heading[2])}</h${level}>`);
    continue;
  }

  if (line.startsWith("- ")) {
    html.push(`<p class="bullet">&bull; ${escapeHtml(line.slice(2))}</p>`);
    continue;
  }

  if (/^\d+\.\s/.test(line)) {
    html.push(`<p class="bullet">${escapeHtml(line)}</p>`);
    continue;
  }

  html.push(`<p>${escapeHtml(line).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")}</p>`);
}

flushCode();
flushTable();

const css = `
body{font-family:Arial,Helvetica,sans-serif;line-height:1.45;color:#1f2937;margin:40px auto;max-width:980px;padding:0 24px}
h1,h2,h3{color:#111827;page-break-after:avoid}
h1{font-size:30px;text-align:center}
h2{border-bottom:1px solid #d1d5db;padding-bottom:6px;margin-top:34px}
table{border-collapse:collapse;width:100%;margin:14px 0;font-size:13px}
th,td{border:1px solid #d1d5db;padding:7px;vertical-align:top}
th{background:#f3f4f6}
pre{background:#111827;color:#f9fafb;padding:14px;overflow:auto;border-radius:6px}
code{font-family:Consolas,monospace}
figure{margin:22px 0;text-align:center;page-break-inside:avoid}
img{max-width:100%;border:1px solid #d1d5db;border-radius:4px}
figcaption{font-size:12px;color:#4b5563;margin-top:6px}
.bullet{margin:4px 0 4px 20px}
@media print{body{margin:18mm;max-width:none;padding:0}pre,figure,table{break-inside:avoid}}
`;

const document = `<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <title>Pre-projeto TCC</title>
  <style>${css}</style>
</head>
<body>
${html.join("\n")}
</body>
</html>
`;

fs.writeFileSync(output, document, "utf8");
console.log(output);
