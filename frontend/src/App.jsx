import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Tree } from "react-arborist";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal } from "@xterm/xterm";
import * as AlertDialog from "@radix-ui/react-alert-dialog";
import * as ContextMenu from "@radix-ui/react-context-menu";
import "@xterm/xterm/css/xterm.css";
import {
  Activity,
  ArrowDownToLine,
  ArrowUpToLine,
  CaseSensitive,
  Check,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  ClipboardPaste,
  Clock3,
  Copy,
  CircleX,
  File,
  FileCheck2,
  FileCode2,
  FilePenLine,
  Files,
  Folder,
  FolderOpen,
  FolderPlus,
  Link,
  ListChecks,
  Moon,
  Minus,
  PanelLeftClose,
  PanelLeftOpen,
  Pencil,
  Play,
  Power,
  Plus,
  Regex,
  Scissors,
  Search,
  Send,
  Settings2,
  Star,
  Sun,
  TerminalSquare,
  Trash2,
  TriangleAlert,
  WholeWord,
  X,
} from "lucide-react";
import { api } from "./api";
import { CopyValue, TaskListValue, writeClipboard } from "./CopyValue";
import { InspectionItems } from "./RunInspection";
import { TerminalOutputAge } from "./TerminalOutputAge";
import { Hint } from "./Tooltip";

const Editor = lazy(() =>
  import("./MonacoEditors.jsx").then((module) => ({ default: module.MonacoEditor })),
);
const DiffEditor = lazy(() =>
  import("./MonacoEditors.jsx").then((module) => ({ default: module.MonacoDiffEditor })),
);

const finalStates = new Set(["succeeded", "failed", "cancelled", "lost"]);
const coreLabels = {
  queued: "队列中",
  starting: "启动中",
  running: "运行中",
  stopping: "退出中",
  succeeded: "已完成",
  failed: "执行错误",
  cancelled: "已停止",
  lost: "状态丢失",
};
const showTime = (value) =>
  value
    ? new Intl.DateTimeFormat("zh-CN", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }).format(new Date(value))
    : "—";
const taskLabel = (task) =>
  task.status?.label || coreLabels[task.state] || task.state;
const taskTone = (task) =>
  task.status?.tone ||
  (task.state === "succeeded"
    ? "success"
    : ["failed", "lost"].includes(task.state)
      ? "danger"
      : "neutral");
const escapeRegularExpression = (value) =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
function countTerminalMatches(term, query, options) {
  if (!term || !query) return { count: 0, invalid: false };
  try {
    const source = options.regex ? query : escapeRegularExpression(query);
    const expression = new RegExp(source, `g${options.caseSensitive ? "" : "i"}`);
    let count = 0;
    for (let index = 0; index < term.buffer.active.length; index += 1) {
      const line = term.buffer.active.getLine(index)?.translateToString() || "";
      for (const match of line.matchAll(expression)) {
        if (
          !options.wholeWord ||
          ((!match.index || /\W/.test(line[match.index - 1])) &&
            (match.index + match[0].length === line.length ||
              /\W/.test(line[match.index + match[0].length])))
        )
          count += 1;
        if (!match[0]) expression.lastIndex += 1;
      }
    }
    return { count, invalid: false };
  } catch {
    return { count: 0, invalid: true };
  }
}
const QUEUE_FOLD_THRESHOLD = 20;
const tagKey = (task) => [...(task.labels || [])].sort().join("\u001f");
const compactQueued = (tasks) => {
  const rows = new Map();
  for (const task of tasks) {
    const key = `${tagKey(task)}\u001e${task.name}`;
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { task, count: 1 });
  }
  return [...rows.values()];
};

function useTheme() {
  const [theme, setTheme] = useState(
    document.documentElement.dataset.theme === "dark" ? "dark" : "light",
  );
  const apply = (next) => {
    document.documentElement.dataset.theme = next;
    document.documentElement.dataset.themeGuard = next;
    localStorage.setItem("localflow-theme", next);
    setTheme(next);
  };
  return [theme, apply];
}

