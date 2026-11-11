// The docs site's configuration: everything docs-kit does not default.
// https://github.com/branes-ai/docs-kit
export default {
  repo: 'drone-capability',
  title: 'Drone Capability',
  description: 'Benchmarks that map drone algorithms and flight-computer hardware to mission capability.',
  // The session logs are working records, not documentation.
  unpublished: ['sessions'],
  // The plans' equations ($…$, $$…$$), rendered with KaTeX at build time.
  math: true,
  accent: {
    dark: { low: '#2f2114', accent: '#bf8040', high: '#f0d9c1' },
    light: { low: '#f3e3d3', accent: '#7c4d1d', high: '#311f0c' },
  },
  // The C++ API reference, once the repo has public headers:
  // api: {
  //   name: 'Drone Capability C++ API',
  //   brief: '…',
  //   input: ['sdk/include'],
  // },
};
