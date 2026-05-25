import { existsSync, readFileSync } from "node:fs";
import { join, sep } from "node:path";
import { spawn } from "node:child_process";
import { complete, type Api, type Model, type UserMessage } from "@earendil-works/pi-ai";
import { BorderedLoader } from "@earendil-works/pi-coding-agent";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

interface ArchonBridgeConfig {
	enabled?: boolean;
	borgosBaseUrl?: string;
	apiToken?: string;
	apiUsername?: string;
	apiPassword?: string;
	pollIntervalMs?: number;
	suggestionModel?: string;
}

interface PersistedState {
	watchedRunIds: string[];
	suggestionModel?: string;
}

interface ArchonRun {
	id: string;
	workflow_name: string;
	status: string;
	user_message: string | null;
	started_at: string | null;
	last_activity_at: string | null;
	completed_at: string | null;
	codebase_name: string | null;
	working_path: string | null;
	metadata?: {
		approval?: {
			message?: string;
			nodeId?: string;
			type?: string;
			captureResponse?: boolean;
		};
	};
}

interface InboxItem {
	runId: string;
	workflowName: string;
	status: string;
	kind: "approval" | "review" | "question" | "feedback-request" | "unknown-paused";
	message: string;
	lastActivityAt: string | null;
}

interface BridgeState {
	config: Required<Pick<ArchonBridgeConfig, "enabled" | "borgosBaseUrl" | "pollIntervalMs">> & ArchonBridgeConfig;
	watchedRunIds: Set<string>;
	inbox: InboxItem[];
	promptedInboxKeys: Set<string>;
	activePromptRunId?: string;
	lastError?: string;
	lastPollAt?: string;
	accessToken?: string;
}

const CUSTOM_STATE = "archon-bridge-state";
const CONFIG_FILE = join(".pi", "archon-bridge.json");
const REPLY_SYSTEM_PROMPT = `You draft concise human replies for paused Archon workflow runs.

Rules:
- Base the draft only on the provided run context.
- Do not invent facts, approvals, or technical results.
- If the run looks like an approval gate, produce a short approval/rejection recommendation plus what to verify.
- If the run contains a question or review request, answer briefly and practically.
- End with a short "Open points:" section only if clarification is still needed.
- Keep output plain text and ready for a human to edit before sending.`;
const DEFAULT_CONFIG: BridgeState["config"] = {
	enabled: true,
	borgosBaseUrl: "http://localhost:8000",
	pollIntervalMs: 15000,
};