function useUiRevision(paused = false) {
  const revision = useRef();
  useEffect(() => {
    if (paused) return undefined;
    let active = true;
    const check = async () => {
      try {
        const current = (await api.uiRevision()).revision;
        if (!active) return;
        if (revision.current && revision.current !== current) location.reload();
        revision.current = current;
      } catch {
        /* the service may still be starting */
      }
    };
    check();
    const timer = setInterval(check, 2000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [paused]);
}

function TaskTerminal({ task, interactive, theme, onStreamStatus }) {
  const windowBytes = 4 * 1024 * 1024;
  // A raw-byte window can contain far more than xterm's bounded number of
  // visual rows when lines wrap.  Keep a search hit in a deliberately smaller
  // neighbourhood so the matching line survives terminal scrollback.
  const archiveHitWindowBytes = 256 * 1024;
  const tailWindowStart = (size) =>
    Math.max(0, Number(size || 0) - windowBytes);
  const host = useRef();
  const finder = useRef();
  const searchInput = useRef();
  const terminal = useRef();
  const contextSelection = useRef("");
  const [selectedText, setSelectedText] = useState("");
  const [searching, setSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [searchOptions, setSearchOptions] = useState({
    caseSensitive: false,
    wholeWord: false,
    regex: false,
  });
  const [searchResult, setSearchResult] = useState({
    resultIndex: -1,
    resultCount: 0,
    invalid: false,
  });
  // A terminal is keyed by task id below.  Derive its first window synchronously:
  // an effect that corrects an initial zero offset would already have opened a
  // WebSocket and visibly replayed the complete archive before reaching this tail.
  const [rangeStart, setRangeStart] = useState(() =>
    tailWindowStart(task.log_size),
  );
  const [rangeBytes, setRangeBytes] = useState(windowBytes);
  const [hydrated, setHydrated] = useState(false);
  const [archiveResults, setArchiveResults] = useState([]);
  const [archiveTruncated, setArchiveTruncated] = useState(false);
  const [archiveSearching, setArchiveSearching] = useState(false);
  const [archiveSearchError, setArchiveSearchError] = useState("");
  const [followingLatest, setFollowingLatest] = useState(true);
  const pendingArchiveHit = useRef();
  const archiveRequest = useRef(0);
  useEffect(() => {
    setArchiveResults([]);
    setArchiveSearchError("");
    setSelectedText("");
    contextSelection.current = "";
  }, []);
  const copyTerminalSelection = async (text = selectedText) => {
    if (!text) return;
    await writeClipboard(text);
  };
  const closeSearch = useCallback(() => {
    archiveRequest.current += 1;
    setSearching(false);
    setArchiveResults([]);
    setArchiveTruncated(false);
    setArchiveSearchError("");
    finder.current?.clearDecorations();
    setSearchResult({ resultIndex: -1, resultCount: 0, invalid: false });
    // A find dialog must return keyboard ownership to its terminal.  Without
    // this, Ctrl+F immediately after Escape/close is handled by the browser
    // instead of reopening the terminal finder.
    requestAnimationFrame(() => terminal.current?.focus());
  }, []);
  const searchArchive = async () => {
    if (!query) return;
    const request = ++archiveRequest.current;
    setArchiveSearching(true);
    setArchiveSearchError("");
    try {
      const result = await api.searchLog(task.id, query, searchOptions);
      if (request !== archiveRequest.current) return;
      setArchiveResults(result.items);
      setArchiveTruncated(result.truncated);
    } catch (error) {
      if (request !== archiveRequest.current) return;
      setArchiveResults([]);
      setArchiveTruncated(false);
      setArchiveSearchError(error.message || "检索失败");
    } finally {
      if (request === archiveRequest.current) setArchiveSearching(false);
    }
  };
  const browseRange = (nextStart) => {
    pendingArchiveHit.current = undefined;
    setFollowingLatest(false);
    setRangeBytes(windowBytes);
    setRangeStart(Math.max(0, nextStart));
  };
  const openArchiveHit = (item) => {
    pendingArchiveHit.current = {
      query,
      options: searchOptions,
      offset: item.offset,
    };
    setFollowingLatest(false);
    setRangeBytes(archiveHitWindowBytes);
    setRangeStart(Math.max(0, item.offset - 8192));
    closeSearch();
  };
  const returnToLatest = () => {
    pendingArchiveHit.current = undefined;
    setFollowingLatest(true);
    setRangeBytes(windowBytes);
    setRangeStart(tailWindowStart(task.log_size));
  };
  const search = (direction = "next", incremental = false, options = searchOptions) => {
    if (!query || !finder.current) return;
    const summary = countTerminalMatches(terminal.current, query, options);
    if (summary.invalid) {
      setSearchResult({ resultIndex: -1, resultCount: 0, invalid: true });
      return;
    }
    const method = direction === "previous" ? "findPrevious" : "findNext";
    finder.current[method](query, {
      ...options,
      incremental,
    });
    setSearchResult((current) => ({
      resultCount: summary.count,
      invalid: false,
      resultIndex:
        summary.count === 0
          ? -1
          : incremental
            ? direction === "previous"
              ? summary.count - 1
              : 0
            : direction === "previous"
              ? (current.resultIndex - 1 + summary.count) % summary.count
              : (current.resultIndex + 1) % summary.count,
    }));
  };
  const toggleSearchOption = (name) => {
    const next = { ...searchOptions, [name]: !searchOptions[name] };
    setSearchOptions(next);
    search("next", false, next);
  };
  useEffect(() => {
    archiveRequest.current += 1;
    setArchiveResults([]);
    setArchiveTruncated(false);
    setArchiveSearchError("");
    if (searching && query) search("next", true);
    else if (!query) {
      finder.current?.clearDecorations();
      setSearchResult({ resultIndex: -1, resultCount: 0, invalid: false });
    }
  }, [query, searching, searchOptions.caseSensitive, searchOptions.wholeWord, searchOptions.regex]);
  useEffect(() => {
    if (!searching) return undefined;
    const frame = requestAnimationFrame(() => searchInput.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [searching]);
  useEffect(() => {
    const element = host.current;
    setHydrated(false);
    const dark = theme === "dark";
    const term = new Terminal({
      convertEol: true,
      cursorBlink: interactive,
      fontSize: 13,
      fontFamily: "Cascadia Mono, ui-monospace, monospace",
      scrollback: 5000,
      theme: dark
        ? { background: "#111418", foreground: "#e5e7eb" }
        : { background: "#fbfcfd", foreground: "#24292f" },
    });
    const fit = new FitAddon();
    const search = new SearchAddon();
    term.loadAddon(fit);
    term.loadAddon(search);
    term.loadAddon(
      new WebLinksAddon((event, uri) => {
        if (event.ctrlKey || event.metaKey)
          window.open(uri, "_blank", "noopener,noreferrer");
      }),
    );
    term.open(element);
    finder.current = search;
    terminal.current = term;
    const selectionListener = term.onSelectionChange(() => {
      const selection = term.getSelection();
      setSelectedText(selection);
      if (selection) contextSelection.current = selection;
    });
    term.attachCustomKeyEventHandler((event) => {
      const modifier = event.ctrlKey || event.metaKey;
      if (
        event.type === "keydown" &&
        modifier &&
        event.key.toLowerCase() === "c" &&
        term.hasSelection()
      ) {
        void copyTerminalSelection(term.getSelection());
        return false;
      }
      if (
        event.type === "keydown" &&
        modifier &&
        event.key.toLowerCase() === "f"
      ) {
        setSearching(true);
        return false;
      }
      return true;
    });
    let frame;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (element.clientWidth && element.clientHeight) fit.fit();
      });
    });
    observer.observe(element);
    fit.fit();
    element.dataset.rows = String(term.rows);
    element.dataset.columns = String(term.cols);
    const protocol = location.protocol === "https:" ? "wss" : "ws";
    const endOffset = Math.min(
      Number(task.log_size || 0),
      rangeStart + rangeBytes,
    );
    // A live terminal follows its tail only until the operator intentionally
    // visits an earlier range or a full-archive hit.  Historical browsing must
    // freeze an end offset; otherwise a live WebSocket silently catches up to
    // newest output and defeats the chosen reading position.
    const end = interactive && followingLatest ? "" : `&end=${endOffset}`;
    const socket = new WebSocket(
      `${protocol}://${location.host}/api/v1/tasks/${task.id}/terminal?offset=${rangeStart}${end}`,
    );
    let caughtUp = false;
    let revealFrame;
    onStreamStatus?.({ taskId: task.id, caughtUp: false, updatedAt: null });
    socket.onopen = () => {
      element.dataset.connection = "open";
    };
    socket.onmessage = (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "output") {
        const bytes = Uint8Array.from(atob(message.data), (value) =>
          value.charCodeAt(0),
        );
        term.write(bytes, () => {
          onStreamStatus?.({
            taskId: task.id,
            caughtUp,
            updatedAt: message.log_updated_at || null,
          });
          if (socket.readyState === WebSocket.OPEN)
            socket.send(
              JSON.stringify({ type: "ack", offset: message.offset }),
            );
        });
      } else if (message.type === "caught_up") {
        caughtUp = true;
        // xterm can retain the viewport at the first replayed row even while it
        // is hidden.  Anchor before revealing it so an opened terminal always
        // starts at the newest available output instead of visibly scrolling
        // through its archive.
        const archiveHit = pendingArchiveHit.current;
        if (archiveHit) {
          pendingArchiveHit.current = undefined;
          term.scrollToTop();
          // The target begins within an 8 KiB context before the server offset;
          // use xterm's mature Search addon to put the matching row in view.
          search.findNext(archiveHit.query, archiveHit.options);
        } else if (followingLatest) term.scrollToBottom();
        else term.scrollToTop();
        cancelAnimationFrame(revealFrame);
        revealFrame = requestAnimationFrame(() => {
          if (!element.isConnected) return;
          // Commit the caught-up metadata with visibility.  Otherwise React can
          // show an old-output age in the single frame where the terminal is
          // still intentionally hidden during replay.
          setHydrated(true);
          onStreamStatus?.({
            taskId: task.id,
            caughtUp: true,
            updatedAt: message.log_updated_at || null,
          });
        });
      }
    };
    socket.onclose = () => {
      if (element.isConnected) {
        element.dataset.connection = "closed";
      }
    };
    term.onData((data) => {
      if (interactive && socket.readyState === WebSocket.OPEN)
        socket.send(
          JSON.stringify({
            type: "input",
            data: btoa(unescape(encodeURIComponent(data))),
          }),
        );
    });
    term.onResize(({ rows, cols }) => {
      element.dataset.rows = String(rows);
      element.dataset.columns = String(cols);
      if (interactive && socket.readyState === WebSocket.OPEN)
        socket.send(JSON.stringify({ type: "resize", rows, cols }));
    });
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
      cancelAnimationFrame(revealFrame);
      socket.onopen = null;
      socket.onmessage = null;
      socket.onclose = null;
      socket.close();
      selectionListener.dispose();
      finder.current = undefined;
      terminal.current = undefined;
      term.dispose();
    };
  }, [task.id, interactive, theme, rangeStart, rangeBytes, followingLatest, onStreamStatus]);
  const rangeEnd = Math.min(Number(task.log_size || 0), rangeStart + rangeBytes);
  return (
    <div className="terminal-shell">
      <div className="terminal-tools">
        {searching && (
          <div className="terminal-find" role="search">
            <input
              ref={searchInput}
              autoFocus
              aria-label="终端搜索"
              placeholder="查找"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter")
                  search(event.shiftKey ? "previous" : "next");
                if (event.key === "Escape") closeSearch();
              }}
            />
            <output aria-live="polite">
              {query
                ? searchResult.invalid
                  ? "表达式有误"
                  : searchResult.resultCount
                  ? `${searchResult.resultIndex + 1}/${searchResult.resultCount}`
                  : "无结果"
                : ""}
            </output>
            {[
              ["caseSensitive", CaseSensitive, "区分大小写"],
              ["wholeWord", WholeWord, "全词匹配"],
              ["regex", Regex, "使用正则表达式"],
            ].map(([name, Icon, label]) => (
              <Hint label={label} key={name}>
                <button
                  className="icon"
                  aria-label={label}
                  aria-pressed={searchOptions[name]}
                  onClick={() => toggleSearchOption(name)}
                >
                  <Icon />
                </button>
              </Hint>
            ))}
            <Hint label="上一个匹配">
              <button
                className="icon"
                aria-label="上一个匹配"
                disabled={!query}
                onClick={() => search("previous")}
              >
                <ChevronUp />
              </button>
            </Hint>
            <Hint label="下一个匹配">
              <button
                className="icon"
                aria-label="下一个匹配"
                disabled={!query}
                onClick={() => search("next")}
              >
                <ChevronDown />
              </button>
            </Hint>
            <button
              className="icon"
              aria-label="关闭查找"
              onClick={closeSearch}
            >
              <X />
            </button>
            <button
              className="terminal-archive-search"
              disabled={!query || archiveSearching}
              onClick={searchArchive}
            >
              {archiveSearching ? "检索中" : "检索全部日志"}
            </button>
          </div>
        )}
        {Number(task.log_size || 0) > windowBytes && (
          <div
            className="terminal-range"
            aria-label={followingLatest ? "最新终端日志窗口" : "终端历史日志窗口"}
          >
            <button
              disabled={rangeStart === 0}
              onClick={() => browseRange(rangeStart - windowBytes)}
            >
              上一段
            </button>
            <span>{rangeStart.toLocaleString()}–{rangeEnd.toLocaleString()} 字节</span>
            <button
              disabled={rangeEnd >= Number(task.log_size || 0)}
              onClick={() => browseRange(rangeEnd)}
            >
              下一段
            </button>
            {!followingLatest && interactive && (
              <button onClick={returnToLatest}>最新输出</button>
            )}
          </div>
        )}
        <Hint label="跳到终端开头">
          <button
            className="icon"
            aria-label="跳到终端开头"
            onClick={() => terminal.current?.scrollToTop()}
          >
            <ArrowUpToLine />
          </button>
        </Hint>
        <Hint label="跳到终端末尾">
          <button
            className="icon"
            aria-label="跳到终端末尾"
            onClick={() => terminal.current?.scrollToBottom()}
          >
            <ArrowDownToLine />
          </button>
        </Hint>
        <button
          className="icon"
          aria-label="在终端中查找"
          aria-pressed={searching}
          onClick={() => (searching ? closeSearch() : setSearching(true))}
        >
          <Search />
        </button>
      </div>
      {archiveResults.length > 0 && searching && (
        <section className="terminal-search-results" aria-label="全部日志检索结果">
          <header>
            <span><b>全部日志</b><small>{archiveResults.length} 个匹配{archiveTruncated ? "，仅显示前 200 个" : ""}</small></span>
            <button className="icon" aria-label="关闭全部日志结果" onClick={closeSearch}><X /></button>
          </header>
          <ol>
            {archiveResults.map((item) => (
              <li key={`${item.offset}-${item.line}`}>
                <button onClick={() => openArchiveHit(item)}>
                  <span className="terminal-search-result-meta">第 {item.line} 行 · {item.offset.toLocaleString()} 字节</span>
                  <code>{item.preview}</code>
                </button>
              </li>
            ))}
          </ol>
        </section>
      )}
      {archiveSearchError && (
        <div className="terminal-search-error" role="alert">{archiveSearchError}</div>
      )}
      <ContextMenu.Root
        onOpenChange={(open) => {
          if (open) {
            const selection = terminal.current?.getSelection() || "";
            if (selection) contextSelection.current = selection;
            setSelectedText(selection || contextSelection.current);
          }
        }}
      >
        <ContextMenu.Trigger asChild>
          <div
            className={`terminal ${hydrated ? "hydrated" : "hydrating"}`}
            ref={host}
            onContextMenuCapture={() => {
              const selection = terminal.current?.getSelection() || "";
              contextSelection.current = selection;
              setSelectedText(selection);
            }}
          />
        </ContextMenu.Trigger>
        <ContextMenu.Portal>
          <ContextMenu.Content className="terminal-context-menu" collisionPadding={8}>
            <ContextMenu.Item
              className="terminal-context-menu-item"
              disabled={!selectedText}
              onSelect={() => copyTerminalSelection(contextSelection.current)}
            >
              复制
              <span>Ctrl+C</span>
            </ContextMenu.Item>
          </ContextMenu.Content>
        </ContextMenu.Portal>
      </ContextMenu.Root>
    </div>
  );
}

function TaskDetail({ task, role, interrupt }) {
  const hidden = new Set(["source", "variable_sources"]);
  if (task.template === "verification") {
    hidden.add("seed");
    hidden.add("运行日志");
  }
  const custom = Object.entries(task.custom || {}).filter(
    ([key, value]) =>
      !hidden.has(key) &&
      !key.startsWith("_") &&
      value != null &&
      value !== "" &&
      (!Array.isArray(value) || value.length),
  );
  const stopLabel = task.state === "stopping" ? "加快退出" : "中止";
  return (
    <div className="detail">
      <div className="details">
        <div className="detail-time">
          <span>开始时间</span>
          <time dateTime={task.started_at || undefined} title={task.started_at || undefined}>
            {showTime(task.started_at)}
          </time>
        </div>
        {(task.display_command || task.command) && (
          <CopyValue label="命令" value={task.display_command || task.command.join(" ")} />
        )}
        {!!(task.source_invocations?.length || task.source_files?.length) && (
          <TaskListValue
            label="加载环境"
            values={task.source_invocations?.length ? task.source_invocations : task.source_files}
          />
        )}
        <CopyValue label="工作目录" value={task.working_directory} />
        <CopyValue label="终端输出" value={task.log_path} />
        {custom.flatMap(([key, value]) =>
          key === "自定义文本" && Array.isArray(value)
            ? value.map((line, index) => (
                <CopyValue
                  customText
                  value={line}
                  key={`${key}-${index}`}
                />
              ))
            : Array.isArray(value)
              ? [<TaskListValue label={key} values={value} key={key} />]
              : [
                <CopyValue
                  label={key === "seed" ? "随机种子" : key}
                  value={value}
                  key={key}
                />,
                ],
        )}
      </div>
      {role === "admin" && !finalStates.has(task.state) && (
        <Hint label={stopLabel}>
          <button
            className="stop-action"
            aria-label={task.state === "stopping" ? "加快退出任务" : "中止任务"}
            onClick={interrupt}
          >
            <X strokeWidth={2} />
          </button>
        </Hint>
      )}
    </div>
  );
}

function TaskItem({
  task,
  count = 1,
  open,
  fresh,
  role,
  toggle,
  ack,
  interrupt,
}) {
  const tone = taskTone(task);
  const timeKind = task.ended_at ? "结束" : "开始";
  return (
    <article className={`task-item ${open ? "open" : ""}`}>
      <button
        className={`task-row ${fresh ? "has-fresh" : ""}`}
        aria-expanded={open}
        onClick={toggle}
        onMouseEnter={() => fresh && ack()}
      >
        {fresh && <i className="fresh-dot" aria-label="新完成" />}
        <span className="task-name">
          <b>{task.name}</b>
          {task.labels?.length > 0 && (
            <small>
              {task.labels.map((item) => (
                <em key={item}>{item}</em>
              ))}
            </small>
          )}
          {count > 1 && (
            <strong
              className="queue-multiple"
              aria-label={`${count} 个相同任务`}
            >
              ×{count}
            </strong>
          )}
        </span>
        <span className={`status tone-${tone}`}>{taskLabel(task)}</span>
        <time aria-label={`${timeKind}时间`}>
          {showTime(task.ended_at || task.started_at || task.created_at)}
        </time>
        <ChevronDown />
      </button>
      {open && <TaskDetail task={task} role={role} interrupt={interrupt} />}
    </article>
  );
}

