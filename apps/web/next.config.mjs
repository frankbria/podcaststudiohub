/** @type {import('next').NextConfig} */
// No eslint.ignoreDuringBuilds / typescript.ignoreBuildErrors (issue #307):
// every `next build` — CI, local, and the on-VPS rebuild in deploy-dev.yml —
// must fail on type or lint errors, not silently ship them.
const nextConfig = {};

export default nextConfig;
