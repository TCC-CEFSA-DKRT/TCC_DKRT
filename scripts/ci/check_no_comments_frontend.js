const cp = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = "frontend/src";
const HUNK = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@/;
const TS_DIRECTIVE = /^(\/\/\s*(eslint-|@ts-|prettier-ignore)|\/\/\/\s*<reference|\/\*\s*(istanbul|eslint))/;
const SCSS_DIRECTIVE = /^(\/\/|\/\*)\s*(stylelint-|prettier-ignore)/;
const GUIDE = "Registre o contexto em docs/historico/<issue>.md (ver AGENTS.md) em vez de comentar no código.";

function git(...args) {
  return cp.execFileSync("git", ["--no-optional-locks", "-c", "core.quotepath=off", ...args], {
    encoding: "utf8",
    maxBuffer: 1 << 27,
  });
}

function parseArgs(argv) {
  const options = { base: "origin/main", head: "HEAD", staged: false };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--base") options.base = argv[++i];
    else if (argv[i] === "--head") options.head = argv[++i];
    else if (argv[i] === "--staged") options.staged = true;
  }
  return options;
}

function addedLines(options) {
  const common = ["diff", "-M", "-U0", "--no-color", "--diff-filter=ACMR"];
  const range = options.staged ? ["--cached"] : [`${options.base}...${options.head}`];
  const diff = git(...common, ...range, "--", ROOT);
  const result = new Map();
  let current = null;
  let inHeader = false;
  for (const line of diff.split("\n")) {
    if (line.startsWith("diff --git")) {
      inHeader = true;
      current = null;
    } else if (inHeader && line.startsWith("+++ ")) {
      const name = line.slice(4).split("\t")[0];
      current = name.startsWith("b/") && /\.(ts|html|scss)$/.test(name) ? name.slice(2) : null;
      if (current) result.set(current, new Set());
    } else if (line.startsWith("@@")) {
      inHeader = false;
      const match = HUNK.exec(line);
      if (match && current) {
        const start = Number(match[1]);
        const count = match[2] === undefined ? 1 : Number(match[2]);
        for (let i = 0; i < count; i++) result.get(current).add(start + i);
      }
    }
  }
  return result;
}

function loadTypescript() {
  const candidates = [
    path.join(process.cwd(), "frontend", "node_modules", "typescript"),
    path.join(process.cwd(), "node_modules", "typescript"),
    "typescript",
  ];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      continue;
    }
  }
  return null;
}

function tsComments(ts, name, source) {
  const sourceFile = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true);
  const found = new Map();
  const collect = (ranges) => {
    for (const range of ranges || []) if (!found.has(range.pos)) found.set(range.pos, range);
  };
  const walk = (node) => {
    if (node.kind >= ts.SyntaxKind.FirstJSDocNode && node.kind <= ts.SyntaxKind.LastJSDocNode) return;
    const children = node.getChildren(sourceFile);
    if (children.length) {
      children.forEach(walk);
      return;
    }
    collect(ts.getLeadingCommentRanges(source, node.getFullStart()));
    collect(ts.getTrailingCommentRanges(source, node.getEnd()));
  };
  walk(sourceFile);
  return [...found.values()]
    .map((range) => ({
      text: source.slice(range.pos, range.end),
      line: sourceFile.getLineAndCharacterOfPosition(range.pos).line + 1,
      endLine: sourceFile.getLineAndCharacterOfPosition(range.end).line + 1,
    }))
    .filter((comment) => !TS_DIRECTIVE.test(comment.text));
}

function htmlComments(source) {
  const result = [];
  for (const match of source.matchAll(/<!--[\s\S]*?-->/g)) {
    const before = (source.slice(0, match.index).match(/\n/g) || []).length;
    const inside = (match[0].match(/\n/g) || []).length;
    result.push({ text: match[0], line: before + 1, endLine: before + 1 + inside });
  }
  return result;
}

function scssComments(source) {
  const result = [];
  let line = 1;
  let i = 0;
  while (i < source.length) {
    const ch = source[i];
    const next = source[i + 1];
    if (ch === "\n") {
      line++;
      i++;
    } else if (ch === '"' || ch === "'") {
      i++;
      while (i < source.length && source[i] !== ch && source[i] !== "\n") {
        if (source[i] === "\\") i++;
        i++;
      }
      i++;
    } else if (source.startsWith("url(", i)) {
      const close = source.indexOf(")", i);
      const stop = close === -1 ? source.length : close;
      line += (source.slice(i, stop).match(/\n/g) || []).length;
      i = stop + 1;
    } else if (ch === "/" && next === "/") {
      let end = source.indexOf("\n", i);
      if (end === -1) end = source.length;
      result.push({ text: source.slice(i, end), line, endLine: line });
      i = end;
    } else if (ch === "/" && next === "*") {
      const close = source.indexOf("*/", i + 2);
      const end = close === -1 ? source.length : close + 2;
      const text = source.slice(i, end);
      const breaks = (text.match(/\n/g) || []).length;
      result.push({ text, line, endLine: line + breaks });
      line += breaks;
      i = end;
    } else {
      i++;
    }
  }
  return result.filter((comment) => !SCSS_DIRECTIVE.test(comment.text));
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const files = addedLines(options);
  let ts = null;
  let total = 0;
  for (const [file, added] of [...files.entries()].sort()) {
    if (added.size === 0) continue;
    const source = git("show", options.staged ? `:${file}` : `${options.head}:${file}`);
    let comments;
    if (file.endsWith(".ts")) {
      ts = ts || loadTypescript();
      if (!ts) {
        console.error("typescript não encontrado: rode npm ci em frontend/");
        process.exit(2);
      }
      comments = tsComments(ts, file, source);
    } else if (file.endsWith(".html")) {
      comments = htmlComments(source);
    } else {
      comments = scssComments(source);
    }
    for (const comment of comments) {
      let touched = false;
      for (let l = comment.line; l <= comment.endLine; l++) if (added.has(l)) touched = true;
      if (!touched) continue;
      total++;
      console.log(`${file}:${comment.line}: comentário novo -> ${comment.text.replace(/\s+/g, " ").slice(0, 70)}`);
    }
  }
  console.log(`[frontend] ${files.size} arquivo(s) alterado(s); ${total} comentário(s) novo(s)`);
  if (total) console.log(GUIDE);
  process.exit(total ? 1 : 0);
}

main();