function QueueTasks({ tasks, renderTask }) {
  const [expanded, setExpanded] = useState(new Set());
  if (tasks.length <= QUEUE_FOLD_THRESHOLD)
    return compactQueued(tasks).map(({ task, count }) =>
      renderTask(task, count),
    );
  const buckets = new Map();
  for (const task of tasks) {
    const key = tagKey(task);
    const bucket = buckets.get(key);
    if (bucket) bucket.tasks.push(task);
    else
      buckets.set(key, {
        key,
        labels: [...(task.labels || [])].sort(),
        tasks: [task],
      });
  }
  return [...buckets.values()].flatMap((bucket) => {
    if (!bucket.key || bucket.tasks.length < 2)
      return compactQueued(bucket.tasks).map(({ task, count }) =>
        renderTask(task, count),
      );
    const open = expanded.has(bucket.key);
    return (
      <section
        className={`queue-cluster ${open ? "open" : ""}`}
        key={`queue:${bucket.key}`}
      >
        <button
          className="queue-cluster-row"
          aria-expanded={open}
          onClick={() =>
            setExpanded((old) => {
              const next = new Set(old);
              if (next.has(bucket.key)) next.delete(bucket.key);
              else next.add(bucket.key);
              return next;
            })
          }
        >
          <span>
            {bucket.labels.map((label) => (
              <em key={label}>{label}</em>
            ))}
          </span>
          <strong>×{bucket.tasks.length}</strong>
          <ChevronDown />
        </button>
        {open && (
          <div className="queue-cluster-items">
            {compactQueued(bucket.tasks).map(({ task, count }) =>
              renderTask(task, count),
            )}
          </div>
        )}
      </section>
    );
  });
}

function TerminalPage({ tasks, role, theme }) {
  const newestFirst = (left, right) =>
    Date.parse(right.ended_at || right.started_at || right.created_at || 0) -
    Date.parse(left.ended_at || left.started_at || left.created_at || 0);
  const active = tasks
    .filter((task) => ["starting", "running", "stopping"].includes(task.state))
    .sort(newestFirst);
  const history = tasks
    .filter((task) => finalStates.has(task.state))
    .sort(newestFirst);
  const available = [...active, ...history];
  const [selectedId, setSelectedId] = useState();
  const manualSelection = useRef(false);
  const observedLogSizes = useRef(new Map());
  const [unreadIds, setUnreadIds] = useState(new Set());
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState("");
  const [streamStatus, setStreamStatus] = useState({
    taskId: null,
    caughtUp: false,
    updatedAt: null,
  });
  const updateStreamStatus = useCallback((next) => setStreamStatus(next), []);
  useEffect(() => {
    setStreamStatus({ taskId: selectedId || null, caughtUp: false, updatedAt: null });
  }, [selectedId]);
  useEffect(() => {
    if (!available.some((task) => task.id === selectedId)) {
      manualSelection.current = false;
      setSelectedId(active[0]?.id || available[0]?.id);
    } else if (!manualSelection.current && active.length) {
      setSelectedId(active[0].id);
    }
  }, [tasks, selectedId]);
  useEffect(() => {
    const present = new Set(available.map((task) => task.id));
    setUnreadIds((previous) => {
      const next = new Set(previous);
      for (const id of next) if (!present.has(id)) next.delete(id);
      for (const task of available) {
        const size = Number(task.log_size || 0);
        const oldSize = observedLogSizes.current.get(task.id);
        if (oldSize !== undefined && size > oldSize && task.id !== selectedId)
          next.add(task.id);
        if (task.id === selectedId) next.delete(task.id);
        observedLogSizes.current.set(task.id, size);
      }
      if (
        next.size === previous.size &&
        [...next].every((id) => previous.has(id))
      )
        return previous;
      return next;
    });
    for (const id of observedLogSizes.current.keys())
      if (!present.has(id)) observedLogSizes.current.delete(id);
  }, [tasks, selectedId]);
  const selected = available.find((task) => task.id === selectedId);
  const selectedIsActive = Boolean(
    selected && ["starting", "running", "stopping"].includes(selected.state),
  );
  const selectedStreamCaughtUp =
    streamStatus.taskId === selected?.id && streamStatus.caughtUp;
  const selectedOutputUpdatedAt =
    streamStatus.taskId === selected?.id && streamStatus.updatedAt
      ? streamStatus.updatedAt
      : selected?.log_updated_at;
  const interactive =
    role === "admin" && selected && !finalStates.has(selected.state);
  const send = async () => {
    if (!selected || !input) return;
    try {
      await api.terminalInput(selected.id, `${input}\n`);
      setInput("");
      setNotice("已发送");
    } catch (error) {
      setNotice(error.message);
    }
  };
  const control = async (key) => {
    try {
      await api.terminalControl(selected.id, key);
      setNotice(`${key === "ctrl_c" ? "Ctrl+C" : "Ctrl+D"} 已发送`);
    } catch (error) {
      setNotice(error.message);
    }
  };
  const selectTerminal = (task) => {
    manualSelection.current = true;
    setSelectedId(task.id);
    observedLogSizes.current.set(task.id, Number(task.log_size || 0));
    setUnreadIds((previous) => {
      if (!previous.has(task.id)) return previous;
      const next = new Set(previous);
      next.delete(task.id);
      return next;
    });
  };
  const renderTerminal = (task) => {
    const unread = unreadIds.has(task.id);
    const tone = taskTone(task);
    return (
      <button
        className={`terminal-entry state-${task.state} tone-${tone} ${task.id === selectedId ? "active" : ""} ${unread ? "has-unread" : ""}`}
        data-terminal-state={task.state}
        data-unread={unread || undefined}
        key={task.id}
        onClick={() => selectTerminal(task)}
      >
        <span className="terminal-entry-text">
          <span className="terminal-entry-heading">
            <b className="terminal-entry-name">{task.name}</b>
          </span>
          <span className="terminal-entry-meta">
            {task.labels?.map((label) => (
              <em className="terminal-entry-label" key={label} title={label}>
                {label}
              </em>
            ))}
          </span>
        </span>
        {unread && (
          <i
            className="terminal-unread"
            aria-label="有新终端输出"
            title="有新终端输出"
          />
        )}
      </button>
    );
  };
  return (
    <div className="terminal-page">
      <aside aria-label="终端列表">
        {active.length > 0 && (
          <div className="terminal-entry-group" data-terminal-group="active">
            <header>
              <span>运行中</span>
              <small>{active.length}</small>
            </header>
            {active.map(renderTerminal)}
          </div>
        )}
        {history.length > 0 && (
          <div className="terminal-entry-group" data-terminal-group="history">
            <header>
              <span>历史</span>
              <small>{history.length}</small>
            </header>
            {history.map(renderTerminal)}
          </div>
        )}
        {available.length === 0 && <p>没有可交互的任务</p>}
      </aside>
      <section>
        {selected ? (
          <>
            <header>
              <div className="terminal-selection-context">
                <TerminalSquare />
                <span className="terminal-selection-copy">
                  <b>{selected.name}</b>
                  {selectedIsActive &&
                    selectedStreamCaughtUp &&
                    Number(selected.log_size || 0) > 0 && (
                    <TerminalOutputAge
                      updatedAt={selectedOutputUpdatedAt}
                      title={`最后输出：${showTime(selectedOutputUpdatedAt)}`}
                    />
                  )}
                </span>
              </div>
              {interactive ? (
                <div className="terminal-actions">
                  <button
                    className="terminal-key"
                    onClick={() => control("ctrl_c")}
                  >
                    Ctrl+C
                  </button>
                  <button
                    className="terminal-key"
                    onClick={() => control("ctrl_d")}
                  >
                    Ctrl+D
                  </button>
                  <span className="terminal-command">
                    <input
                      aria-label="发送终端指令"
                      placeholder="输入后按 Enter"
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => event.key === "Enter" && send()}
                    />
                    <button
                      aria-label="发送终端指令"
                      disabled={!input}
                      onClick={send}
                    >
                      <Send />
                    </button>
                  </span>
                </div>
              ) : null}
            </header>
            <span className="terminal-status" role="status">
              {notice}
            </span>
            <TaskTerminal
              key={selected.id}
              task={selected}
              interactive={interactive}
              theme={theme}
              onStreamStatus={updateStreamStatus}
            />
          </>
        ) : (
          <div className="tasks-empty">
            <TerminalSquare />
            <p>暂无可查看的终端</p>
          </div>
        )}
      </section>
    </div>
  );
}

const workspaceExtension = (name) =>
  name.match(/\.(?:ya?ml|json|toml|py|md)$/i)?.[0] || "";

function buildTree(entries, diagnostics, dirtyPaths = new Set()) {
  const nodes = new Map();
  const roots = [];
  const decoratedPaths = new Set(dirtyPaths);
  for (const path of dirtyPaths) {
    let parent = path;
    while (parent.includes("/")) {
      parent = parent.slice(0, parent.lastIndexOf("/"));
      decoratedPaths.add(parent);
    }
  }
  for (const entry of [...entries].sort(
    (a, b) =>
      a.path.split("/").length - b.path.split("/").length ||
      a.path.localeCompare(b.path),
  )) {
    const name = pathLeaf(entry.path);
    const node = {
      id: entry.kind === "directory" ? `folder:${entry.path}` : entry.path,
      name,
      path: entry.path,
      kind: entry.kind,
      symlink: entry.symlink,
      readonly: entry.readonly,
      diagnosis: diagnostics[entry.path],
      dirty: decoratedPaths.has(entry.path),
      ...(entry.kind === "directory" ? { children: [] } : {}),
    };
    nodes.set(entry.path, node);
    const parentPath = entry.path.includes("/")
      ? entry.path.slice(0, entry.path.lastIndexOf("/"))
      : "";
    const parent = nodes.get(parentPath);
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

function TreeNode({ node, style, dragHandle }) {
  const state = node.isInternal ? "folder" : "file";
  const Icon = node.data.symlink
    ? Link
    : node.isInternal
      ? node.isOpen
        ? FolderOpen
        : Folder
      : File;
  const label = node.isInternal ? "文件夹" : "配置文件";
  const displayName = node.data.name;
  const submit = (value) => {
    const clean = value.trim();
    const extension = node.isInternal ? "" : workspaceExtension(node.data.name);
    node.submit(
      node.isInternal
        ? clean
        : `${clean.slice(0, clean.length - workspaceExtension(clean).length)}${extension}`,
    );
  };
  return (
    <Hint label={node.data.symlink ? `${label} · 软链接` : label} side="right">
      <div
        data-file={node.id}
        data-config-state={state}
        aria-label={`${displayName}，${label}${node.data.dirty ? "，未保存" : ""}`}
        className={`tree-node state-${state} ${node.isSelected ? "selected" : ""}`}
        style={style}
        ref={dragHandle}
        onClick={(event) => {
          node.select();
          if (node.isInternal && event.detail === 1) node.toggle();
        }}
      >
        {node.isInternal ? (
          node.isOpen ? (
            <ChevronDown aria-hidden="true" />
          ) : (
            <ChevronRight aria-hidden="true" />
          )
        ) : (
          <span className="tree-spacer" />
        )}
        <Icon aria-hidden="true" />
        {node.isEditing ? (
          <input
            aria-label="名称"
            ref={node.editInputRef}
            defaultValue={displayName}
            onBlur={() => node.reset()}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                event.stopPropagation();
                submit(event.currentTarget.value);
              }
              if (event.key === "Escape") {
                event.preventDefault();
                event.stopPropagation();
                node.reset();
              }
            }}
          />
        ) : (
          <span className="tree-name">{displayName}</span>
        )}
        {node.data.dirty && (
          <span className="tree-dirty" aria-hidden="true" />
        )}
      </div>
    </Hint>
  );
}

