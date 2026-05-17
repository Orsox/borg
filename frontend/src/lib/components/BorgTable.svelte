<script lang="ts">
	interface Props {
		headers: string[];
		class?: string;
		children?: import('svelte').Snippet;
	}

	let { headers, class: cls = '', children }: Props = $props();
</script>

<div class="borg-table-wrapper {cls}">
	<table class="borg-table">
		<thead>
			<tr>
				{#each headers as header}
					<th>{header}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{@render children?.()}
		</tbody>
	</table>
</div>

<style>
	.borg-table-wrapper {
		overflow-x: auto;
		border: 1px solid var(--borg-border);
	}

	.borg-table {
		width: 100%;
		border-collapse: collapse;
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
	}

	.borg-table thead tr {
		background-color: var(--borg-panel);
		border-top: 2px solid var(--borg-cyan);
	}

	.borg-table thead th {
		padding: 12px 16px;
		text-align: left;
		color: var(--borg-cyan);
		font-weight: 400;
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		border-bottom: 1px solid var(--borg-border);
		white-space: nowrap;
	}

	:global(.borg-table tbody tr:nth-child(odd)) {
		background-color: var(--borg-void);
	}

	:global(.borg-table tbody tr:nth-child(even)) {
		background-color: var(--borg-grid);
	}

	:global(.borg-table tbody tr:hover) {
		background-color: var(--borg-border-active);
	}

	:global(.borg-table tbody td) {
		padding: 10px 16px;
		color: var(--borg-text-primary);
		border-bottom: 1px solid var(--borg-border);
	}
</style>
