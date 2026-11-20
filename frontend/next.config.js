/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // O proxy que injeta TRADER_API_TOKEN está em
  // src/app/api/backend/[...path]/route.ts. Um rewrite não consegue
  // acrescentar esse header sem expô-lo ao browser.
};

module.exports = nextConfig;