function CasePicker({ field, filePath, values, discoverValues, setValues }) {
  const [options, setOptions] = useState([]);
  const [error, setError] = useState("");
  const [scope, setScope] = useState([]);
  const [drag, setDrag] = useState();
  const dragRef = useRef();
  const repeatRef = useRef();
  const grid = useRef();
  const countField = field.count_field;
  const defaultCountField = field.default_count_field;
  const included = new Set(values[field.name] || []);
  const runs = values[countField] || {};
  const defaultRuns = (defaultCountField && values[defaultCountField]) || 1;
  const scoped = new Set(scope);
  const discoveryInputKey = JSON.stringify(discoverValues);
  useEffect(() => {
    const discoveryInputs = JSON.parse(discoveryInputKey);
    const timer = setTimeout(
      () =>
        api
          .discoverConfig(filePath, discoveryInputs)
          .then((result) => {
            setOptions(result.items);
            setError("");
          })
          .catch((reason) => setError(reason.message)),
      250,
    );
    return () => clearTimeout(timer);
  }, [filePath, discoveryInputKey]);
  useEffect(() => {
    const clear = (event) => {
      if (grid.current && !grid.current.contains(event.target)) setScope([]);
    };
    document.addEventListener("pointerdown", clear, true);
    return () => document.removeEventListener("pointerdown", clear, true);
  }, []);
  const count = (name) =>
    included.has(name) ? Number(runs[name] ?? defaultRuns) : 0;
  const changeCounts = (names, resolve) =>
    setValues((current) => {
      const currentIncluded = new Set(current[field.name] || []);
      const nextRuns = { ...(current[countField] || {}) };
      const fallback = (defaultCountField && current[defaultCountField]) || 1;
      for (const name of names) {
        const old = currentIncluded.has(name)
          ? Number(nextRuns[name] ?? fallback)
          : 0;
        const next = Math.max(0, Number(resolve(old)) || 0);
        if (next) {
          currentIncluded.add(name);
          nextRuns[name] = next;
        } else {
          currentIncluded.delete(name);
          delete nextRuns[name];
        }
      }
      return {
        ...current,
        [field.name]: options.filter((name) => currentIncluded.has(name)),
        [countField]: nextRuns,
      };
    });
  const targets = (name) => (scoped.has(name) ? scope : [name]);
  const select = (event, name) => {
    if (event.ctrlKey || event.metaKey) {
      setScope((current) =>
        current.includes(name)
          ? current.filter((item) => item !== name)
          : [...current, name],
      );
      return;
    }
    setScope((current) =>
      current.length === 1 && current[0] === name ? [] : [name],
    );
  };
  useEffect(() => {
    const stop = () => stopRepeat();
    window.addEventListener("pointerup", stop, true);
    window.addEventListener("pointercancel", stop, true);
    window.addEventListener("blur", stop);
    return () => {
      stopRepeat();
      window.removeEventListener("pointerup", stop, true);
      window.removeEventListener("pointercancel", stop, true);
      window.removeEventListener("blur", stop);
    };
  }, []);
  const stopRepeat = () => {
    const active = repeatRef.current;
    clearTimeout(active?.timer);
    if (active?.target?.hasPointerCapture?.(active.pointerId))
      active.target.releasePointerCapture(active.pointerId);
    repeatRef.current = undefined;
  };
  const step = (name, delta) =>
    changeCounts(targets(name), (old) => old + delta);
  const beginRepeat = (event, name, delta) => {
    if (event.button !== 0) return;
    event.preventDefault();
    stopRepeat();
    const state = {
      pointerId: event.pointerId,
      target: event.currentTarget,
      timer: undefined,
      name,
      delta,
      applied: 0,
    };
    repeatRef.current = state;
    state.target.setPointerCapture?.(state.pointerId);
    const applyStep = () => {
      step(name, delta);
      state.applied += 1;
    };
    applyStep();
    const started = performance.now();
    const repeat = () => {
      if (repeatRef.current !== state) return;
      applyStep();
      const held = performance.now() - started;
      const delay = held > 2400 ? 65 : held > 1400 ? 105 : 170;
      state.timer = setTimeout(repeat, delay);
    };
    state.timer = setTimeout(repeat, 550);
  };
  const cancelIncrementForDrag = (name) => {
    const active = repeatRef.current;
    if (!active || active.name !== name || active.delta !== 1) return;
    const applied = active.applied;
    stopRepeat();
    if (applied) changeCounts(targets(name), (old) => old - applied);
  };
  const startMarquee = (event, kind) => {
    if (event.button !== 0 || event.target.closest(".case-count")) return;
    const root = event.currentTarget;
    const box = root.getBoundingClientRect();
    const startedCase = event.target.closest(".case-item")?.dataset.case;
    const origin = {
      pointerId: event.pointerId,
      x: event.clientX - box.left,
      y: event.clientY - box.top,
      startedOnItem: Boolean(startedCase),
      startedCase,
    };
    const matches = (pointer) =>
      kind === "mouse" || pointer.pointerId === origin.pointerId;
    const moveEvent = kind === "mouse" ? "mousemove" : "pointermove";
    const upEvent = kind === "mouse" ? "mouseup" : "pointerup";
    const cancelEvent = kind === "mouse" ? "mouseleave" : "pointercancel";
    const update = (pointer) => {
      if (!matches(pointer)) return;
      const currentBox = root.getBoundingClientRect();
      const x = pointer.clientX - currentBox.left;
      const y = pointer.clientY - currentBox.top;
      const next = {
        ...origin,
        left: Math.min(origin.x, x),
        top: Math.min(origin.y, y),
        width: Math.abs(x - origin.x),
        height: Math.abs(y - origin.y),
      };
      if (
        origin.startedCase &&
        !origin.incrementCancelled &&
        next.width + next.height > 8
      ) {
        origin.incrementCancelled = true;
        cancelIncrementForDrag(origin.startedCase);
      }
      dragRef.current = next;
      setDrag(next);
    };
    const cleanup = () => {
      window.removeEventListener(moveEvent, update);
      window.removeEventListener(upEvent, finish);
      window.removeEventListener(cancelEvent, cancel);
      dragRef.current = undefined;
      setDrag(undefined);
    };
    const finish = (pointer) => {
      if (!matches(pointer)) return;
      update(pointer);
      const current = dragRef.current;
      if (current && current.width + current.height > 8) {
        const currentBox = root.getBoundingClientRect();
        const selection = {
          left: currentBox.left + current.left,
          right: currentBox.left + current.left + current.width,
          top: currentBox.top + current.top,
          bottom: currentBox.top + current.top + current.height,
        };
        const hits = [...root.querySelectorAll(".case-item")]
          .filter((item) => {
            const itemBox = item.getBoundingClientRect();
            return (
              itemBox.left < selection.right &&
              itemBox.right > selection.left &&
              itemBox.top < selection.bottom &&
              itemBox.bottom > selection.top
            );
          })
          .map((item) => item.dataset.case);
        setScope(hits);
      } else if (!origin.startedOnItem) setScope([]);
      cleanup();
    };
    const cancel = (pointer) => {
      if (matches(pointer)) cleanup();
    };
    dragRef.current = {
      ...origin,
      left: origin.x,
      top: origin.y,
      width: 0,
      height: 0,
    };
    setDrag(dragRef.current);
    window.addEventListener(moveEvent, update);
    window.addEventListener(upEvent, finish);
    window.addEventListener(cancelEvent, cancel);
  };
  return (
    <fieldset className="case-picker">
      <legend>{field.label || "Case"}</legend>
      {error && <small className="error">{error}</small>}
      <div
        className="case-list"
        ref={grid}
        onPointerDown={(event) => startMarquee(event, "pointer")}
      >
        {options.map((name) => {
          const amount = count(name);
          const isScoped = scoped.has(name);
          const groupSize = isScoped ? scope.length : 1;
          return (
            <div
              className={`case-item ${amount ? "has-count" : ""} ${isScoped ? "scoped" : ""}`}
              data-case={name}
              key={name}
              onPointerDown={(event) => {
                if (
                  !event.ctrlKey &&
                  !event.metaKey &&
                  !event.target.closest(".case-step.decrease")
                )
                  beginRepeat(event, name, 1);
              }}
              onPointerUp={stopRepeat}
              onPointerCancel={stopRepeat}
              onLostPointerCapture={stopRepeat}
            >
              <button
                type="button"
                className="case-main"
                aria-pressed={isScoped}
                aria-label={`增加 ${name} 次数，当前 ${amount} 次${isScoped ? "，应用到已框选 Case" : ""}`}
                onClick={(event) => {
                  if (event.ctrlKey || event.metaKey) select(event, name);
                  else if (event.detail === 0) step(name, 1);
                }}
              >
                <span>{name}</span>
              </button>
              {amount > 0 && (
                <div className="case-count" role="group" aria-label={`${name} 运行次数`}>
                  <button
                    type="button"
                    className="case-step decrease"
                    aria-label={groupSize > 1 ? `减少所选 ${groupSize} 个 Case 次数` : `减少 ${name} 次数`}
                    onPointerDown={(event) => beginRepeat(event, name, -1)}
                    onPointerUp={stopRepeat}
                    onPointerCancel={stopRepeat}
                    onLostPointerCapture={stopRepeat}
                    onClick={(event) => event.detail === 0 && step(name, -1)}
                  >
                    <Minus />
                  </button>
                  <output aria-live="polite">{amount}</output>
                </div>
              )}
            </div>
          );
        })}
        {drag && (
          <i
            className="selection-box"
            style={{
              left: drag.left,
              top: drag.top,
              width: drag.width,
              height: drag.height,
            }}
          />
        )}
      </div>
    </fieldset>
  );
}

function pluginInputs(plugin, values) {
  const names = new Set();
  for (const field of plugin?.fields || []) {
    names.add(field.name);
    if (field.count_field) names.add(field.count_field);
    if (field.default_count_field) names.add(field.default_count_field);
  }
  return Object.fromEntries(
    [...names]
      .filter((name) => Object.prototype.hasOwnProperty.call(values, name))
      .map((name) => [name, values[name]]),
  );
}

function withoutCaseSelections(plugin, values) {
  const next = { ...(values || {}) };
  for (const field of plugin?.fields || []) {
    if (field.type !== "case-picker") continue;
    next[field.name] = [];
    if (field.count_field) next[field.count_field] = {};
  }
  return next;
}

function pathLeaf(value) {
  const parts = value.split("/");
  return parts[parts.length - 1];
}

function ConfigurationDebug({ preview }) {
  const diagnosis = preview?.run_diagnosis || preview?.diagnosis;
  const errors = diagnosis?.errors || [];
  const document = preview?.resolved_document || preview?.document;
  return (
    <section className="configuration-debug" aria-label="配置调试" role="region">
      <header>
        <TriangleAlert aria-hidden="true" />
        <div>
          <b>配置无效</b>
          <span>修复下列问题后即可运行</span>
        </div>
        <strong>{errors.length}</strong>
      </header>
      <div className="configuration-debug-body">
        <section className="configuration-issues" aria-label="配置问题">
          <h3>问题</h3>
          {errors.length ? (
            <ul>
              {errors.map((message, index) => {
                const separator = message.indexOf(":");
                return (
                  <li key={`${message}-${index}`}>
                    <CircleX aria-hidden="true" />
                    <code>{separator > 0 ? message.slice(0, separator) : "yaml"}</code>
                    <span>{separator > 0 ? message.slice(separator + 1).trim() : message}</span>
                  </li>
                );
              })}
            </ul>
          ) : <p>暂无可用诊断</p>}
        </section>
        <section className="configuration-resolution" aria-label="YAML 解析结果">
          <h3>YAML 解析结果</h3>
          {document && typeof document === "object" && !Array.isArray(document) ? (
            <dl>
              {Object.entries(document).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd><code>{typeof value === "string" ? value : JSON.stringify(value)}</code></dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>YAML 语法或导入尚未形成可解析的配置树。</p>
          )}
        </section>
      </div>
    </section>
  );
}

function RunFields({
  plugin,
  filePath,
  values,
  setValues,
  inspectionControllerRef,
}) {
  const [inspection, setInspection] = useState([]);
  const [inspectionError, setInspectionError] = useState("");
  const update = (field, raw) =>
    setValues({
      ...values,
      [field.name]:
        field.type === "integer"
          ? Number(raw)
          : field.type === "string-list"
            ? raw
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean)
            : raw,
    });
  const inputs = useMemo(() => pluginInputs(plugin, values), [plugin, values]);
  useEffect(() => {
    const controller = new AbortController();
    inspectionControllerRef.current = controller;
    let active = true;
    const timer = setTimeout(
      () =>
        api
          .inspectConfig(filePath, {}, controller.signal)
          .then((result) => {
            if (active) {
              setInspection(result.items);
              setInspectionError((result.errors || []).join("；"));
            }
          })
          .catch((error) => {
            if (active && error.name !== "AbortError")
              setInspectionError(error.message);
          }),
      120,
    );
    return () => {
      active = false;
      clearTimeout(timer);
      controller.abort();
      if (inspectionControllerRef.current === controller)
        inspectionControllerRef.current = undefined;
    };
  }, [filePath, inspectionControllerRef]);
  return (
    <div className="run-surface">
      <InspectionItems items={inspection} error={inspectionError} />
      <div className="run-fields">
        {plugin?.fields.map((field) =>
          field.type === "case-picker" ? (
            <CasePicker
              field={field}
              key={field.name}
              filePath={filePath}
              values={values}
              discoverValues={inputs}
              setValues={setValues}
            />
          ) : field.type === "json" ? (
            <details className="advanced-field" key={field.name}>
              <summary>
                运行参数
                <i />
              </summary>
              <label>
                <span>{field.label}</span>
                <textarea
                  value={
                    typeof values[field.name] === "string"
                      ? values[field.name]
                      : JSON.stringify(values[field.name] || {}, null, 2)
                  }
                  onChange={(event) => update(field, event.target.value)}
                />
              </label>
            </details>
          ) : (
            <label className={`run-field field-${field.type}`} key={field.name}>
              <span>{field.label || field.name}</span>
              <input
                required={field.required}
                inputMode={
                  ["integer", "seed"].includes(field.type)
                    ? "numeric"
                    : undefined
                }
                type={field.type === "integer" ? "number" : "text"}
                value={
                  Array.isArray(values[field.name])
                    ? values[field.name].join(", ")
                    : (values[field.name] ?? field.default ?? "")
                }
                onChange={(event) => update(field, event.target.value)}
              />
              {field.type === "string-list" && <small>用逗号分隔</small>}
            </label>
          ),
        )}
      </div>
    </div>
  );
}

