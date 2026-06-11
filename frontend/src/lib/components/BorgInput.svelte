<script lang="ts">
	interface Props {
		type?: string;
		value?: string;
		placeholder?: string;
		disabled?: boolean;
		id?: string;
		name?: string;
		class?: string;
		autocomplete?: string;
		autofocus?: boolean;
		oninput?: (e: Event) => void;
		onchange?: (e: Event) => void;
		onfocus?: (e: FocusEvent) => void;
	}

	let {
		type = 'text',
		value = $bindable(''),
		placeholder = '',
		disabled = false,
		id,
		name,
		class: cls = '',
		autocomplete,
		autofocus = false,
		oninput,
		onchange,
		onfocus
	}: Props = $props();
</script>

<input
	{type}
	bind:value
	{placeholder}
	{disabled}
	{id}
	{name}
	{autocomplete}
	{autofocus}
	class="borg-input {cls}"
	{oninput}
	{onchange}
	{onfocus}
/>

<style>
	.borg-input {
		font-family: 'JetBrains Mono', monospace;
		font-size: 13px;
		background-color: var(--borg-void);
		color: var(--borg-text-primary);
		border: 1px solid var(--borg-border);
		border-radius: 0;
		padding: 8px 12px;
		width: 100%;
		transition: border-color 150ms ease-out, box-shadow 150ms ease-out;
		outline: none;
	}

	.borg-input::placeholder {
		color: var(--borg-text-disabled);
	}

	.borg-input:focus {
		border-color: var(--borg-cyan);
		box-shadow: var(--glow-cyan);
	}

	.borg-input:disabled {
		opacity: 0.3;
		cursor: not-allowed;
	}
</style>
