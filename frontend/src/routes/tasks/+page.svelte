<script lang="ts">
	import { onMount } from 'svelte';
	import BorgPanel from '$lib/components/BorgPanel.svelte';
	import BorgButton from '$lib/components/BorgButton.svelte';
	import BorgInput from '$lib/components/BorgInput.svelte';
	import BorgBadge from '$lib/components/BorgBadge.svelte';
	import {
		listTasks, createTask, getTask, updateTask, deleteTask,
		toggleTask, runTaskNow, getTaskRuns,
	} from '$lib/api/tasks';
	import type { Task, TaskListItem, TaskRun } from '$lib/api/tasks';

	let tasks = $state<TaskListItem[]>([]);
	let selectedTask: Task | null = $state(null);
	let showCreateForm = $state(false);
	let showRunHistory = $state(false);
	let runHistory = $state<TaskRun[]>([]);
	let loading = $state(true);
	let error = $state('');

	// Create form state
	let newName = $state('');
	let newDescription = $state('');
	let newTaskType = $state('shell');
	let newCommand = $state('');
	let newWorkflowName = $state('');
	let newSchedule = $state('');
	let newTags = $state('');
	let saving = $state(false);

	// Cron builder state
	let cronMinute = $state('*');
	let cronHour = $state('*');
	let cronDay = $state('*');
	let cronMonth = $state('*');
	let cronWeekday = $state('*');

	async function loadTasks() {
		try {
			const result = await listTasks(1, 100);
			tasks = result.items;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load tasks';
		} finally {
			loading = false;
		}
	}

	async function selectTask(id: number) {
		try {
			const task = await getTask(id);
			selectedTask = task;
			showRunHistory = false;
			runHistory = [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load task';
		}
	}

	async function saveNewTask() {
		saving = true;
		try {
			const tags = newTags.split(',').map((t) => t.trim().toLowerCase()).filter(Boolean);
			await createTask(
				newName,
				newTaskType,
				newSchedule || null,
				newTaskType === 'shell' ? newCommand || null : null,
				newTaskType === 'archon_workflow' ? newWorkflowName || null : null,
				newDescription || null,
				tags,
			);
			resetForm();
			await loadTasks();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create task';
		} finally {
			saving = false;
		}
	}

	async function toggleTaskEnabled(id: number) {
		try {
			await toggleTask(id);
			await loadTasks();
			if (selectedTask?.id === id) {
				await selectTask(id);
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to toggle task';
		}
	}

	async function triggerRunNow(id: number) {
		try {
			await runTaskNow(id);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to trigger task';
		}
	}

	async function deleteSelectedTask() {
		if (!selectedTask) return;
		try {
			await deleteTask(selectedTask.id);
			selectedTask = null;
			await loadTasks();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete task';
		}
	}

	async function loadRunHistory() {
		if (!selectedTask) return;
		try {
			const result = await getTaskRuns(selectedTask.id, 1, 20);
			runHistory = result.items;
			showRunHistory = true;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load run history';
		}
	}

	function resetForm() {
		newName = '';
		newDescription = '';
		newTaskType = 'shell';
		newCommand = '';
		newWorkflowName = '';
		newSchedule = '';
		newTags = '';
		showCreateForm = false;
	}

	function buildCronExpression() {
		return `${cronMinute} ${cronHour} ${cronDay} ${cronMonth} ${cronWeekday}`;
	}

	function describeCron(expr: string): string {
		if (!expr || expr === '* * * * *') return 'Every minute';
		const parts = expr.split(' ');
		if (parts.length !== 5) return expr;
		const [min, hour, day, month, weekday] = parts;
		let desc = '';
		if (min !== '*') desc += `at minute ${min} `;
		if (hour !== '*') desc += `hour ${hour} `;
		if (day !== '*') desc += `on day ${day} `;
		if (month !== '*') desc += `in month ${month} `;
		if (weekday !== '*') desc += `on weekday ${weekday}`;
		return desc || 'Custom schedule';
	}

	function formatDuration(ms: number | null): string {
		if (ms === null) return '—';
		if (ms < 1000) return `${ms}ms`;
		if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
		return `${(ms / 60000).toFixed(1)}m`;
	}

	function formatTime(dateStr: string): string {
		if (!dateStr) return '—';
		const d = new Date(dateStr);
		return d.toLocaleString('en-GB', {
			day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
		});
	}

	function statusVariant(status: string): string {
		switch (status) {
			case 'success': return 'green';
			case 'failed': return 'red';
			case 'running': return 'amber';
			default: return 'cyan';
		}
	}

	onMount(loadTasks);
</script>

<svelte:head>
	<title>BorgOS — Task Automation</title>
</svelte:head>

<div class="tasks-container">
	<header class="module-header">
		<h1>TASK AUTOMATION</h1>
		<p class="subtitle">Schedule &amp; automate tasks</p>
	</header>

	{#if error}
		<div class="error-banner" role="alert">{error}</div>
	{:else}
		<div class="tasks-layout">
			<!-- Task List -->
			<BorgPanel class="task-list-panel">
				<div class="task-list-header">
					<span class="section-label">TASKS ({tasks.length})</span>
					<BorgButton variant="primary" onclick={() => showCreateForm = !showCreateForm}>
						{showCreateForm ? 'CANCEL' : '+ NEW TASK'}
					</BorgButton>
				</div>

				{#if showCreateForm}
					<div class="create-form">
						<BorgInput bind:value={newName} placeholder="Task name..." />
						<BorgInput bind:value={newDescription} placeholder="Description..." />

						<div class="form-row">
							<label>Type:</label>
							<select class="borg-select" value={newTaskType} oninput={(e) => newTaskType = e.currentTarget.value}>
								<option value="shell">Shell Command</option>
								<option value="archon_workflow">Archon Workflow</option>
							</select>
						</div>

						{#if newTaskType === 'shell'}
							<BorgInput bind:value={newCommand} placeholder="Command to execute..." />
						{:else}
							<BorgInput bind:value={newWorkflowName} placeholder="Workflow name..." />
						{/if}

						<div class="cron-builder">
							<label class="cron-label">SCHEDULE (optional)</label>
							<div class="cron-row">
								<input type="text" class="borg-cron-input" value={cronMinute} oninput={(e) => cronMinute = e.currentTarget.value} placeholder="min" />
								<input type="text" class="borg-cron-input" value={cronHour} oninput={(e) => cronHour = e.currentTarget.value} placeholder="hour" />
								<input type="text" class="borg-cron-input" value={cronDay} oninput={(e) => cronDay = e.currentTarget.value} placeholder="day" />
								<input type="text" class="borg-cron-input" value={cronMonth} oninput={(e) => cronMonth = e.currentTarget.value} placeholder="month" />
								<input type="text" class="borg-cron-input" value={cronWeekday} oninput={(e) => cronWeekday = e.currentTarget.value} placeholder="dow" />
							</div>
							<div class="cron-preview">{describeCron(buildCronExpression())}</div>
						</div>

						<BorgInput bind:value={newTags} placeholder="Tags (comma separated)..." />

						<BorgButton variant="primary" onclick={saveNewTask} disabled={saving || !newName}>
							{saving ? 'CREATING...' : 'CREATE TASK'}
						</BorgButton>
					</div>
				{/if}

				{#if loading}
					<div class="loading-text">LOADING TASKS...</div>
				{:else}
					<ul class="task-list">
						{#each tasks as task (task.id)}
							<li
								class="task-item {selectedTask?.id === task.id ? 'selected' : ''}"
								onclick={() => selectTask(task.id)}
							>
								<div class="task-item-header">
									<span class="task-name">{task.name}</span>
									<BorgBadge variant={task.is_enabled ? 'green' : 'amber'} size="sm">
										{task.is_enabled ? 'ACTIVE' : 'PAUSED'}
									</BorgBadge>
								</div>
								<div class="task-item-meta">
									<span class="task-type">{task.task_type}</span>
									{#if task.schedule}
										<span class="task-schedule">{describeCron(task.schedule)}</span>
									{/if}
								</div>
							</li>
						{/each}
					</ul>
					{#if tasks.length === 0}
						<div class="empty-state">No tasks yet. Create your first task.</div>
					{/if}
				{/if}
			</BorgPanel>

			<!-- Task Detail -->
			<BorgPanel class="task-detail-panel">
				{#if selectedTask}
					<div class="task-detail-header">
						<h2 class="task-detail-title">{selectedTask.name}</h2>
						<div class="task-detail-actions">
							<BorgButton
								variant={selectedTask.is_enabled ? 'secondary' : 'primary'}
								onclick={() => toggleTaskEnabled(selectedTask.id)}
							>
								{selectedTask.is_enabled ? 'DISABLE' : 'ENABLE'}
							</BorgButton>
							<BorgButton variant="primary" onclick={() => triggerRunNow(selectedTask.id)}>
								RUN NOW
							</BorgButton>
							<BorgButton variant="secondary" onclick={loadRunHistory}>
								RUN HISTORY
							</BorgButton>
							<BorgButton variant="danger" onclick={deleteSelectedTask}>DELETE</BorgButton>
						</div>
					</div>

					<div class="task-detail-info">
						<div class="info-row">
							<span class="info-label">TYPE:</span>
							<span class="info-value">{selectedTask.task_type}</span>
						</div>
						{#if selectedTask.description}
							<div class="info-row">
								<span class="info-label">DESCRIPTION:</span>
								<span class="info-value">{selectedTask.description}</span>
							</div>
						{/if}
						{#if selectedTask.task_type === 'shell' && selectedTask.command}
							<div class="info-row">
								<span class="info-label">COMMAND:</span>
								<code class="info-code">{selectedTask.command}</code>
							</div>
						{/if}
						{#if selectedTask.task_type === 'archon_workflow' && selectedTask.archon_workflow_name}
							<div class="info-row">
								<span class="info-label">WORKFLOW:</span>
								<span class="info-value">{selectedTask.archon_workflow_name}</span>
							</div>
						{/if}
						{#if selectedTask.schedule}
							<div class="info-row">
								<span class="info-label">SCHEDULE:</span>
								<span class="info-value">{selectedTask.schedule} — {describeCron(selectedTask.schedule)}</span>
							</div>
						{/if}
						<div class="info-row">
							<span class="info-label">TIMEOUT:</span>
							<span class="info-value">{selectedTask.timeout}s</span>
						</div>
						<div class="info-row">
							<span class="info-label">RETRIES:</span>
							<span class="info-value">{selectedTask.retry_max} (delay: {selectedTask.retry_delay}s)</span>
						</div>
						{#if selectedTask.tags.length > 0}
							<div class="info-row">
								<span class="info-label">TAGS:</span>
								<div class="tag-list">
									{#each selectedTask.tags as tag}
										<BorgBadge variant="cyan" size="sm">{tag}</BorgBadge>
									{/each}
								</div>
							</div>
						{/if}
					</div>

					{#if showRunHistory}
						<div class="run-history">
							<h3 class="history-title">EXECUTION HISTORY</h3>
							{#if runHistory.length === 0}
								<div class="empty-history">No runs yet.</div>
							{:else}
								<table class="borg-table">
									<thead>
										<tr>
											<th>TIME</th>
											<th>STATUS</th>
											<th>DURATION</th>
											<th>EXIT</th>
										</tr>
									</thead>
									<tbody>
										{#each runHistory as run (run.id)}
											<tr>
												<td>{formatTime(run.started_at)}</td>
												<td>
													<BorgBadge variant={statusVariant(run.status)} size="sm">
														{run.status.toUpperCase()}
													</BorgBadge>
												</td>
												<td>{formatDuration(run.duration_ms)}</td>
												<td>{run.exit_code ?? '—'}</td>
											</tr>
										{/each}
									</tbody>
								</table>
							{/if}
						</div>
					{/if}
				{:else}
					<div class="task-detail-empty">
						<p>Select a task to view details.</p>
					</div>
				{/if}
			</BorgPanel>
		</div>
	{/if}
</div>

<style>
	.tasks-container {
		display: flex;
		flex-direction: column;
		gap: 24px;
	}

	.module-header h1 {
		font-size: 24px;
		color: var(--borg-cyan);
		letter-spacing: 0.15em;
		margin: 0 0 8px;
	}

	.subtitle {
		color: var(--borg-text-secondary);
		margin: 0;
		font-size: 13px;
	}

	.error-banner {
		background: var(--borg-void);
		border: 1px solid var(--borg-red);
		color: var(--borg-red);
		padding: 12px 16px;
		font-size: 13px;
	}

	.tasks-layout {
		display: flex;
		gap: 16px;
		min-height: 500px;
	}

	.task-list-panel {
		width: 360px;
		min-width: 300px;
		display: flex;
		flex-direction: column;
	}

	.task-list-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 16px;
	}

	.section-label {
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.1em;
	}

	.create-form {
		padding: 0 16px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.form-row {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: var(--borg-text-secondary);
	}

	.borg-select {
		background: var(--borg-void);
		border: 1px solid var(--borg-border);
		color: var(--borg-text-primary);
		padding: 6px 8px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 12px;
		outline: none;
	}

	.borg-select:focus {
		border-color: var(--borg-cyan);
		box-shadow: var(--glow-cyan);
	}

	.cron-builder {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.cron-label {
		font-size: 11px;
		color: var(--borg-text-secondary);
		letter-spacing: 0.1em;
	}

	.cron-row {
		display: flex;
		gap: 4px;
	}

	.borg-cron-input {
		flex: 1;
		background: var(--borg-void);
		border: 1px solid var(--borg-border);
		color: var(--borg-text-primary);
		padding: 4px 6px;
		font-family: 'JetBrains Mono', monospace;
		font-size: 11px;
		text-align: center;
		outline: none;
	}

	.borg-cron-input:focus {
		border-color: var(--borg-cyan);
	}

	.cron-preview {
		font-size: 10px;
		color: var(--borg-text-secondary);
		text-align: center;
	}

	.task-list {
		list-style: none;
		padding: 0 8px;
		margin: 0;
		flex: 1;
		overflow-y: auto;
	}

	.task-item {
		padding: 12px;
		margin-bottom: 4px;
		cursor: pointer;
		border-left: 2px solid transparent;
		transition: all 150ms ease-out;
	}

	.task-item:hover {
		background: var(--borg-grid);
	}

	.task-item.selected {
		border-left-color: var(--borg-cyan);
		background: var(--borg-grid);
	}

	.task-item-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 4px;
	}

	.task-name {
		color: var(--borg-text-primary);
		font-size: 13px;
	}

	.task-item-meta {
		display: flex;
		gap: 8px;
		font-size: 11px;
		color: var(--borg-text-secondary);
	}

	.task-detail-panel {
		flex: 1;
		display: flex;
		flex-direction: column;
	}

	.task-detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 16px;
	}

	.task-detail-title {
		font-size: 18px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
		margin: 0;
	}

	.task-detail-actions {
		display: flex;
		gap: 8px;
	}

	.task-detail-info {
		padding: 0 16px 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.info-row {
		display: flex;
		gap: 12px;
		font-size: 12px;
	}

	.info-label {
		color: var(--borg-text-secondary);
		min-width: 100px;
		letter-spacing: 0.05em;
	}

	.info-value {
		color: var(--borg-text-primary);
	}

	.info-code {
		color: var(--borg-green);
		font-family: 'JetBrains Mono', monospace;
		background: var(--borg-void);
		padding: 2px 6px;
	}

	.tag-list {
		display: flex;
		gap: 4px;
		flex-wrap: wrap;
	}

	.run-history {
		padding: 0 16px 16px;
		border-top: 1px solid var(--borg-border);
		margin-top: 8px;
	}

	.history-title {
		font-size: 12px;
		color: var(--borg-cyan);
		letter-spacing: 0.1em;
		margin: 16px 0 8px;
	}

	.empty-history {
		color: var(--borg-text-secondary);
		font-size: 12px;
		padding: 16px 0;
	}

	.borg-table {
		width: 100%;
		border-collapse: collapse;
		font-size: 12px;
	}

	.borg-table th {
		text-align: left;
		padding: 8px;
		color: var(--borg-cyan);
		border-bottom: 2px solid var(--borg-cyan);
		font-size: 11px;
		letter-spacing: 0.05em;
	}

	.borg-table td {
		padding: 6px 8px;
		color: var(--borg-text-primary);
		border-bottom: 1px solid var(--borg-border);
	}

	.borg-table tr:nth-child(even) {
		background: var(--borg-grid);
	}

	.task-detail-empty {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--borg-text-secondary);
		font-size: 13px;
	}

	.loading-text {
		padding: 16px;
		text-align: center;
		color: var(--borg-cyan);
		font-size: 12px;
		letter-spacing: 0.1em;
	}

	.empty-state {
		padding: 24px 16px;
		text-align: center;
		color: var(--borg-text-secondary);
		font-size: 12px;
	}
</style>