export default function archonBridge(pi: ExtensionAPI) {
	let state: BridgeState = {
		config: { ...DEFAULT_CONFIG },
		watchedRunIds: new Set<string>(),
		inbox: [],
		promptedInboxKeys: new Set<string>(),
	};
	let interval: ReturnType<typeof setInterval> | undefined;
	let currentCtx: ExtensionContext | undefined;

	function loadConfig(cwd: string): BridgeState["config"] {
		const path = join(cwd, CONFIG_FILE);
		if (!existsSync(path)) return { ...DEFAULT_CONFIG };
		try {
			const parsed = JSON.parse(readFileSync(path, "utf8")) as ArchonBridgeConfig;
			return {
				...DEFAULT_CONFIG,
				...parsed,
				pollIntervalMs: Math.max(5000, parsed.pollIntervalMs ?? DEFAULT_CONFIG.pollIntervalMs),
			};
		} catch (error) {
			return {
				...DEFAULT_CONFIG,
				enabled: false,
			};
		}
	}

	function refreshConfigFromDisk(): void {
		if (!currentCtx) return;
		const nextConfig = loadConfig(currentCtx.cwd);
		const authChanged =
			nextConfig.borgosBaseUrl !== state.config.borgosBaseUrl ||
			nextConfig.apiToken !== state.config.apiToken ||
			nextConfig.apiUsername !== state.config.apiUsername ||
			nextConfig.apiPassword !== state.config.apiPassword;
		state.config = nextConfig;
		if (authChanged) {
			state.accessToken = undefined;
		}
	}

	function restoreState(ctx: ExtensionContext): void {
		const entries = ctx.sessionManager.getEntries();
		const latest = [...entries]
			.reverse()
			.find((entry: any) => entry.type === "custom" && entry.customType === CUSTOM_STATE);
		const data = latest?.data as PersistedState | undefined;
		state.watchedRunIds = new Set(data?.watchedRunIds ?? []);
		state.promptedInboxKeys = new Set<string>();
		state.activePromptRunId = undefined;
		if (data?.suggestionModel && !state.config.suggestionModel) {
			state.config.suggestionModel = data.suggestionModel;
		}
	}

	function persistState(): void {
		pi.appendEntry(CUSTOM_STATE, {
			watchedRunIds: [...state.watchedRunIds].sort(),
			suggestionModel: state.config.suggestionModel,
		});
	}

	function updateStatus(ctx: ExtensionContext): void {
		const watched = state.watchedRunIds.size;
		const inbox = state.inbox.length;
		const suffix = state.lastError ? ` ⚠ ${state.lastError}` : "";
		ctx.ui.setStatus("archon-bridge", `archon:${watched} watched • ${inbox} open${suffix}`);
		if (watched === 0 && inbox === 0) {
			ctx.ui.setWidget("archon-bridge", undefined);
			return;
		}
		const lines = [
			`Archon Bridge`,
			`watched: ${watched} • open: ${inbox}`,
			...state.inbox.slice(0, 5).map((item) => `- ${item.runId} [${item.kind}] ${item.workflowName}`),
		];
		ctx.ui.setWidget("archon-bridge", lines);
	}

	function classifyRun(run: ArchonRun): InboxItem | null {
		const status = run.status.toLowerCase();
		const message = (run.user_message ?? "").trim();
		const approvalMessage = (run.metadata?.approval?.message ?? "").trim();
		if (status === "paused" && approvalMessage) {
			return {
				runId: run.id,
				workflowName: run.workflow_name,
				status: run.status,
				kind: "approval",
				message: approvalMessage,
				lastActivityAt: run.last_activity_at,
			};
		}
		const combined = `${status} ${message}`.toLowerCase();
		if (!/pause|paused|approval|review|question|feedback|input|waiting/.test(combined)) return null;

		let kind: InboxItem["kind"] = "unknown-paused";
		if (/approval/.test(combined)) kind = "approval";
		else if (/review/.test(combined)) kind = "review";
		else if (/feedback/.test(combined)) kind = "feedback-request";
		else if (/question|input|waiting/.test(combined)) kind = "question";

		return {
			runId: run.id,
			workflowName: run.workflow_name,
			status: run.status,
			kind,
			message: message || `Run ${run.id} requires human attention.`,
			lastActivityAt: run.last_activity_at,
		};
	}

	function isTerminalStatus(status: string): boolean {
		return ["completed", "success", "failed", "error", "cancelled", "rejected"].includes(status.toLowerCase());
	}

	async function ensureAccessToken(): Promise<string | undefined> {
		if (state.config.apiToken) return state.config.apiToken;
		if (state.accessToken) return state.accessToken;
		if (!state.config.apiUsername || !state.config.apiPassword) return undefined;

		const res = await fetch(`${state.config.borgosBaseUrl}/api/auth/token`, {
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body: new URLSearchParams({
				username: state.config.apiUsername,
				password: state.config.apiPassword,
			}).toString(),
		});
		if (!res.ok) {
			throw new Error(`login failed: HTTP ${res.status}`);
		}
		const body = (await res.json()) as { access_token?: string };
		state.accessToken = body.access_token;
		return state.accessToken;
	}

	async function fetchRunsViaApi(forceRefreshToken = false): Promise<ArchonRun[]> {
		if (forceRefreshToken) state.accessToken = undefined;
		const token = await ensureAccessToken();
		const headers: Record<string, string> = { "Content-Type": "application/json" };
		if (token) headers.Authorization = `Bearer ${token}`;
		const res = await fetch(`${state.config.borgosBaseUrl}/api/archon-system/runs?status=all&limit=100`, {
			headers,
		});
		if (res.status === 401 && !forceRefreshToken) {
			return await fetchRunsViaApi(true);
		}
		if (!res.ok) {
			throw new Error(`run poll failed: HTTP ${res.status}`);
		}
		const body = (await res.json()) as { items?: ArchonRun[] };
		return body.items ?? [];
	}

	async function fetchRunsViaCli(): Promise<ArchonRun[]> {
		const result = await runArchon(["workflow", "status", "--json"]);
		if (result.code !== 0) {
			throw new Error(`run poll failed via CLI: ${result.stderr.trim() || result.stdout.trim() || `exit ${result.code}`}`);
		}
		const runs = extractStatusRuns([result.stdout, result.stderr].filter(Boolean).join("\n"));
		if (!runs) {
			throw new Error("run poll failed via CLI: invalid JSON output");
		}
		return runs;
	}

	async function fetchRuns(): Promise<ArchonRun[]> {
		refreshConfigFromDisk();
		try {
			return await fetchRunsViaApi();
		} catch (error) {
			const message = error instanceof Error ? error.message : String(error);
			if (!/HTTP 401|login failed: HTTP 401/i.test(message)) throw error;
			const runs = await fetchRunsViaCli();
			state.lastError = `API auth failed; using Archon CLI fallback`;
			return runs;
		}
	}

	function inboxKey(item: InboxItem): string {
		return `${item.runId}:${item.status}:${item.lastActivityAt ?? ""}:${item.kind}:${item.message}`;
	}

	function extractStatusRuns(raw: string): ArchonRun[] | null {
		const match = raw.match(/(\{[\s\S]*\})\s*$/);
		if (!match) return null;
		try {
			const parsed = JSON.parse(match[1]) as { runs?: ArchonRun[] };
			return parsed.runs ?? null;
		} catch {
			return null;
		}
	}

	async function fetchDetailedRun(runId: string): Promise<ArchonRun | null> {
		const result = await runArchon(["workflow", "status", "--json"]);
		if (result.code !== 0) return null;
		const runs = extractStatusRuns([result.stdout, result.stderr].filter(Boolean).join("\n"));
		return runs?.find((run) => run.id === runId) ?? null;
	}

	async function pollRuns(): Promise<void> {
		if (!currentCtx || !state.config.enabled || state.watchedRunIds.size === 0) return;
		try {
			const previousInboxKeys = new Set(state.inbox.map(inboxKey));
			const runs = await fetchRuns();
			const watched = runs.filter((run) => state.watchedRunIds.has(run.id));
			const terminalRuns = watched.filter((run) => isTerminalStatus(run.status));
			for (const run of terminalRuns) {
				state.watchedRunIds.delete(run.id);
			}
			state.inbox = watched
				.filter((run) => !isTerminalStatus(run.status))
				.map(classifyRun)
				.filter((item): item is InboxItem => item !== null)
				.sort((a, b) => (b.lastActivityAt ?? "").localeCompare(a.lastActivityAt ?? ""));
			state.lastError = undefined;
			state.lastPollAt = new Date().toISOString();
			if (terminalRuns.length > 0) {
				currentCtx.ui.notify(
					`Archon Bridge: ${terminalRuns.length} watched run(s) reached a terminal status and were removed.`,
					"info",
				);
				persistState();
			}
			const nextPrompt = state.inbox.find((item) => {
				const key = inboxKey(item);
				return !previousInboxKeys.has(key) && !state.promptedInboxKeys.has(key);
			});
			if (nextPrompt && !state.activePromptRunId) {
				const key = inboxKey(nextPrompt);
				state.promptedInboxKeys.add(key);
				state.activePromptRunId = nextPrompt.runId;
				try {
					currentCtx.ui.notify(`Archon run ${nextPrompt.runId} requires attention.`, "warning");
					const detailedRun = (await fetchDetailedRun(nextPrompt.runId)) ?? watched.find((run) => run.id === nextPrompt.runId) ?? null;
					if (detailedRun) {
						await promptPausedRunAction(currentCtx, detailedRun);
					}
				} finally {
					state.activePromptRunId = undefined;
				}
			}
		} catch (error) {
			state.lastError = error instanceof Error ? error.message : String(error);
		}
		updateStatus(currentCtx);
	}

	function restartPolling(): void {
		if (interval) clearInterval(interval);
		interval = undefined;
		if (!state.config.enabled) return;
		interval = setInterval(() => {
			void pollRuns();
		}, state.config.pollIntervalMs);
	}

	function requireRunId(args: string, ctx: ExtensionContext): string | null {
		const runId = args.trim();
		if (!runId) {
			ctx.ui.notify("Usage: provide a run ID.", "warning");
			return null;
		}
		return runId;
	}

	function splitRunIdAndMessage(args: string): { runId: string; message?: string } | null {
		const parsed = parseArgs(args);
		const runId = parsed[0];
		if (!runId) return null;
		const message = parsed.slice(1).join(" ").trim();
		return { runId, message: message || undefined };
	}

	async function runArchon(args: string[]): Promise<{ code: number; stdout: string; stderr: string }> {
		return await new Promise((resolve, reject) => {
			const child = spawn("archon", args, { cwd: currentCtx?.cwd ?? process.cwd() });
			let stdout = "";
			let stderr = "";
			child.stdout.on("data", (chunk) => {
				stdout += String(chunk);
			});
			child.stderr.on("data", (chunk) => {
				stderr += String(chunk);
			});
			child.on("error", reject);
			child.on("close", (code) => {
				resolve({ code: code ?? 1, stdout, stderr });
			});
		});
	}

	function parseArgs(input: string): string[] {
		const matches = input.match(/"[^"]*"|'[^']*'|\S+/g) ?? [];
		return matches.map((token) => token.replace(/^['"]|['"]$/g, ""));
	}

	async function discoverNewRunId(beforeIds: Set<string>): Promise<string | undefined> {
		for (let attempt = 0; attempt < 8; attempt++) {
			await new Promise((resolve) => setTimeout(resolve, attempt === 0 ? 500 : 1500));
			const runs = await fetchRuns();
			for (const run of runs) {
				if (!beforeIds.has(run.id)) return run.id;
			}
		}
		return undefined;
	}

	async function snapshotRunIds(): Promise<Set<string>> {
		const runs = await fetchRuns();
		return new Set(runs.map((run) => run.id));
	}

	function getSuggestionModel(ctx: ExtensionContext): Model<Api> | undefined {
		if (state.config.suggestionModel) {
			const slash = state.config.suggestionModel.indexOf("/");
			if (slash > 0) {
				const provider = state.config.suggestionModel.slice(0, slash);
				const modelId = state.config.suggestionModel.slice(slash + 1);
				return ctx.modelRegistry.find(provider, modelId);
			}
		}
		return ctx.model;
	}

	function findInboxItem(runId: string): InboxItem | undefined {
		return state.inbox.find((item) => item.runId === runId);
	}

	function getWatchableRuns(runs: ArchonRun[]): ArchonRun[] {
		return runs
			.filter((run) => !isTerminalStatus(run.status))
			.sort((a, b) => (b.last_activity_at ?? b.started_at ?? "").localeCompare(a.last_activity_at ?? a.started_at ?? ""));
	}

	function formatWatchableRunOption(run: ArchonRun): string {
		const watched = state.watchedRunIds.has(run.id) ? " • watched" : "";
		return `${run.workflow_name} • ${run.status}${watched} • ${run.id.slice(0, 12)}`;
	}

	async function watchRunById(ctx: ExtensionContext, runId: string): Promise<void> {
		state.watchedRunIds.add(runId);
		persistState();
		await pollRuns();

		try {
			const run = (await fetchDetailedRun(runId)) ?? (await fetchRuns()).find((r) => r.id === runId);
			if (run && !isTerminalStatus(run.status)) {
				await promptPausedRunAction(ctx, run);
			}
		} catch {
			// pollRuns already captured errors
		}
		ctx.ui.notify(`Archon Bridge now watches ${runId}.`, "info");
	}

	function buildReplyPrompt(item: InboxItem): string {
		return [
			`Run ID: ${item.runId}`,
			`Workflow: ${item.workflowName}`,
			`Status: ${item.status}`,
			`Kind: ${item.kind}`,
			`Message: ${item.message}`,
			`Last activity: ${item.lastActivityAt ?? "unknown"}`,
			"",
			"Draft a reply the user can review and edit before sending to Archon.",
		].join("\n");
	}

	function deriveWorkspaceRoot(run: ArchonRun): string | undefined {
		const workingPath = run.working_path?.trim();
		if (!workingPath) return undefined;
		const marker = `${sep}worktrees${sep}`;
		const index = workingPath.indexOf(marker);
		if (index < 0) return undefined;
		return workingPath.slice(0, index);
	}

	function deriveArtifactsDir(run: ArchonRun): string | undefined {
		const root = deriveWorkspaceRoot(run);
		return root ? join(root, "artifacts", "runs", run.id) : undefined;
	}

	function deriveLogPath(run: ArchonRun): string | undefined {
		const root = deriveWorkspaceRoot(run);
		return root ? join(root, "logs", `${run.id}.jsonl`) : undefined;
	}

	function readArtifactIfExists(path?: string): string | undefined {
		if (!path || !existsSync(path)) return undefined;
		try {
			return readFileSync(path, "utf8");
		} catch {
			return undefined;
		}
	}

	function extractExplicitQuestions(markdown?: string): Array<{ label: string; prompt: string }> {
		if (!markdown) return [];
		const section = markdown.match(/## Explicit Questions for the User\n([\s\S]*?)(?:\n## |\n<promise>|$)/);
		if (!section) return [];
		const questions: Array<{ label: string; prompt: string }> = [];
		const regex = /\*\*(Q\d+[^*\n]*)\*\*\n([\s\S]*?)(?=\n\*\*Q\d+|\n## |\n<promise>|$)/g;
		for (const match of section[1].matchAll(regex)) {
			const label = match[1].trim();
			const prompt = match[2].trim();
			if (label && prompt) questions.push({ label, prompt });
		}
		return questions;
	}

	function readLastAssistantMessage(run: ArchonRun): string | undefined {
		const path = deriveLogPath(run);
		if (!path || !existsSync(path)) return undefined;
		try {
			const lines = readFileSync(path, "utf8").trim().split("\n");
			for (let index = lines.length - 1; index >= 0; index--) {
				const line = lines[index]?.trim();
				if (!line) continue;
				const parsed = JSON.parse(line) as { type?: string; content?: string };
				if (parsed.type === "assistant" && typeof parsed.content === "string" && parsed.content.trim()) {
					return parsed.content.trim();
				}
			}
		} catch {
			return undefined;
		}
		return undefined;
	}

	function buildGuidedContext(
		run: ArchonRun,
		item: InboxItem,
		questions: Array<{ label: string; prompt: string }>,
		assistantMessage?: string,
	): string {
		const artifactsDir = deriveArtifactsDir(run);
		const reviewPath = artifactsDir ? join(artifactsDir, "plan-review.md") : undefined;
		return [
			`# Archon ${item.kind === "approval" ? "Approval" : "Attention"}`,
			`runId: ${run.id}`,
			`workflow: ${run.workflow_name}`,
			`status: ${run.status}`,
			`last activity: ${run.last_activity_at ?? "—"}`,
			artifactsDir ? `artifacts: ${artifactsDir}` : undefined,
			reviewPath ? `review: ${reviewPath}` : undefined,
			"",
			assistantMessage ? "## Letzte Workflow-Nachricht" : undefined,
			assistantMessage,
			assistantMessage ? "" : undefined,
			"## Approval message",
			item.message,
			"",
			questions.length > 0
				? `Es gibt ${questions.length} Review-Frage(n). Pi stellt sie jetzt einzeln und sammelt deine Antworten.`
				: "Keine expliziten Review-Fragen erkannt. Du kannst direkt antworten oder approven.",
		].filter(Boolean).join("\n");
	}

	async function runGuidedApproval(ctx: ExtensionContext, run: ArchonRun, item: InboxItem): Promise<string | null> {
		const artifactsDir = deriveArtifactsDir(run);
		const review = readArtifactIfExists(artifactsDir ? join(artifactsDir, "plan-review.md") : undefined);
		const questions = extractExplicitQuestions(review);
		const assistantMessage = readLastAssistantMessage(run);
		ctx.ui.setEditorText(buildGuidedContext(run, item, questions, assistantMessage));
		if (questions.length === 0) {
			const freeform = await ctx.ui.editor(
				"Antwort an Archon",
				[item.message, "", "Antwort:", ""].join("\n"),
			);
			return freeform?.trim() ? freeform.trim() : null;
		}

		const answers: string[] = [];
		for (let index = 0; index < questions.length; index++) {
			const question = questions[index];
			const stepContext = [
				`# Archon Frage ${index + 1}/${questions.length}`,
				`runId: ${run.id}`,
				`workflow: ${run.workflow_name}`,
				"",
				question.label,
				"",
				question.prompt,
				"",
				answers.length > 0 ? "## Bisherige Antworten" : undefined,
				...(answers.length > 0 ? answers : []),
			].filter(Boolean).join("\n");
			ctx.ui.setEditorText(stepContext);
			const answer = await ctx.ui.editor(
				`${question.label} (${index + 1}/${questions.length})`,
				stepContext + "\n\nDeine Antwort:\n",
			);
			if (answer === undefined) return null;
			const trimmed = answer.trim();
			answers.push(`${question.label}\n${trimmed || "(keine Antwort angegeben)"}`);
		}

		const compiled = [
			`Antwort zu ${run.workflow_name} (${run.id})`,
			"",
			...answers.flatMap((entry) => [entry, ""]),
		].join("\n").trim();
		ctx.ui.setEditorText(compiled);
		return compiled;
	}

	async function draftReplyForRun(ctx: ExtensionContext, runId: string): Promise<void> {
		await pollRuns();
		const item = findInboxItem(runId);
		if (!item) {
			ctx.ui.notify(`No open inbox item found for ${runId}.`, "warning");
			return;
		}
		const model = getSuggestionModel(ctx);
		if (!model) {
			ctx.ui.notify("No Pi model available for reply suggestions.", "error");
			return;
		}

		const result = await ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
			const loader = new BorderedLoader(tui, theme, `Drafting Archon reply using ${model.provider}/${model.id}...`);
			loader.onAbort = () => done(null);

			const doDraft = async () => {
				const auth = await ctx.modelRegistry.getApiKeyAndHeaders(model);
				if (!auth.ok || !auth.apiKey) {
					throw new Error(auth.ok ? `No API key for ${model.provider}` : auth.error);
				}
				const userMessage: UserMessage = {
					role: "user",
					content: [{ type: "text", text: buildReplyPrompt(item) }],
					timestamp: Date.now(),
				};
				const response = await complete(
					model,
					{ systemPrompt: REPLY_SYSTEM_PROMPT, messages: [userMessage] },
					{ apiKey: auth.apiKey, headers: auth.headers, signal: loader.signal },
				);
				if (response.stopReason === "aborted") return null;
				return response.content
					.filter((c): c is { type: "text"; text: string } => c.type === "text")
					.map((c) => c.text)
					.join("\n")
					.trim();
			};

			doDraft().then(done).catch(() => done(null));
			return loader;
		});

		if (result === null) {
			ctx.ui.notify("Reply drafting cancelled.", "info");
			return;
		}

		ctx.ui.setEditorText(
			[
				`# Archon Reply Draft`,
				`runId: ${item.runId}`,
				`workflow: ${item.workflowName}`,
				`kind: ${item.kind}`,
				"",
				result,
			].join("\n"),
		);
		ctx.ui.notify(`Reply draft for ${runId} loaded into the editor.`, "info");
	}

	async function promptPausedRunAction(ctx: ExtensionContext, run: ArchonRun): Promise<void> {
		const item = classifyRun(run);
		if (!item) return;
		const artifactsDir = deriveArtifactsDir(run);
		const questions = extractExplicitQuestions(readArtifactIfExists(artifactsDir ? join(artifactsDir, "plan-review.md") : undefined));
		ctx.ui.setEditorText(buildGuidedContext(run, item, questions, readLastAssistantMessage(run)));

		if (item.kind === "approval" && questions.length > 0) {
			const compiled = await runGuidedApproval(ctx, run, item);
			if (!compiled) return;
			const followUp = await ctx.ui.select("Antwort verwenden", ["Antwort senden", "Nur im Editor lassen", "Approval ohne Kommentar", "Ablehnen"]);
			if (!followUp || followUp === "Nur im Editor lassen") return;
			if (followUp === "Approval ohne Kommentar") {
				await executeAndRefresh(ctx, "Archon approve", ["workflow", "approve", run.id]);
				return;
			}
			if (followUp === "Ablehnen") {
				await executeAndRefresh(ctx, "Archon reject", ["workflow", "reject", run.id, compiled]);
				return;
			}
			await executeAndRefresh(ctx, "Archon reply", ["workflow", "approve", run.id, compiled]);
			return;
		}

		const options = item.kind === "approval"
			? ["Antwort senden", "Antwortentwurf generieren", "Approval bestätigen", "Ablehnen"]
			: ["Antwort senden", "Antwortentwurf generieren", "Ablehnen"];
		const choice = await ctx.ui.select("Archon-Aktion", options);
		if (!choice) return;

		switch (choice) {
			case "Antwort senden": {
				const reply = await ctx.ui.editor("Antwort an Archon", [item.message, "", "Antwort:", ""].join("\n"));
				if (reply === undefined) return;
				const trimmed = reply.trim();
				if (!trimmed) {
					ctx.ui.notify("Antwort war leer.", "warning");
					return;
				}
				await executeAndRefresh(ctx, "Archon reply", ["workflow", "approve", run.id, trimmed]);
				return;
			}
			case "Antwortentwurf generieren":
				await draftReplyForRun(ctx, run.id);
				return;
			case "Approval bestätigen": {
				const comment = await ctx.ui.input("Kommentar (optional)", "leer lassen = ohne Kommentar");
				if (comment === undefined) return;
				const trimmed = comment.trim();
				await executeAndRefresh(
					ctx,
					"Archon approve",
					trimmed ? ["workflow", "approve", run.id, trimmed] : ["workflow", "approve", run.id],
				);
				return;
			}
			case "Ablehnen": {
				const reason = await ctx.ui.editor("Ablehnungsgrund (optional)", [item.message, "", "Ablehnungsgrund:", ""].join("\n"));
				if (reason === undefined) return;
				const trimmed = reason.trim();
				await executeAndRefresh(
					ctx,
					"Archon reject",
					trimmed ? ["workflow", "reject", run.id, trimmed] : ["workflow", "reject", run.id],
				);
			}
		}
	}

	async function executeAndRefresh(ctx: ExtensionContext, commandLabel: string, archonArgs: string[]): Promise<void> {
		const result = await runArchon(archonArgs);
		ctx.ui.setEditorText([`$ archon ${archonArgs.join(" ")}`, "", result.stdout, result.stderr].filter(Boolean).join("\n"));
		if (result.code !== 0) {
			ctx.ui.notify(`${commandLabel} failed. Output loaded into the editor.`, "error");
			return;
		}
		await pollRuns();
		ctx.ui.notify(`${commandLabel} sent.`, "info");
	}

	async function executeAndWatch(ctx: ExtensionContext, commandLabel: string, archonArgs: string[]): Promise<void> {
		const beforeIds = await snapshotRunIds();
		const result = await runArchon(archonArgs);
		if (result.code !== 0) {
			ctx.ui.setEditorText([`$ archon ${archonArgs.join(" ")}`, "", result.stdout, result.stderr].filter(Boolean).join("\n"));
			ctx.ui.notify(`${commandLabel} failed. Output loaded into the editor.`, "error");
			return;
		}

		let newRunId: string | undefined;
		try {
			newRunId = await discoverNewRunId(beforeIds);
		} catch (error) {
			state.lastError = error instanceof Error ? error.message : String(error);
		}

		if (newRunId) {
			state.watchedRunIds.add(newRunId);
			persistState();
			await pollRuns();
			ctx.ui.notify(`${commandLabel} started. Auto-watching run ${newRunId}.`, "info");
		} else {
			updateStatus(ctx);
			ctx.ui.notify(`${commandLabel} finished, but no new run ID was detected yet.`, "warning");
		}

		ctx.ui.setEditorText([`$ archon ${archonArgs.join(" ")}`, "", result.stdout, result.stderr].filter(Boolean).join("\n"));
	}
	
	pi.registerCommand("archon-watch", {
		description: "Watch an Archon run ID, or choose an active run",
		handler: async (args, ctx) => {
			const runId = args.trim();
			if (!runId) {
				try {
					const runs = getWatchableRuns(await fetchRuns());
					if (runs.length === 0) {
						ctx.ui.notify("No active Archon runs available to watch.", "info");
						return;
					}
					const options = runs.map((run) => formatWatchableRunOption(run));
					const choice = await ctx.ui.select("Archon-Run wählen", options);
					if (!choice) return;
					const index = options.indexOf(choice);
					if (index < 0) {
						ctx.ui.notify("Auswahl konnte nicht zugeordnet werden.", "error");
						return;
					}
					await watchRunById(ctx, runs[index].id);
				} catch (error) {
					ctx.ui.notify(
						`Failed to load active Archon runs: ${error instanceof Error ? error.message : String(error)}`,
						"error",
					);
				}
				return;
			}
			const resolved = requireRunId(runId, ctx) ?? "";
			if (!resolved) return;
			await watchRunById(ctx, resolved);
		},
	});

	pi.registerCommand("archon-unwatch", {
		description: "Stop watching an Archon run ID",
		handler: async (args, ctx) => {
			const runId = requireRunId(args, ctx);
			if (!runId) return;
			state.watchedRunIds.delete(runId);
			state.inbox = state.inbox.filter((item) => item.runId !== runId);
			persistState();
			updateStatus(ctx);
			ctx.ui.notify(`Archon Bridge stopped watching ${runId}.`, "info");
		},
	});

	pi.registerCommand("archon-inbox", {
		description: "Show the current Archon Bridge inbox summary",
		handler: async (_args, ctx) => {
			await pollRuns();
			if (state.inbox.length === 0) {
				ctx.ui.notify("Archon Bridge inbox is empty.", "info");
				return;
			}
			ctx.ui.setEditorText(
				state.inbox
					.map(
						(item) =>
							`[${item.kind}] ${item.workflowName} (${item.runId})\nstatus: ${item.status}\nmessage: ${item.message}\nlast activity: ${item.lastActivityAt ?? "—"}`,
					)
					.join("\n\n"),
			);
			ctx.ui.notify("Archon Bridge inbox loaded into the editor.", "info");
		},
	});

	pi.registerCommand("archon-bridge-status", {
		description: "Show Archon Bridge configuration and runtime status",
		handler: async (_args, ctx) => {
			const authMode = state.config.apiToken
				? "token"
				: state.config.apiUsername && state.config.apiPassword
					? "username/password"
					: "none";
			const suggestionModel = state.config.suggestionModel ?? (ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "current Pi model");
			ctx.ui.setEditorText(
				[
					`enabled: ${state.config.enabled}`,
					`config: ${join(ctx.cwd, CONFIG_FILE)}`,
					`base url: ${state.config.borgosBaseUrl}`,
					`auth: ${authMode}`,
					`poll interval: ${state.config.pollIntervalMs}ms`,
					`suggestion model: ${suggestionModel}`,
					`watched runs: ${[...state.watchedRunIds].join(", ") || "(none)"}`,
					`open inbox items: ${state.inbox.length}`,
					`last poll: ${state.lastPollAt ?? "(never)"}`,
					`last error: ${state.lastError ?? "(none)"}`,
				].join("\n"),
			);
			ctx.ui.notify("Archon Bridge status loaded into the editor.", "info");
		},
	});

	pi.registerCommand("archon-bridge-model", {
		description: "Show the reply-suggestion model",
		handler: async (_args, ctx) => {
			const modelLabel = state.config.suggestionModel ?? (ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : "current Pi model");
			ctx.ui.notify(
				state.config.suggestionModel
					? `Archon Bridge suggestion model: ${modelLabel}`
					: `Archon Bridge uses the current Pi model: ${modelLabel}`,
				"info",
			);
		},
	});

	pi.registerCommand("archon-run", {
		description: "Run an Archon workflow and auto-watch the created run",
		handler: async (args, ctx) => {
			const parsed = parseArgs(args);
			if (parsed.length === 0) {
				ctx.ui.notify("Usage: /archon-run <workflow> [message...]", "warning");
				return;
			}
			await executeAndWatch(ctx, "Archon workflow", ["workflow", "run", ...parsed]);
		},
	});

	pi.registerCommand("archon-continue", {
		description: "Continue an Archon branch and auto-watch the resulting run",
		handler: async (args, ctx) => {
			const parsed = parseArgs(args);
			if (parsed.length === 0) {
				ctx.ui.notify("Usage: /archon-continue <branch> [message...]", "warning");
				return;
			}
			await executeAndWatch(ctx, "Archon continue", ["continue", ...parsed]);
		},
	});

	pi.registerCommand("archon-reply", {
		description: "Draft a reply, or send one via approval comment",
		handler: async (args, ctx) => {
			await pollRuns();
			const parts = splitRunIdAndMessage(args);
			if (!parts) {
				ctx.ui.notify("Usage: /archon-reply <runId> [message...]", "warning");
				return;
			}
			const { runId, message } = parts;
			if (message) {
				await executeAndRefresh(ctx, "Archon reply", ["workflow", "approve", runId, message]);
				return;
			}
			await draftReplyForRun(ctx, runId);
		},
	});

	pi.registerCommand("archon-approve", {
		description: "Approve a paused Archon run, optionally with a comment",
		handler: async (args, ctx) => {
			const parts = splitRunIdAndMessage(args);
			if (!parts) {
				ctx.ui.notify("Usage: /archon-approve <runId> [comment...]", "warning");
				return;
			}
			await executeAndRefresh(
				ctx,
				"Archon approve",
				parts.message ? ["workflow", "approve", parts.runId, parts.message] : ["workflow", "approve", parts.runId],
			);
		},
	});

	pi.registerCommand("archon-reject", {
		description: "Reject a paused Archon run, optionally with a reason",
		handler: async (args, ctx) => {
			const parts = splitRunIdAndMessage(args);
			if (!parts) {
				ctx.ui.notify("Usage: /archon-reject <runId> [reason...]", "warning");
				return;
			}
			await executeAndRefresh(
				ctx,
				"Archon reject",
				parts.message ? ["workflow", "reject", parts.runId, parts.message] : ["workflow", "reject", parts.runId],
			);
		},
	});

	pi.on("session_start", async (_event, ctx) => {
		currentCtx = ctx;
		state.config = loadConfig(ctx.cwd);
		restoreState(ctx);
		restartPolling();
		updateStatus(ctx);
		if (!existsSync(join(ctx.cwd, CONFIG_FILE))) {
			ctx.ui.notify(`Archon Bridge: add ${CONFIG_FILE} to enable API polling.`, "info");
		}
		void pollRuns();
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		if (interval) clearInterval(interval);
		interval = undefined;
		ctx.ui.setStatus("archon-bridge", undefined);
		ctx.ui.setWidget("archon-bridge", undefined);
		currentCtx = undefined;
	});
}