function readConfigMemory() {
  try {
    return (
      JSON.parse(sessionStorage.getItem("localflow-run-context") || "{}") || {}
    );
  } catch {
    return {};
  }
}

function readExplorerOpenState() {
  try {
    const collapsed = JSON.parse(
      localStorage.getItem("localflow-explorer-collapsed") || "[]",
    );
    return Object.fromEntries(
      (Array.isArray(collapsed) ? collapsed : []).map((id) => [id, false]),
    );
  } catch {
    return {};
  }
}

function readFavoriteConfigs() {
  try {
    const paths = JSON.parse(
      localStorage.getItem("localflow-favorite-configs") || "[]",
    );
    return Array.isArray(paths)
      ? paths.filter((path) => typeof path === "string").slice(0, 100)
      : [];
  } catch {
    return [];
  }
}

function Config({ theme, explorerView, onExplorerViewChange, paused = false }) {
  const filePathRef = useRef();
  const inspectionControllerRef = useRef();
  const diagnosisControllerRef = useRef();
  const editorRef = useRef();
  const monacoRef = useRef();
  const contentRef = useRef("");
  const baseContentRef = useRef("");
  const fileRef = useRef();
  const draftsRef = useRef(new Map());
  const localVersionsRef = useRef(new Map());
  const openRequestRef = useRef(0);
  const pluginsRef = useRef([]);
  const [files, setFiles] = useState([]);
  const [diagnostics, setDiagnostics] = useState({});
  const [editorDiagnosis, setEditorDiagnosis] = useState();
  const [plugins, setPlugins] = useState([]);
  const [file, setFile] = useState();
  const [preview, setPreview] = useState();
  const [inspectionRevision, setInspectionRevision] = useState(0);
  const [selectedPath, setSelectedPath] = useState();
  const [clipboard, setClipboard] = useState();
  const [content, setContent] = useState("");
  const [dirtyPaths, setDirtyPaths] = useState(new Set());
  const [mode, setMode] = useState("edit");
  const [values, setValues] = useState({});
  const [notice, setNotice] = useState("");
  const [runStatus, setRunStatus] = useState("idle");
  const [conflict, setConflict] = useState();
  const [createOpen, setCreateOpen] = useState(false);
  const [createKind, setCreateKind] = useState("file");
  const [createPath, setCreatePath] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [treeOpen, setTreeOpen] = useState(false);
  const [favoritePaths, setFavoritePaths] = useState(readFavoriteConfigs);
  const [recentConfigs, setRecentConfigs] = useState([]);
  const [treeSize, setTreeSize] = useState({ width: 260, height: 600 });
  const treeHost = useRef();
  const treeRef = useRef();
  const initialTreeOpenState = useRef(readExplorerOpenState());
  const markDirty = useCallback((path, dirty) => {
    setDirtyPaths((current) => {
      if (dirty === current.has(path)) return current;
      const next = new Set(current);
      if (dirty) next.add(path);
      else next.delete(path);
      return next;
    });
  }, []);
  const forgetDrafts = useCallback((prefix) => {
    for (const path of draftsRef.current.keys()) {
      if (path === prefix || path.startsWith(`${prefix}/`))
        draftsRef.current.delete(path);
    }
    setDirtyPaths(
      (current) =>
        new Set(
          [...current].filter(
            (path) => path !== prefix && !path.startsWith(`${prefix}/`),
          ),
        ),
    );
  }, []);
  const remapDrafts = useCallback((source, target) => {
    const replacements = [];
    for (const [path, draft] of draftsRef.current.entries()) {
      if (path !== source && !path.startsWith(`${source}/`)) continue;
      const nextPath = target + path.slice(source.length);
      replacements.push([
        path,
        nextPath,
        { ...draft, file: { ...draft.file, path: nextPath } },
      ]);
    }
    if (!replacements.length) return;
    for (const [path] of replacements) draftsRef.current.delete(path);
    for (const [, path, draft] of replacements)
      draftsRef.current.set(path, draft);
    setDirtyPaths((current) => {
      const next = new Set(current);
      for (const [path, nextPath] of replacements) {
        next.delete(path);
        next.add(nextPath);
      }
      return next;
    });
  }, []);
  const reload = useCallback(async () => {
    const result = await api.workspace();
    setFiles(result.items);
    setDiagnostics(result.diagnostics || {});
    const available = new Set(
      result.items
        .filter((item) => item.kind === "file" && item.path.startsWith("config/"))
        .map((item) => item.path),
    );
    setFavoritePaths((current) => {
      const next = current.filter((path) => available.has(path));
      return next.length === current.length ? current : next;
    });
    return result.items;
  }, []);
  const reloadRecent = useCallback(async () => {
    const result = await api.recentConfigs();
    const items = Array.isArray(result.items) ? result.items : [];
    setRecentConfigs(items);
    return items;
  }, []);
  const open = useCallback(async (path, restore = true, cleanSyncBase) => {
    const request = ++openRequestRef.current;
    const serverValue = await api.workspaceFile(path);
    if (request !== openRequestRef.current) return serverValue;
    if (
      cleanSyncBase !== undefined &&
      contentRef.current !== cleanSyncBase
    )
      return serverValue;
    const draft =
      cleanSyncBase === undefined ? draftsRef.current.get(path) : undefined;
    const value = draft?.file || serverValue;
    const stored = restore ? readConfigMemory().files?.[path] : undefined;
    const remembered = stored?.version === value.version ? stored : undefined;
    filePathRef.current = path;
    fileRef.current = value;
    contentRef.current = draft?.content ?? value.content;
    baseContentRef.current = draft?.baseContent ?? value.content;
    setSelectedPath(path);
    setFile(value);
    setPreview(value);
    setContent(contentRef.current);
    const plugin = pluginsRef.current.find((item) => item.name === value.plugin);
    setValues(
      remembered?.values || withoutCaseSelections(plugin, value.document || {}),
    );
    setEditorDiagnosis(draft?.diagnosis || value.diagnosis);
    if (cleanSyncBase === undefined)
      setMode(
        path.startsWith("config/")
          ? draft || !value.content
            ? "edit"
            : "use"
          : "edit",
      );
    setRunStatus("idle");
    setNotice(
      draft && draft.file.version !== serverValue.version
        ? "文件已在外部变化，请比较后选择"
        : "",
    );
    setTreeOpen(false);
    setConflict(undefined);
  }, []);
  useEffect(() => {
    Promise.all([
      reload(),
      reloadRecent(),
      api.plugins().then((result) => {
        pluginsRef.current = result.items;
        setPlugins(result.items);
      }),
    ])
      .then(([items]) => {
        const remembered = readConfigMemory().path;
        const paths = items
          .filter((item) => item.kind === "file")
          .map((item) => item.path);
        const target = paths.includes(remembered) ? remembered : paths[0];
        if (target) open(target);
      })
      .catch((error) => setNotice(error.message));
  }, [reload, reloadRecent, open]);
  useEffect(() => {
    localStorage.setItem(
      "localflow-favorite-configs",
      JSON.stringify(favoritePaths),
    );
  }, [favoritePaths]);
  useEffect(() => {
    if (!file?.path) return;
    const memory = readConfigMemory();
    sessionStorage.setItem(
      "localflow-run-context",
      JSON.stringify({
        ...memory,
        path: file.path,
        files: {
          ...(memory.files || {}),
          [file.path]: { version: file.version, mode, values },
        },
      }),
    );
  }, [file?.path, file?.version, mode, values]);
  useEffect(() => {
    filePathRef.current = file?.path;
    fileRef.current = file;
  }, [file?.path]);
  useEffect(() => {
    contentRef.current = content;
  }, [content]);
  useEffect(() => {
    if (!file?.path?.startsWith("config/")) return;
    diagnosisControllerRef.current?.abort();
    const controller = new AbortController();
    diagnosisControllerRef.current = controller;
    const timer = setTimeout(() => {
      api
        .diagnoseConfig(
          file.path.replace(/^config\//, ""),
          content,
          controller.signal,
        )
        .then((result) => {
          if (!controller.signal.aborted) {
            setEditorDiagnosis(result.diagnosis);
            setPreview(result);
          }
        })
        .catch((error) =>
          error.name === "AbortError"
            ? undefined
            : setEditorDiagnosis({ valid: false, errors: [error.message] }),
        );
    }, 220);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [file?.path, content]);
  useEffect(() => {
    const monaco = monacoRef.current;
    const model = editorRef.current?.getModel();
    if (!monaco || !model) return;
    const issues = editorDiagnosis?.issues || [];
    const fallback = issues.length
      ? issues
      : (editorDiagnosis?.errors || []).map((message) => ({
          message,
          line: 1,
          column: 1,
          end_line: 1,
          end_column: 2,
          severity: "error",
        }));
    monaco.editor.setModelMarkers(
      model,
      "localflow-yaml",
      fallback.map((issue) => ({
        message: issue.message,
        severity:
          issue.severity === "warning"
            ? monaco.MarkerSeverity.Warning
            : monaco.MarkerSeverity.Error,
        startLineNumber: issue.line,
        startColumn: issue.column,
        endLineNumber: issue.end_line,
        endColumn: issue.end_column,
      })),
    );
  }, [editorDiagnosis, file?.path, mode]);
  useEffect(() => {
    if (!notice.startsWith("已")) return;
    const timer = setTimeout(
      () => setNotice((current) => (current === notice ? "" : current)),
      2800,
    );
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (runStatus !== "accepted") return;
    const timer = setTimeout(() => setRunStatus("idle"), 1600);
    return () => clearTimeout(timer);
  }, [runStatus]);
  useEffect(() => {
    let frame;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const rect = treeHost.current?.getBoundingClientRect();
        if (!rect?.width || !rect?.height) return;
        setTreeSize({
          width: Math.floor(rect.width),
          height: Math.floor(rect.height),
        });
      });
    });
    if (treeHost.current) observer.observe(treeHost.current);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, []);
  useEffect(() => {
    if (paused) return undefined;
    const events = new EventSource("/api/v1/events");
    const changed = (event) => {
      const data = JSON.parse(event.data);
      const path = `config/${data.path}`;
      if (localVersionsRef.current.get(path) === data.version) {
        localVersionsRef.current.delete(path);
        return;
      }
      reload()
        .then((items) => {
          const affected = (data.affected_paths || [data.path]).map(
            (item) => `config/${item}`,
          );
          if (
            !affected.includes(filePathRef.current) ||
            !items.some((item) => item.path === filePathRef.current)
          )
            return undefined;
          if (contentRef.current !== baseContentRef.current) {
            return api
              .diagnoseConfig(
                filePathRef.current.replace(/^config\//, ""),
                contentRef.current,
              )
              .then((result) => {
                setEditorDiagnosis(result.diagnosis);
                setPreview(result);
                setInspectionRevision((value) => value + 1);
                setNotice(
                  path === filePathRef.current
                    ? "文件已在外部变化；已保留未保存编辑并重新检查"
                    : "配置依赖已变化；已保留未保存编辑并重新检查",
                );
              });
          }
          const cleanBase = baseContentRef.current;
          return open(filePathRef.current, false, cleanBase).then(() => {
            setInspectionRevision((value) => value + 1);
            setNotice(path === filePathRef.current ? "已同步外部修改" : "已同步配置依赖");
          });
        })
        .catch((error) => setNotice(`同步失败：${error.message}`));
    };
    const removed = (event) => {
      const data = JSON.parse(event.data);
      const affected = (data.affected_paths || [data.path]).map(
        (item) => `config/${item}`,
      );
      return reload().then((items) => {
        if (
          filePathRef.current &&
          !items.some((item) => item.path === filePathRef.current)
        ) {
          setFile(undefined);
          filePathRef.current = undefined;
          return undefined;
        }
        if (!affected.includes(filePathRef.current)) return undefined;
        if (contentRef.current !== baseContentRef.current)
          return api
            .diagnoseConfig(
              filePathRef.current.replace(/^config\//, ""),
              contentRef.current,
            )
            .then((result) => {
              setEditorDiagnosis(result.diagnosis);
              setPreview(result);
              setNotice("配置依赖已删除；已保留未保存编辑并重新检查");
            });
        const cleanBase = baseContentRef.current;
        return open(filePathRef.current, false, cleanBase).then(() =>
          setNotice("已同步配置依赖"),
        );
      });
    };
    const pluginChanged = () => {
      return api.plugins().then((result) => {
        pluginsRef.current = result.items;
        setPlugins(result.items);
        const current = filePathRef.current;
        if (!current?.startsWith("config/")) return undefined;
        if (contentRef.current !== baseContentRef.current) {
          setNotice("插件已更新；保存或重新打开后刷新运行检查");
          return undefined;
        }
        const cleanBase = baseContentRef.current;
        return open(current, false, cleanBase).then(() =>
          setNotice("已同步外部修改"),
        );
      });
    };
    events.addEventListener("config.changed", changed);
    events.addEventListener("config.invalid", changed);
    events.addEventListener("config.deleted", removed);
    events.addEventListener("plugins.changed", pluginChanged);
    return () => events.close();
  }, [reload, open, paused]);
  const effectiveConfig = preview || file;
  const selectedPlugin = plugins.find(
    (item) => item.name === effectiveConfig?.plugin,
  );
  const runDisabled =
    dirtyPaths.has(file?.path) ||
    !effectiveConfig?.run_diagnosis?.runnable ||
    selectedPlugin?.fields.some(
      (field) =>
        field.required &&
        (values[field.name] == null ||
          values[field.name] === "" ||
          (Array.isArray(values[field.name]) && values[field.name].length === 0)),
    );
  const move = async (source, target) => {
    const movesOpenFile =
      filePathRef.current === source ||
      filePathRef.current?.startsWith(`${source}/`);
    inspectionControllerRef.current?.abort();
    if (movesOpenFile)
      filePathRef.current = target + filePathRef.current.slice(source.length);
    await api.moveWorkspace(source, target);
    remapDrafts(source, target);
    setFavoritePaths((current) =>
      current.map((path) =>
        path === source || path.startsWith(`${source}/`)
          ? target + path.slice(source.length)
          : path,
      ),
    );
    await Promise.all([reload(), reloadRecent()]);
    setSelectedPath(target);
    if (movesOpenFile) await open(filePathRef.current);
    setNotice("已移动");
  };
  const rename = async ({ id, name }) => {
    const source = id.replace(/^folder:/, "");
    if (source === "config") return;
    const parent = source.slice(0, source.lastIndexOf("/") + 1);
    await move(source, `${parent}${name}`);
  };
  const beginRename = () => {
    if (!selectedPath || selectedEntry?.readonly) return;
    const id = selectedEntry?.kind === "directory"
      ? `folder:${selectedPath}`
      : selectedPath;
    treeRef.current?.edit(id);
    requestAnimationFrame(() => {
      const input = treeHost.current?.querySelector(
        `[data-file="${CSS.escape(id)}"] input`,
      );
      input?.focus();
      input?.select();
    });
  };
  const onMove = async ({ dragIds, parentId }) => {
    const targetFolder = parentId?.replace(/^folder:/, "") || "";
    for (const raw of dragIds) {
      const source = raw.replace(/^folder:/, "");
      await move(source, `${targetFolder}/${pathLeaf(source)}`);
    }
  };
  const save = async () => {
    try {
      const activeMode = mode;
      const saved = await api.saveWorkspaceFile(
        file.path,
        contentRef.current,
        file.version,
      );
      localVersionsRef.current.set(saved.path, saved.version);
      draftsRef.current.delete(saved.path);
      markDirty(saved.path, false);
      await open(saved.path, false);
      setMode(activeMode);
      setNotice("已保存");
    } catch (error) {
      if (error.status === 412) {
        setConflict(await api.workspaceFile(file.path));
        setNotice("文件已变化，请比较后选择");
      } else setNotice(`保存失败：${error.message}`);
    }
  };
  const run = async () => {
    setRunStatus("submitting");
    setNotice("");
    try {
      const result = await api.runConfig(
        file.path.replace(/^config\//, ""),
        pluginInputs(selectedPlugin, values),
      );
      await reloadRecent();
      setRunStatus("accepted");
      setValues((current) => withoutCaseSelections(selectedPlugin, current));
      setNotice(`已加入 ${result.count} 个任务`);
    } catch (error) {
      setRunStatus("idle");
      setNotice(`运行失败：${error.message}`);
    }
  };
  const selectedEntry = files.find((item) => item.path === selectedPath);
  const selectedFolder =
    selectedEntry?.kind === "directory"
      ? selectedPath
      : selectedPath?.slice(0, selectedPath.lastIndexOf("/"));
  const create = async () => {
    try {
      const base = selectedFolder || "config";
      let path = createPath.includes("/")
        ? createPath
        : `${base}/${createPath}`;
      if (createKind === "directory") await api.createDirectory(path);
      else if (path.startsWith("config/")) {
        const relative = path.replace(/^config\//, "");
        const named = /\.(?:ya?ml|json|toml)$/i.test(relative)
          ? relative
          : `${relative}.yaml`;
        const created = await api.saveWorkspaceFile(`config/${named}`, "", "*");
        localVersionsRef.current.set(created.path, created.version);
        path = `config/${named}`;
      }
      setCreateOpen(false);
      setCreatePath("");
      await reload();
      setSelectedPath(path);
      if (createKind === "file") await open(path, false);
      setNotice("已创建");
    } catch (error) {
      setNotice(`创建失败：${error.message}`);
    }
  };
  const remove = async () => {
    const removedPath = selectedPath;
    const removesOpenFile =
      filePathRef.current === removedPath ||
      filePathRef.current?.startsWith(`${removedPath}/`);
    inspectionControllerRef.current?.abort();
    if (removesOpenFile) {
      setFile(undefined);
      filePathRef.current = undefined;
    }
    try {
      await api.deleteWorkspace(removedPath);
      forgetDrafts(removedPath);
      setFavoritePaths((current) =>
        current.filter(
          (path) => path !== removedPath && !path.startsWith(`${removedPath}/`),
        ),
      );
      setDeleting(false);
      await reload();
      setSelectedPath(undefined);
      setNotice("已删除");
    } catch (error) {
      if (removesOpenFile) await open(removedPath, false).catch(() => undefined);
      setNotice(`删除失败：${error.message}`);
    }
  };
  const place = async () => {
    if (!clipboard || !selectedFolder) return;
    const target = `${selectedFolder}/${pathLeaf(clipboard.path)}`;
    try {
      if (clipboard.mode === "cut") {
        await move(clipboard.path, target);
        setClipboard(undefined);
      } else {
        await api.copyWorkspace(clipboard.path, target);
        await reload();
        setSelectedPath(target);
        setNotice("已粘贴");
      }
    } catch (error) {
      setNotice(`粘贴失败：${error.message}`);
    }
  };
  const keyAction = (event) => {
    if (
      !selectedPath ||
      ["INPUT", "TEXTAREA"].includes(event.target.tagName) ||
      event.target.closest(".monaco-editor")
    )
      return;
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && ["c", "x", "v"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      if (event.key.toLowerCase() === "v") place();
      else
        setClipboard({
          path: selectedPath,
          mode: event.key.toLowerCase() === "x" ? "cut" : "copy",
        });
    } else if (event.key === "F2") {
      event.preventDefault();
      beginRename();
    } else if (event.key === "Delete" && !selectedEntry?.readonly) {
      event.preventDefault();
      setDeleting(true);
    }
  };
  const editorTheme = theme === "dark" ? "localflow-dark" : "vs";
  const availableConfigPaths = new Set(
    files
      .filter((item) => item.kind === "file" && item.path.startsWith("config/"))
      .map((item) => item.path),
  );
  const recentByPath = new Map(recentConfigs.map((item) => [item.path, item]));
  const quickEntry = (path) => ({
    path,
    name: recentByPath.get(path)?.name || pathLeaf(path),
    labels: recentByPath.get(path)?.labels || [],
    last_used_at: recentByPath.get(path)?.last_used_at,
  });
  const favoriteConfigs = favoritePaths
    .map((path, index) => ({ ...quickEntry(path), favoriteIndex: index }))
    .filter((item) => availableConfigPaths.has(item.path))
    .sort((left, right) => {
      if (left.last_used_at && right.last_used_at)
        return right.last_used_at.localeCompare(left.last_used_at);
      if (left.last_used_at) return -1;
      if (right.last_used_at) return 1;
      return right.favoriteIndex - left.favoriteIndex;
    });
  const unpinnedRecentConfigs = recentConfigs.filter(
    (item) =>
      availableConfigPaths.has(item.path) && !favoritePaths.includes(item.path),
  );
  const isFavorite = Boolean(file?.path && favoritePaths.includes(file.path));
  const toggleFavorite = () => {
    if (!file?.path?.startsWith("config/")) return;
    setFavoritePaths((current) =>
      current.includes(file.path)
        ? current.filter((path) => path !== file.path)
        : [...current, file.path].slice(-100),
    );
  };
  const openQuickConfig = async (path) => {
    try {
      await open(path);
    } catch (error) {
      if (error.status !== 404 && error.status !== 410) {
        setNotice(`打开失败：${error.message}`);
        return;
      }
      setFavoritePaths((current) => current.filter((item) => item !== path));
      await Promise.allSettled([reload(), reloadRecent()]);
    }
  };
  const editorLanguage = file?.path.endsWith(".py")
    ? "python"
    : file?.path.endsWith(".md")
      ? "markdown"
      : file?.path.endsWith("json")
        ? "json"
        : file?.path.endsWith("toml")
          ? "ini"
          : "yaml";
  const sourceViews = [
    ["resources", "资源"],
    ["quick", "常用"],
  ];
  const moveSourceTab = (event, index) => {
    let next = index;
    if (event.key === "ArrowLeft")
      next = (index + sourceViews.length - 1) % sourceViews.length;
    else if (event.key === "ArrowRight") next = (index + 1) % sourceViews.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = sourceViews.length - 1;
    else return;
    event.preventDefault();
    onExplorerViewChange(sourceViews[next][0]);
    event.currentTarget.parentElement
      ?.querySelectorAll('[role="tab"]')
      [next]?.focus();
  };
  return (
    <div className="config-explorer" tabIndex="0" onKeyDown={keyAction}>
      <aside
        id="config-source-panel"
        className="explorer"
        data-explorer-view={explorerView}
      >
        <header className="config-source-header">
          <div className="config-source-tabs" role="tablist" aria-label="配置来源">
            {sourceViews.map(([id, label], index) => (
              <button
                id={`config-source-${id}-tab`}
                className="config-source-tab"
                type="button"
                role="tab"
                aria-selected={explorerView === id}
                aria-controls={`config-source-${id}-panel`}
                tabIndex={explorerView === id ? 0 : -1}
                onClick={() => onExplorerViewChange(id)}
                onKeyDown={(event) => moveSourceTab(event, index)}
                key={id}
              >
                {label}
              </button>
            ))}
          </div>
          {explorerView === "resources" && (
            <div className="config-resource-actions" role="group" aria-label="资源操作">
              <button
                className="icon"
                aria-label="新建文件"
                title="新建文件"
                onClick={() => {
                  setCreateKind("file");
                  setCreateOpen(true);
                }}
              >
                <Plus />
              </button>
              <button
                className="icon"
                aria-label="新建目录"
                title="新建目录"
                onClick={() => {
                  setCreateKind("directory");
                  setCreateOpen(true);
                }}
              >
                <FolderPlus />
              </button>
              <button
                className="icon"
                aria-label="复制"
                title="复制"
                disabled={!selectedPath}
                onClick={() => setClipboard({ path: selectedPath, mode: "copy" })}
              >
                <Copy />
              </button>
              <button
                className="icon"
                aria-label="剪切"
                title="剪切"
                disabled={!selectedPath || selectedEntry?.readonly}
                onClick={() => setClipboard({ path: selectedPath, mode: "cut" })}
              >
                <Scissors />
              </button>
              <button
                className="icon"
                aria-label="粘贴"
                title="粘贴"
                disabled={!clipboard || !selectedFolder}
                onClick={place}
              >
                <ClipboardPaste />
              </button>
              <button
                className="icon"
                aria-label="重命名"
                title="重命名"
                disabled={!selectedPath || selectedEntry?.readonly}
                onClick={beginRename}
              >
                <Pencil />
              </button>
              <button
                className="icon danger-icon"
                aria-label="删除"
                title="删除"
                disabled={!selectedPath || selectedEntry?.readonly}
                onClick={() => setDeleting(true)}
              >
                <Trash2 />
              </button>
            </div>
          )}
        </header>
        {explorerView === "resources" ? (
          <div
            id="config-source-resources-panel"
            className="tree-host"
            role="tabpanel"
            aria-labelledby="config-source-resources-tab"
            ref={treeHost}
          >
            <Tree
              ref={treeRef}
              data={buildTree(files, diagnostics, dirtyPaths)}
              width={treeSize.width}
              height={treeSize.height}
              rowHeight={32}
              indent={16}
              overscanCount={8}
              openByDefault
              initialOpenState={initialTreeOpenState.current}
              onToggle={(id) => {
                setTimeout(() => {
                  const current = readExplorerOpenState();
                  if (treeRef.current?.isOpen(id)) delete current[id];
                  else current[id] = false;
                  localStorage.setItem(
                    "localflow-explorer-collapsed",
                    JSON.stringify(Object.keys(current).slice(-512)),
                  );
                }, 0);
              }}
              selection={
                selectedEntry?.kind === "directory"
                  ? `folder:${selectedPath}`
                  : selectedPath
              }
              onSelect={(nodes) => {
                const node = nodes[0];
                if (!node) return;
                setSelectedPath(node.data.path);
                if (!node.isInternal) open(node.data.path);
              }}
              onRename={rename}
              onMove={onMove}
              disableEdit
            >
              {TreeNode}
            </Tree>
          </div>
        ) : (
          <div
            id="config-source-quick-panel"
            className="quick-configs"
            role="tabpanel"
            aria-labelledby="config-source-quick-tab"
          >
            {[
              ["已收藏", favoriteConfigs, true],
              ["最近使用", unpinnedRecentConfigs, false],
            ].map(([heading, items, favorite]) =>
              items.length ? (
                <section className="quick-config-group" key={heading}>
                  <h3>{heading}</h3>
                  <ul aria-label={heading}>
                    {items.map((item) => (
                      <li key={item.path}>
                        <button
                          type="button"
                          className={item.path === file?.path ? "active" : ""}
                          aria-current={item.path === file?.path ? "true" : undefined}
                          aria-label={item.path}
                          title={item.path}
                          onClick={() => openQuickConfig(item.path)}
                        >
                          {favorite ? (
                            <Star aria-hidden="true" />
                          ) : (
                            <Clock3 aria-hidden="true" />
                          )}
                          <span className="quick-config-path">{item.path}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null,
            )}
            {!favoriteConfigs.length && !unpinnedRecentConfigs.length && (
              <p className="quick-config-empty">暂无常用配置</p>
            )}
          </div>
        )}
      </aside>
      <section className="config-workbench">
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        {file ? (
          <>
            <header className="workbench-header">
              <div className="workbench-context">
                <FileCode2 />
                <span>{pathLeaf(file.path)}</span>
              </div>
              <div className="workbench-actions" role="group" aria-label="配置操作">
                {file.path.startsWith("config/") && (
                  <button
                    type="button"
                    className={`secondary icon-only favorite-action ${isFavorite ? "active" : ""}`}
                    aria-label={isFavorite ? "取消收藏" : "收藏配置"}
                    aria-pressed={isFavorite}
                    title={isFavorite ? "取消收藏" : "收藏配置"}
                    onClick={toggleFavorite}
                  >
                    <Star aria-hidden="true" />
                  </button>
                )}
                {mode === "edit" && file.path.startsWith("config/") && (
                    <button
                      className="secondary"
                      onClick={() => {
                        setMode("use");
                      }}
                    >
                      <Play />
                      运行
                    </button>
                  )}
                  {mode === "use" && (
                    <button className="secondary" onClick={() => setMode("edit")}>
                      <FilePenLine />
                      编辑
                    </button>
                  )}
                  {mode === "edit" ? (
                    <button
                      className="primary"
                      disabled={!file || content === baseContentRef.current}
                      onClick={save}
                    >
                      保存
                    </button>
                  ) : (
                    <button
                      className={`primary run-action ${runStatus}`}
                      data-run-state={runStatus}
                      disabled={runDisabled || runStatus === "submitting"}
                      title={dirtyPaths.has(file.path) ? "请先保存配置" : undefined}
                      onClick={run}
                    >
                      {runStatus === "accepted" ? (
                        <Check />
                      ) : runStatus === "submitting" ? (
                        <Activity />
                      ) : (
                        <Play />
                      )}
                      <span>
                        {runStatus === "accepted"
                          ? "已创建"
                          : runStatus === "submitting"
                            ? "提交中"
                            : effectiveConfig?.run_diagnosis?.runnable
                              ? "运行"
                              : "配置无效"}
                      </span>
                    </button>
                  )}
              </div>
            </header>
            {mode === "use" ? (
              <div className="use-config">
                {effectiveConfig?.run_diagnosis?.runnable && selectedPlugin ? (
                  <RunFields
                    key={`${file.version}:${inspectionRevision}`}
                    plugin={selectedPlugin}
                    filePath={file.path.replace(/^config\//, "")}
                    values={values}
                    setValues={setValues}
                    inspectionControllerRef={inspectionControllerRef}
                  />
                ) : (
                  <ConfigurationDebug preview={effectiveConfig} />
                )}
              </div>
            ) : conflict ? (
              <div className="conflict">
                <div>
                  <b>最新版本</b>
                  <span>你的编辑</span>
                  <button
                    onClick={() => {
                      setFile(conflict);
                      fileRef.current = conflict;
                      contentRef.current = conflict.content;
                      baseContentRef.current = conflict.content;
                      setContent(conflict.content);
                      draftsRef.current.delete(conflict.path);
                      markDirty(conflict.path, false);
                      setConflict(undefined);
                    }}
                  >
                    采用最新版本
                  </button>
                </div>
                <Suspense fallback={<div className="editor-loading">正在载入编辑器</div>}>
                  <DiffEditor
                    height="calc(100vh - 120px)"
                    original={conflict.content}
                    modified={content}
                    language={editorLanguage}
                    theme={editorTheme}
                    options={{ readOnly: true, automaticLayout: true }}
                  />
                </Suspense>
              </div>
            ) : (
              <div className="editor-stack">
                <Suspense fallback={<div className="editor-loading">正在载入编辑器</div>}>
                  <Editor
                  height="100%"
                  language={editorLanguage}
                  theme={editorTheme}
                  value={content}
                  onMount={(editor, monaco) => {
                    editorRef.current = editor;
                    monacoRef.current = monaco;
                    setEditorDiagnosis((current) => ({ ...current }));
                  }}
                  onChange={(value) => {
                    const next = value || "";
                    if (next === contentRef.current) return;
                    contentRef.current = next;
                    setContent(next);
                    const path = filePathRef.current;
                    if (!path || !fileRef.current) return;
                    if (next === baseContentRef.current) {
                      draftsRef.current.delete(path);
                      markDirty(path, false);
                    } else {
                      draftsRef.current.set(path, {
                        file: fileRef.current,
                        content: next,
                        baseContent: baseContentRef.current,
                        diagnosis: editorDiagnosis,
                      });
                      markDirty(path, true);
                    }
                  }}
                  options={{
                    minimap: { enabled: false },
                    automaticLayout: true,
                    padding: { top: 16 },
                  }}
                  />
                </Suspense>
                {editorDiagnosis?.errors?.length > 0 && (
                  <section className="problems-panel" aria-label="问题" role="region">
                    <header>
                      <b>问题</b>
                      <span>{editorDiagnosis.errors.length}</span>
                    </header>
                    <ul>
                      {(editorDiagnosis.issues?.length
                        ? editorDiagnosis.issues
                        : editorDiagnosis.errors.map((message) => ({
                            message,
                            line: 1,
                            column: 1,
                          }))).map((issue, index) => (
                        <li key={`${issue.message}-${index}`}>
                          <button
                            type="button"
                            onClick={() => {
                              editorRef.current?.setPosition({
                                lineNumber: issue.line,
                                column: issue.column,
                              });
                              editorRef.current?.revealLineInCenter(issue.line);
                              editorRef.current?.focus();
                            }}
                          >
                            <TriangleAlert />
                            <span>{issue.message}</span>
                            <code>{issue.line}:{issue.column}</code>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="empty-workbench">
            <FileCode2 />
          </div>
        )}
      </section>
      {createOpen && (
        <div className="dialog-backdrop">
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="create-title"
            className="dialog"
          >
            <header>
              <h2 id="create-title">
                {createKind === "directory" ? "新建目录" : "新建文件"}
              </h2>
              <button
                className="icon"
                aria-label="关闭"
                onClick={() => setCreateOpen(false)}
              >
                <X />
              </button>
            </header>
            <label>
              <span>名称</span>
              <input
                autoFocus
                value={createPath}
                onChange={(event) => setCreatePath(event.target.value)}
              />
            </label>
            <footer>
              <button
                className="secondary"
                onClick={() => setCreateOpen(false)}
              >
                取消
              </button>
              <button
                className="primary"
                disabled={!createPath.trim()}
                onClick={create}
              >
                创建
              </button>
            </footer>
          </div>
        </div>
      )}
      {deleting && (
        <div className="dialog-backdrop">
          <div role="alertdialog" aria-modal="true" className="dialog">
            <h2>删除 {pathLeaf(selectedPath || "")}？</h2>
            <p>此操作无法撤销。</p>
            <footer>
              <button className="secondary" onClick={() => setDeleting(false)}>
                取消
              </button>
              <button className="danger compact" onClick={remove}>
                删除
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
}

function localInputValue(value) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 19);
}
function SettingsPage({
  theme,
  setTheme,
  role,
  onLogin,
  onShutdownAccepted,
  activeTaskCount,
}) {
  const [serverTime, setServerTime] = useState();
  const [referenceTime, setReferenceTime] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [editing, setEditing] = useState(false);
  const [, setTick] = useState(0);
  const [adminKey, setAdminKey] = useState("");
  const [loginNotice, setLoginNotice] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [shutdownOpen, setShutdownOpen] = useState(false);
  const [shuttingDown, setShuttingDown] = useState(false);
  const [shutdownError, setShutdownError] = useState("");
  const loadTime = useCallback(async () => {
    const state = await api.status();
    const value = state.time.wall_clock;
    setServerTime({ value: new Date(value), observed: Date.now() });
    setReferenceTime(localInputValue(value));
  }, []);
  useEffect(() => {
    loadTime().catch((error) => setNotice(`读取失败：${error.message}`));
  }, [loadTime]);
  useEffect(() => {
    const timer = setInterval(() => setTick((old) => old + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const current = serverTime
    ? new Date(serverTime.value.getTime() + Date.now() - serverTime.observed)
    : undefined;
  const displayedTime = editing
    ? referenceTime
    : current
      ? localInputValue(current)
      : "";
  useEffect(() => {
    if (!dirty || !referenceTime) return;
    const timer = setTimeout(async () => {
      try {
        await api.adjustTime(new Date(referenceTime).toISOString());
        setDirty(false);
        setEditing(false);
        await loadTime();
        setNotice("");
      } catch (error) {
        setNotice(`校准失败：${error.message}`);
      }
    }, 600);
    return () => clearTimeout(timer);
  }, [dirty, referenceTime, loadTime]);
  const login = async (event) => {
    event.preventDefault();
    if (!adminKey.trim() || loggingIn) return;
    setLoggingIn(true);
    setLoginNotice("");
    try {
      await api.login(adminKey.trim());
      setAdminKey("");
      await onLogin();
    } catch (error) {
      setLoginNotice(
        error.status === 401 ? "秘钥不正确" : `登录失败：${error.message}`,
      );
    } finally {
      setLoggingIn(false);
    }
  };
  const shutdown = async (event) => {
    event.preventDefault();
    if (shuttingDown) return;
    setShuttingDown(true);
    setShutdownError("");
    try {
      await api.shutdown();
      onShutdownAccepted();
    } catch (error) {
      setShuttingDown(false);
      setShutdownError(`退出失败：${error.message}`);
    }
  };
  return (
    <div className="settings">
      <section className="settings-panel">
        <div className="setting-row">
          <span>主题</span>
          <div className="theme-choice" role="group" aria-label="主题">
            <button
              className={theme === "light" ? "active" : ""}
              aria-pressed={theme === "light"}
              onClick={() => setTheme("light")}
            >
              <Sun />
              浅色
            </button>
            <button
              className={theme === "dark" ? "active" : ""}
              aria-pressed={theme === "dark"}
              onClick={() => setTheme("dark")}
            >
              <Moon />
              深色
            </button>
          </div>
        </div>
        {role !== "admin" && (
          <form className="setting-row login-row" onSubmit={login}>
            <label htmlFor="web-admin-key">秘钥登录</label>
            <span className="login-control">
              <span className="secret-entry">
                <input
                  id="web-admin-key"
                  aria-label="管理员秘钥"
                  type="password"
                  autoComplete="current-password"
                  value={adminKey}
                  onChange={(event) => setAdminKey(event.target.value)}
                />
                <button
                  className="primary"
                  type="submit"
                  disabled={!adminKey.trim() || loggingIn}
                >
                  {loggingIn ? "登录中" : "登录"}
                </button>
              </span>
              {loginNotice && <small role="alert">{loginNotice}</small>}
            </span>
          </form>
        )}
        {role === "admin" && (
          <label className="setting-row">
            <span>时间校准</span>
            <span className="time-control">
              <input
                aria-label="时间校准"
                type="datetime-local"
                step="1"
                value={displayedTime}
                onFocus={() => {
                  setReferenceTime(displayedTime);
                  setEditing(true);
                }}
                onChange={(event) => {
                  setReferenceTime(event.target.value);
                  setDirty(true);
                }}
              />
              {notice && <small>{notice}</small>}
            </span>
          </label>
        )}
        {role === "admin" && (
          <div className="setting-row">
            <span>服务</span>
            <AlertDialog.Root
              open={shutdownOpen}
              onOpenChange={(open) => {
                if (!shuttingDown) {
                  setShutdownOpen(open);
                  setShutdownError("");
                }
              }}
            >
              <AlertDialog.Trigger asChild>
                <button className="shutdown-trigger" type="button">
                  <Power aria-hidden="true" />
                  退出
                </button>
              </AlertDialog.Trigger>
              <AlertDialog.Portal>
                <AlertDialog.Overlay className="alert-dialog-overlay" />
                <AlertDialog.Content className="alert-dialog-content">
                  <AlertDialog.Title>退出 LocalFlow？</AlertDialog.Title>
                  <AlertDialog.Description>
                    {activeTaskCount > 0
                      ? `将先停止 ${activeTaskCount} 个未结束任务，确认全部退出后关闭。`
                      : "LocalFlow 将停止服务。"}
                  </AlertDialog.Description>
                  {shutdownError && <p role="alert">{shutdownError}</p>}
                  <footer>
                    <AlertDialog.Cancel asChild>
                      <button className="secondary" disabled={shuttingDown}>
                        取消
                      </button>
                    </AlertDialog.Cancel>
                    <AlertDialog.Action asChild>
                      <button
                        className="danger compact"
                        disabled={shuttingDown}
                        onClick={shutdown}
                      >
                        {shuttingDown && <Activity aria-hidden="true" />}
                        {shuttingDown ? "正在退出" : "退出"}
                      </button>
                    </AlertDialog.Action>
                  </footer>
                </AlertDialog.Content>
              </AlertDialog.Portal>
            </AlertDialog.Root>
          </div>
        )}
      </section>
    </div>
  );
}

export default function App() {
  const [shutdownAccepted, setShutdownAccepted] = useState(false);
  useUiRevision(shutdownAccepted);
  const [page, setPage] = useState("tasks");
  const [status, setStatus] = useState();
  const [tasks, setTasks] = useState([]);
  const [opened, setOpened] = useState();
  const [fresh, setFresh] = useState(new Set());
  const [error, setError] = useState("");
  const [theme, setTheme] = useTheme();
  const [runOpen, setRunOpen] = useState(
    () => sessionStorage.getItem("localflow-run-panel") !== "closed",
  );
  const [configSourceView, setConfigSourceView] = useState(
    () => {
      const remembered = sessionStorage.getItem("localflow-config-source-view");
      return ["quick", "favorites"].includes(remembered)
        ? "quick"
        : "resources";
    },
  );
  const [taskWorkspaceNode, setTaskWorkspaceNode] = useState();
  const [splitReady, setSplitReady] = useState(false);
  const refresh = useCallback(async () => {
    if (shutdownAccepted) return;
    try {
      const [state, result] = await Promise.all([api.status(), api.tasks()]);
      setStatus(state);
      setTasks(result.items);
      setError("");
    } catch (reason) {
      setError(reason.message);
    }
  }, [shutdownAccepted]);
  useEffect(() => {
    if (shutdownAccepted) return undefined;
    refresh();
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [refresh, shutdownAccepted]);
  useEffect(() => {
    if (
      status &&
      status.role !== "admin" &&
      !["tasks", "settings"].includes(page)
    )
      setPage("tasks");
  }, [status, page]);
  useEffect(() => {
    setFresh(
      new Set(
        tasks.filter((task) => task.newly_completed).map((task) => task.id),
      ),
    );
  }, [tasks]);
  useEffect(() => {
    sessionStorage.setItem("localflow-run-panel", runOpen ? "open" : "closed");
  }, [runOpen]);
  useEffect(() => {
    sessionStorage.setItem("localflow-config-source-view", configSourceView);
  }, [configSourceView]);
  useEffect(() => {
    if (!taskWorkspaceNode) {
      setSplitReady(false);
      return undefined;
    }
    const update = () => {
      const width = taskWorkspaceNode.getBoundingClientRect().width;
      if (width > 0) setSplitReady(width >= 1240);
    };
    update();
    if (!window.ResizeObserver) return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(taskWorkspaceNode);
    return () => observer.disconnect();
  }, [taskWorkspaceNode]);
  const groups = useMemo(
    () => ({
      running: tasks.filter((task) =>
        ["starting", "running", "stopping"].includes(task.state),
      ),
      queued: tasks.filter((task) => task.state === "queued"),
      history: tasks.filter((task) => finalStates.has(task.state)),
    }),
    [tasks],
  );
  const acknowledge = async (id) => {
    if (status?.role !== "admin") return;
    setFresh((old) => {
      const next = new Set(old);
      next.delete(id);
      return next;
    });
    try {
      await api.acknowledge(id);
    } catch {
      /* optimistic */
    }
  };
  const navigation = [
    ["tasks", "任务", ListChecks],
    ...(status?.role === "admin" ? [["terminal", "终端", TerminalSquare]] : []),
    ["settings", "设置", Settings2],
  ];
  const definitions = [
    ["running", "正在运行", Activity],
    ["queued", "等待队列", Clock3],
    ["history", "历史任务", ListChecks],
  ].filter(([key]) => groups[key].length > 0);
  const moveNavigation = (event, index) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? navigation.length - 1
          : (index + (event.key === "ArrowDown" ? 1 : -1) + navigation.length) %
            navigation.length;
    setPage(navigation[next][0]);
    requestAnimationFrame(() =>
      document.getElementById(`nav-${navigation[next][0]}`)?.focus(),
    );
  };
  const renderTask = (key, task, count = 1) => (
    <TaskItem
      task={task}
      count={count}
      key={task.id}
      role={status?.role}
      theme={theme}
      open={opened === task.id}
      fresh={key === "history" && fresh.has(task.id)}
      toggle={() => setOpened((old) => (old === task.id ? undefined : task.id))}
      ack={() => acknowledge(task.id)}
      interrupt={async () => {
        await api.interrupt(task.id);
        refresh();
      }}
    />
  );
  return (
    <div className="app-shell">
      <aside className="top">
        <nav role="tablist" aria-label="主导航" aria-orientation="vertical">
          {navigation.map(([id, text, Icon], index) => (
            <button
              id={`nav-${id}`}
              role="tab"
              aria-selected={page === id}
              aria-controls="page-panel"
              tabIndex={page === id ? 0 : -1}
              className={page === id ? "active" : ""}
              onClick={() => setPage(id)}
              onKeyDown={(event) => moveNavigation(event, index)}
              key={id}
            >
              <Icon />
              <span>{text}</span>
            </button>
          ))}
        </nav>
        {status?.role === "admin" && page === "tasks" && (
          <div className="nav-actions">
            <button
              className={`run-panel-toggle ${runOpen ? "active" : ""}`}
              aria-expanded={runOpen}
              aria-controls="run-panel"
              onClick={() => setRunOpen((open) => !open)}
            >
              {runOpen ? <PanelLeftClose /> : <PanelLeftOpen />}
              <span>配置</span>
            </button>
          </div>
        )}
      </aside>
      <div className="app-content">
        {error && <p className="global-error">{error}</p>}
        <main
          id="page-panel"
          role="tabpanel"
          aria-labelledby={`nav-${page}`}
          tabIndex="0"
        >
          <section
            ref={setTaskWorkspaceNode}
            data-layout={splitReady ? "split" : "focused"}
            className={`task-workspace ${runOpen ? "run-open" : ""} ${splitReady ? "split-ready" : ""}`}
            hidden={page !== "tasks"}
          >
              <div className="task-pane">
                <section className="workspace">
                  {definitions.length === 0 ? (
                    <div className="tasks-empty">
                      <ListChecks />
                      <p>暂无任务</p>
                    </div>
                  ) : (
                    definitions.map(([key, title, Icon]) => (
                      <section className="group" key={key}>
                        <h2>
                          <Icon />
                          {title}
                          <span>{groups[key].length}</span>
                        </h2>
                        <div>
                          {key === "queued" ? (
                            <QueueTasks
                              tasks={groups[key]}
                              renderTask={(task, count) =>
                                renderTask(key, task, count)
                              }
                            />
                          ) : (
                            groups[key].map((task) => renderTask(key, task))
                          )}
                        </div>
                      </section>
                    ))
                  )}
                </section>
              </div>
              {status?.role === "admin" && (
                <aside id="run-panel" className="run-panel" hidden={!runOpen}>
                  <Config
                    theme={theme}
                    explorerView={configSourceView}
                    onExplorerViewChange={setConfigSourceView}
                    paused={shutdownAccepted}
                  />
                </aside>
              )}
          </section>
          {status?.role === "admin" && page === "terminal" && (
            <TerminalPage tasks={tasks} role={status?.role} theme={theme} />
          )}{" "}
          {page === "settings" && (
            <SettingsPage
              theme={theme}
              setTheme={setTheme}
              role={status?.role}
              onLogin={refresh}
              onShutdownAccepted={() => setShutdownAccepted(true)}
              activeTaskCount={tasks.filter(
                (task) => !finalStates.has(task.state),
              ).length}
            />
          )}
        </main>
      </div>
    </div>
  );
}
