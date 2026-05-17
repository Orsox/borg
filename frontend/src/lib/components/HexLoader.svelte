<script lang="ts">
	let { size = 48, class: cls = '' } = $props();
</script>

<svg
	class="hex-loader {cls}"
	width={size * 1.5}
	height={size * 1.5}
	viewBox="0 0 72 72"
	xmlns="http://www.w3.org/2000/svg"
	aria-label="Loading"
>
	<!-- Center hex -->
	<polygon class="hex hex-0" points="36,18 47,24 47,36 36,42 25,36 25,24" />
	<!-- Top -->
	<polygon class="hex hex-1" points="36,0 47,6 47,18 36,24 25,18 25,6" />
	<!-- Top-right -->
	<polygon class="hex hex-2" points="47,6 58,12 58,24 47,30 36,24 36,12" style="transform: translate(0, 12px)" />
	<!-- Bottom-right -->
	<polygon class="hex hex-3" points="47,30 58,36 58,48 47,54 36,48 36,36" />
	<!-- Bottom -->
	<polygon class="hex hex-4" points="36,42 47,48 47,60 36,66 25,60 25,48" />
	<!-- Bottom-left -->
	<polygon class="hex hex-5" points="25,30 36,36 36,48 25,54 14,48 14,36" />
	<!-- Top-left -->
	<polygon class="hex hex-6" points="25,6 36,12 36,24 25,30 14,24 14,12" />
</svg>

<style>
	.hex-loader {
		overflow: visible;
	}

	.hex {
		fill: none;
		stroke: var(--borg-cyan);
		stroke-width: 1;
		opacity: 0.2;
	}

	@keyframes hex-pulse {
		0%, 100% { opacity: 0.15; fill: transparent; }
		50% { opacity: 1; fill: rgba(0, 229, 255, 0.2); }
	}

	.hex-0 { animation: hex-pulse 1.4s ease-in-out 0s infinite; }
	.hex-1 { animation: hex-pulse 1.4s ease-in-out 0.2s infinite; }
	.hex-2 { animation: hex-pulse 1.4s ease-in-out 0.4s infinite; }
	.hex-3 { animation: hex-pulse 1.4s ease-in-out 0.6s infinite; }
	.hex-4 { animation: hex-pulse 1.4s ease-in-out 0.8s infinite; }
	.hex-5 { animation: hex-pulse 1.4s ease-in-out 1.0s infinite; }
	.hex-6 { animation: hex-pulse 1.4s ease-in-out 1.2s infinite; }
</style>
